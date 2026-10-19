"""Time estimates learned from the user's own runs (speed.py), and the two tools that use them."""
import asyncio
import json
import os
from pathlib import Path

import pytest

os.environ["LLMLEDGER_DATA"] = str(Path(__file__).with_name("fixture.json"))

from fastmcp import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

from llmledger_mcp import speed  # noqa: E402
from llmledger_mcp.server import mcp  # noqa: E402


def call(tool, **args):
    async def go():
        async with Client(mcp) as client:
            return (await client.call_tool(tool, args)).data
    return asyncio.run(go())


def runs(points, model="m", way="api"):
    return [{"model": model, "way": way, "thinking": False, "input": 1000, "output": out, "seconds": sec}
            for out, sec in points]


def test_a_straight_line_is_found_exactly():
    line = runs([(out, 0.5 + 0.02 * out) for out in (100, 300, 500, 800, 1200)])
    start, slope = speed.fit(line)
    assert start == pytest.approx(0.5) and slope == pytest.approx(0.02)
    usual, slow = speed.estimate(line, 1000)
    assert usual == pytest.approx(20.5) and slow == pytest.approx(20.5)        # every run on the line


def test_one_slow_run_barely_moves_the_usual_time():
    line = runs([(out, 0.5 + 0.02 * out) for out in (100, 300, 500, 800, 1200, 600)] + [(400, 80.0)])
    usual, slow = speed.estimate(line, 1000)
    assert usual == pytest.approx(20.5, rel=0.05)                              # Theil-Sen and the median ratio
    assert slow > usual                                                         # the slow run shows in a slow day


def test_few_runs_give_a_rough_range():
    usual, slow = speed.estimate(runs([(500, 10.0)]), 1000)
    assert usual == pytest.approx(20.0) and slow == pytest.approx(40.0)         # one run: 0.02 s a token, slow day 2x


def test_logging_and_estimating_through_the_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    none = call("estimate_time", model="claude-opus-5.5", input_tokens=1000, output_tokens=800)
    assert none["estimate"] is None and "log_run" in none["note"] and none["model"] == "anthropic / claude-opus-5.5"
    for out in (200, 400, 600, 800, 1000):
        logged = call("log_run", model="opus 5.5", input_tokens=1000, output_tokens=out, seconds=1 + out / 50)
        assert logged["logged"] == 1 and logged["run"]["model"] == "anthropic / claude-opus-5.5"   # one name
    call("log_run", model="llama3.1:8b", input_tokens=500, output_tokens=100, seconds=3, way="ollama")
    out = call("estimate_time", model="claude-opus-5.5", input_tokens=1000, output_tokens=500, calls=100, concurrency=4)
    assert out["runs_used"] == 5 and "rough" not in out
    assert out["per_call_seconds"]["usual"] == pytest.approx(11.0)
    assert out["job"]["usual_seconds"] == pytest.approx(11.0 * 25) and out["job"]["usual"] == "4.6 minutes"
    other = call("estimate_time", model="claude-opus-5.5", input_tokens=1000, output_tokens=500, way="claude-code")
    assert other["estimate"] is None and other["runs_of_this_model"] == [{"way": "api", "thinking": False}]
    local = call("estimate_time", model="llama3.1:8b", input_tokens=500, output_tokens=200, way="ollama")
    assert local["model"] == "llama3.1:8b" and local["per_call_seconds"]["usual"] == pytest.approx(6.0)
    with pytest.raises(ToolError, match="Give model"):
        call("log_run", model="claude-opus-5.5")


def promptfoo_file(path, results):
    path.write_text(json.dumps({"evalId": "eval-abc", "results": {"version": 3, "timestamp": "2026-10-19T18:04:47Z",
                                                                  "results": results}}))
    return str(path)


def test_a_promptfoo_results_file_counts_as_runs_once(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    usage = {"prompt": 900, "completion": 300, "cached": 0, "total": 1200, "numRequests": 1}
    results = [
        {"provider": {"id": "anthropic:messages:claude-opus-5-5", "label": ""}, "latencyMs": 6500,
         "tokenUsage": usage, "response": {"output": "...", "cached": False, "tokenUsage": usage}},
        {"provider": {"id": "openai:chat:gpt-6.1-sol", "label": "sol"}, "latencyMs": 4000,
         "response": {"output": "...", "cached": False, "tokenUsage": usage}},
        {"provider": {"id": "anthropic:messages:claude-opus-5-5"}, "latencyMs": 3,
         "tokenUsage": usage, "response": {"cached": True}},
        {"provider": {"id": "anthropic:messages:claude-opus-5-5"}, "latencyMs": 0, "error": "timeout", "response": {}},
        {"provider": {"id": "mcp"}, "latencyMs": 2180, "response": {"output": "...", "cached": False}},  # a tool call
    ]
    file = promptfoo_file(tmp_path / "results.json", results)
    first = call("log_run", promptfoo_results=file)
    assert first["logged"] == 2
    assert first["skipped"] == {"cached": 1, "failed or no time": 1, "no tokens (not a model call)": 1}
    # the label wins over the id, and either becomes the catalogue's name when it knows the model
    assert first["models"] == ["anthropic / claude-opus-5.5", "openai / gpt-6.1-sol"]
    again = call("log_run", promptfoo_results=file)
    assert again["logged"] == 0 and again["skipped"] == {"already logged": 2, "cached": 1, "failed or no time": 1,
                                                         "no tokens (not a model call)": 1}
    saved = speed.load()
    assert saved[0]["seconds"] == 6.5 and saved[0]["output"] == 300 and saved[0]["source"] == "promptfoo:eval-abc:0"
    with pytest.raises(ToolError, match="Not a promptfoo results file"):
        call("log_run", promptfoo_results=str(tmp_path / "nothing.json"))


def test_bad_input_says_what_to_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    with pytest.raises(speed.SpeedError, match="Unknown way"):
        speed.log("m", 1, 1, 1.0, way="carrier pigeon")
    with pytest.raises(speed.SpeedError, match="more than 0"):
        speed.log("m", 1, 1, 0)
    (tmp_path / "runs.jsonl").write_text('{"model": "m", "way": "api", "output": 10, "seconds": 1}\n{"half a line')
    assert len(speed.load()) == 1                                               # a broken line is skipped
