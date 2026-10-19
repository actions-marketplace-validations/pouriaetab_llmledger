"""The Agent Skill (skills/llmledger) runs the plug-in's own code with plain Python and the same data."""
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
SKILL = ROOT / "skills" / "llmledger"
PLUGIN = ROOT / "mcp" / "src" / "llmledger_mcp"
FIXTURE = ROOT / "mcp" / "tests" / "fixture.json"
VERSION = tomllib.loads((ROOT / "mcp" / "pyproject.toml").read_text())["project"]["version"]


def run(*args, data=FIXTURE, cache=None):
    env = {**os.environ, "LLMLEDGER_DATA": str(data)}
    if cache:
        env["XDG_CACHE_HOME"] = str(cache)
    done = subprocess.run([sys.executable, str(SKILL / "scripts" / "llmledger.py"), *args],
                          capture_output=True, text=True, env=env, timeout=60)
    return done.returncode, json.loads(done.stdout)


def frontmatter():
    text = (SKILL / "SKILL.md").read_text()
    head, body = text.split("---\n", 2)[1:]
    fields = dict(re.findall(r"^(\w+): (.+)$", head, re.M))
    return fields, head, body


def test_req_s41_the_skill_carries_an_exact_copy_of_the_plugin_code():
    for name in ("__init__.py", "data.py", "logic.py", "tools.py"):
        assert (SKILL / "scripts" / "llmledger_mcp" / name).read_bytes() == (PLUGIN / name).read_bytes(), name
    # the shared code needs nothing outside the standard library
    for name in ("data.py", "logic.py", "tools.py"):
        imports = re.findall(r"^(?:from|import) (\w+)", (PLUGIN / name).read_text(), re.M)
        assert set(imports) <= {"gzip", "json", "os", "re", "tempfile", "time", "urllib", "importlib", "pathlib",
                                "math", "datetime", "llmledger_mcp"}, (name, imports)


def test_req_s41_skill_md_follows_the_agent_skills_format():
    fields, head, body = frontmatter()
    assert fields["name"] == SKILL.name == "llmledger"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fields["name"]) and len(fields["name"]) <= 64
    assert 1 <= len(fields["description"]) <= 1024 and "Use when" in fields["description"]
    assert len(fields["compatibility"]) <= 500 and fields["license"] == "MIT"
    assert f'version: "{VERSION}"' in head
    assert body.count("\n") < 500 and len(body) / 4 < 5000          # well under the format's limits
    assert "—" not in (SKILL / "SKILL.md").read_text()
    for command in ("suggest", "compare", "cost", "find", "history", "tasks"):
        assert f"`{command}" in body


def test_req_s41_the_repository_is_a_claude_code_marketplace_for_the_skill():
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert market["name"] == plugin["name"] == "llmledger" and market["owner"]["name"]
    assert market["plugins"] == [{**market["plugins"][0], "name": "llmledger", "source": "./"}]
    assert plugin["version"] == VERSION and plugin["license"] == "MIT"
    assert (ROOT / "skills" / "llmledger" / "SKILL.md").exists()
    # nothing else in the repository root is loaded as part of the plugin
    assert not any((ROOT / name).exists() for name in ("hooks", "agents", "commands", ".mcp.json"))


def test_req_s41_the_script_gives_the_plugins_answers():
    code, out = run("compare", "opus 5.5", "claude-fable-5-1", "claude-sonnet-5.5", "--task", "coding")
    assert code == 0 and out["pick"] == "anthropic / claude-opus-5.5"
    assert out["models"][0]["cost_per_task"] == (1000 * 4 + 800 * 20) / 1e6
    code, out = run("cost", "claude-opus-5.5", "gpt-6.1-sol", "--input", "1000", "--output", "500",
                    "--calls-per-day", "100")
    assert [m["per_30_days"] for m in out["models"]] == [(1000 * 2 + 500 * 10) / 1e6 * 3000,
                                                          (1000 * 4 + 500 * 20) / 1e6 * 3000]
    code, out = run("suggest", "Fix this Python function so the tests pass: def add(a, b): return a - b")
    assert code == 0 and out["task"] == "Coding" and out["picks"][0]["role"] == "best value"
    code, out = run("history", "claude-opus-5.5")
    assert {x["listing"] for x in out["listings"]} == {"claude-opus-5-5", "bedrock/claude-opus-5-5"}
    code, out = run("find", "--task", "coding", "--needs", "vision", "--limit", "5")
    found = {m["model"]: m["listing"] for m in out["models"]}
    assert found["anthropic / claude-opus-5.5"] == "claude-opus-5-5"          # the listing that takes images
    assert "anthropic / claude-sonnet-5.5" not in found
    code, out = run("tasks")
    assert out["models_listed"] == 6 and "coding" in out["tasks"]
    code, out = run("history", "bedrock/claude-opus-5-5", "--date", "2026-08-15")
    assert code == 0 and out["listings"][0]["on_date"]["price_per_1m"]["input"] == 5.0
    code, out = run("cost", "claude-opus-5.5", "--input", "10000", "--output", "1000", "--cached", "8000",
                    "--cache-write", "1000")
    assert code == 0 and out["models"][0]["without_cache"]["per_call"] == (10000 * 4 + 1000 * 20) / 1e6
    code, out = run("unpriced")
    assert code == 1 and "no list of models not yet priced" in out["error"]   # the test data has none


def test_req_s41_the_script_says_what_went_wrong(tmp_path):
    code, out = run("compare", "no-such-model", "gpt-6.1-sol")
    assert code == 1 and out["error"].startswith("Not found: 'no-such-model'")
    code, out = run("compare", "gpt-6.1-sol")
    assert code == 1 and out["error"] == "Give 2 to 6 models to compare."
    # no copy saved and nothing to download: a clear message, not a crash
    code, out = run("tasks", data="http://127.0.0.1:9/data.json", cache=tmp_path)
    assert code == 1 and out["error"].startswith("No data yet:")
