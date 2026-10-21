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
    for name in ("__init__.py", "data.py", "logic.py", "tools.py", "speed.py", "forecast.py", "usage.py"):
        assert (SKILL / "scripts" / "llmledger_mcp" / name).read_bytes() == (PLUGIN / name).read_bytes(), name
    # the shared code needs nothing outside the standard library
    for name in ("data.py", "logic.py", "tools.py", "speed.py", "forecast.py", "usage.py"):
        imports = re.findall(r"^(?:from|import) (\w+)", (PLUGIN / name).read_text(), re.M)
        assert set(imports) <= {"gzip", "json", "os", "re", "tempfile", "time", "urllib", "importlib", "pathlib",
                                "math", "datetime", "statistics", "random", "llmledger_mcp"}, (name, imports)


def test_req_s41_skill_md_follows_the_agent_skills_format():
    fields, head, body = frontmatter()
    assert fields["name"] == SKILL.name == "llmledger"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fields["name"]) and len(fields["name"]) <= 64
    assert 1 <= len(fields["description"]) <= 1024 and "Use when" in fields["description"]
    assert len(fields["compatibility"]) <= 500 and fields["license"] == "MIT"
    assert f'version: "{VERSION}"' in head
    assert body.count("\n") < 500 and len(body) / 4 < 5000          # well under the format's limits
    assert "—" not in (SKILL / "SKILL.md").read_text()
    for command in ("suggest", "compare", "cost", "find", "history", "unpriced", "time", "log", "forecast", "local",
                    "tasks"):
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


def test_req_s45_the_script_times_a_job_from_logged_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    code, out = run("time", "claude-opus-5.5", "--input", "1000", "--output", "500")
    assert code == 0 and out["estimate"] is None
    for n in (100, 300, 500, 700, 900):
        code, out = run("log", "claude-opus-5.5", "--input", "1000", "--output", str(n), "--seconds", str(1 + n / 100))
        assert code == 0 and out["logged"] == 1
    code, out = run("time", "claude-opus-5.5", "--input", "1000", "--output", "500", "--calls", "10", "--at-once", "2")
    assert out["per_call_seconds"]["usual"] == 6.0 and out["job"]["usual_seconds"] == 30.0
    # no data at all: timing a local model still works
    code, out = run("time", "llama3.1:8b", "--input", "10", "--output", "10", "--way", "ollama",
                    data="http://127.0.0.1:9/data.json", cache=tmp_path / "empty")
    assert code == 0 and out["runs_used"] == 0


def test_req_s47_the_script_quotes_a_job_from_a_promptfoo_sample(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    usage = {"prompt": 1000, "completion": 500, "total": 1500, "numRequests": 1}
    results = [{"provider": {"id": provider, "label": ""}, "testIdx": i, "promptIdx": 0, "latencyMs": 10500,
                "success": i != 0 or provider.startswith("openai"), "failureReason": 0, "tokenUsage": usage,
                "gradingResult": {"pass": True, "componentResults": [{"pass": True}]},
                "response": {"output": "ok", "cached": False, "tokenUsage": usage}}
               for i in range(10) for provider in ("anthropic:messages:claude-opus-5-5", "openai:chat:gpt-6.1-sol")]
    file = tmp_path / "sample.json"
    file.write_text(json.dumps({"evalId": "e1", "results": {"results": results, "prompts": [], "stats": {}}}))
    code, out = run("forecast", str(file), "--items", "1000", "--at-once", "5")
    assert code == 0 and out["pick"] == "openai / gpt-6.1-sol"          # right 10 of 10 and the cheaper
    sol = out["models"][0]
    assert sol["cost"]["cheapest"]["whole_job"] == 1000 * (1000 * 2 + 500 * 10) / 1e6
    assert sol["time"]["usual_seconds"] == 10.5 * 200 and sol["right"]["right"] == 10
    code, out = run("forecast", str(tmp_path / "nothing.json"), "--items", "10")
    assert code == 1 and out["error"].startswith("Not a promptfoo results file")


def test_req_s48_the_script_says_when_buying_a_computer_pays_off(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    for n in (100, 300, 500, 700, 900):
        run("log", "llama3.1:8b", "--input", "2000", "--output", str(n), "--seconds", str(1 + n / 50), "--way", "ollama")
    code, out = run("local", "llama3.1:8b", "gpt-6.1-sol", "--input", "2000", "--output", "500",
                    "--calls-per-month", "30000", "--hardware-price", "2000", "--watts", "150", "--kwh-price", "0.2")
    power = 30000 * 11 / 3600 * 0.15 * 0.2
    assert code == 0 and out["local"]["electricity_a_month"]["usual"] == round(power, 4)
    assert out["cloud"][0]["buying_pays_off_after_months"]["usual"] == round(2000 / (270 - power), 1)


def test_req_s55_the_script_prices_an_export(tmp_path):
    rows = [{"sessionId": f"s{i}", "lastActivity": "2026-10-10T10:00:00Z", "inputTokens": 1000, "outputTokens": 400,
             "cacheCreationTokens": 0, "cacheReadTokens": 0, "totalTokens": 1400, "totalCost": 0.1,
             "modelsUsed": ["claude-opus-5-5"],
             "modelBreakdowns": [{"modelName": "claude-opus-5-5", "inputTokens": 1000, "outputTokens": 400,
                                  "cacheCreationTokens": 0, "cacheReadTokens": 0, "cost": 0.1}]} for i in range(6)]
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps({"sessions": rows, "totals": {}}))
    code, out = run("usage", str(path), "--task", "coding", "--compare", "claude-opus-5.5", "gpt-6.1-sol")
    assert code == 0 and out["source"] == "ccusage session" and out["sessions"] == 6
    assert out["you_paid"]["cost"] == 6 * (1000 * 4 + 400 * 20) / 1e6
    assert out["tests"][0]["kind"] == "same work" and "real difference" in out["tests"][0]["verdict"]
    code, out = run("usage", str(tmp_path / "missing.json"))
    assert code == 1 and "No file" in out["error"]


def test_req_s41_the_script_says_what_went_wrong(tmp_path):
    code, out = run("compare", "no-such-model", "gpt-6.1-sol")
    assert code == 1 and out["error"].startswith("Not found: 'no-such-model'")
    code, out = run("compare", "gpt-6.1-sol")
    assert code == 1 and out["error"] == "Give 2 to 6 models to compare."
    # no copy saved and nothing to download: a clear message, not a crash
    code, out = run("tasks", data="http://127.0.0.1:9/data.json", cache=tmp_path)
    assert code == 1 and out["error"].startswith("No data yet:")
