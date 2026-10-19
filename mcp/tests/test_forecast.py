"""The whole-job quote from a promptfoo sample (forecast.py and the forecast_job tool)."""
import asyncio
import json
import os
from pathlib import Path

import pytest

os.environ["LLMLEDGER_DATA"] = str(Path(__file__).with_name("fixture.json"))

from fastmcp import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

from llmledger_mcp import forecast, speed  # noqa: E402
from llmledger_mcp.server import mcp  # noqa: E402


def call(tool, **args):
    async def go():
        async with Client(mcp) as client:
            return (await client.call_tool(tool, args)).data
    return asyncio.run(go())


def result(test, provider, out, right=True, label="", prompt_tokens=1000, error=None, reasoning=0, cost=None,
           prompt=0, asserts=True):
    """One result as promptfoo 0.124 writes it: a call taking 0.5 s plus 0.02 s an answer token."""
    usage = {"prompt": prompt_tokens, "completion": out, "total": prompt_tokens + out, "numRequests": 1}
    if reasoning:
        usage["completionDetails"] = {"reasoning": reasoning}
    row = {"provider": {"id": provider, "label": label}, "testIdx": test, "promptIdx": prompt,
           "latencyMs": 0 if error else int((0.5 + 0.02 * out) * 1000), "success": right and not error,
           "failureReason": 2 if error else (0 if right else 1), "tokenUsage": usage,
           "gradingResult": {"pass": right, "componentResults": [{"pass": right}]} if asserts and not error else None,
           "testCase": {"assert": [{"type": "contains", "value": "ok"}]} if asserts else {"vars": {}},
           "response": {"error": error} if error else {"output": "ok", "cached": False, "tokenUsage": usage}}
    if error or not right:
        row["error"] = error or "Expected output to contain \"ok\""    # promptfoo writes a failed check here too
    if cost is not None:
        row["cost"] = cost
    return row


def sample(path, results, at_once=4, seconds=95.0, prompts=1):
    path.write_text(json.dumps({
        "evalId": "eval-sample", "runtimeOptions": {"maxConcurrency": at_once, "repeat": 1},
        "results": {"version": 3, "timestamp": "2026-10-19T18:00:00Z",
                    "prompts": [{"label": f"prompt {i + 1}", "raw": "{{q}}"} for i in range(prompts)],
                    "results": results, "stats": {"durationMs": seconds * 1000}}}))
    return str(path)


def three_models(path):
    rows = []
    for i in range(20):
        out = 200 + 50 * i
        rows.append(result(i, "anthropic:messages:claude-opus-5-5", out, right=i not in (3, 11),
                           cost=(1000 * 4 + out * 20) / 1e6))
        rows.append(result(i, "openai:chat:gpt-6.1-sol", out, label="sol", right=i not in (1, 4, 9, 14, 17),
                           error="timeout" if i == 7 else None))
        rows.append(result(i, "ollama:chat:llama3.1:8b", out, right=i % 2 == 0))
    rows[0]["response"]["cached"] = True                          # opus' first answer came from promptfoo's cache
    rows[0]["tokenUsage"] = {"cached": 1200, "total": 1200}
    return sample(path, rows)


def test_req_s47_wilson_ranges():
    low, high = forecast.wilson(18, 20)
    assert (round(low, 3), round(high, 3)) == (0.699, 0.972)
    low, high = forecast.wilson(20, 20)
    assert (round(low, 3), high) == (0.839, 1.0)
    low, high = forecast.wilson(0, 5)
    assert low == 0.0 and round(high, 3) == 0.434
    assert forecast.wilson(0, 0) is None
    assert [forecast.dollars(x) for x in (12.4, 0.5, 0.1, 0.01, 0.0092, 0.056, 0.00031)] == [
        "$12.40", "$0.50", "$0.10", "$0.01", "$0.0092", "$0.056", "$0.00031"]


def test_req_s47_promptfoo_names_ways_and_hosts():
    assert speed.model_part("ollama:chat:llama3.1:8b") == "llama3.1:8b"            # the tag after the colon stays
    assert speed.model_part("bedrock:us.anthropic.claude-opus-5-5-v1:0") == "us.anthropic.claude-opus-5-5-v1:0"
    assert speed.model_part("openai:gpt-6.1-sol") == speed.model_part("openai:chat:gpt-6.1-sol") == "gpt-6.1-sol"
    assert [speed.way_of(p) for p in ("anthropic:claude-agent-sdk", "ollama:chat:qwen3:4b", "openai:chat:x",
                                      "exec:python run.py", "echo")] == ["claude-code", "ollama", "api", "other",
                                                                         "other"]
    assert forecast.hosts_of("bedrock:us.anthropic.claude-opus-5-5-v1:0") == ("bedrock",)
    assert forecast.hosts_of("anthropic:claude-agent-sdk") == ("anthropic",) and forecast.hosts_of("exec:x") == ()


def test_req_s47_a_sample_becomes_a_quote_for_the_whole_job(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    out = call("forecast_job", promptfoo_results=three_models(tmp_path / "sample.json"), items=5000)
    assert out["sample"] == {"file": str(tmp_path / "sample.json"), "eval": "eval-sample", "tests": 20, "results": 60,
                             "at_once": 4, "took": "1.6 minutes"}
    models = {m["model"]: m for m in out["models"]}
    assert list(models) == ["openai / gpt-6.1-sol", "anthropic / claude-opus-5.5", "llama3.1:8b"]   # cheapest first
    opus, sol, llama = models["anthropic / claude-opus-5.5"], models["openai / gpt-6.1-sol"], models["llama3.1:8b"]
    # how often each was right: errors are counted apart, a cached answer still counts as checked
    assert opus["right"] == {"right": 18, "of": 20, "share": 0.9, "low": 0.699, "high": 0.9721}
    assert sol["right"]["right"] == 14 and sol["right"]["of"] == 19 and sol["errors"] == {"failed": 1, "of": 20}
    assert opus["cached_results"] == 1 and opus["tokens_per_call"]["output"] == 700     # cached call left out
    # cost: the average call of the sample at the cheapest listing, times every call of the job
    assert opus["cost"]["cheapest"]["whole_job"] == pytest.approx(5000 * (1000 * 4 + 700 * 20) / 1e6)
    assert opus["cost"]["as_sampled"]["host"] == "anthropic"
    assert opus["cost"]["as_sampled"]["sample_cost"] == pytest.approx(
        sum(1000 * 4 + (200 + 50 * i) * 20 for i in range(1, 20)) / 1e6)
    by_promptfoo = sum(1000 * 4 + (200 + 50 * i) * 20 for i in range(20)) / 1e6        # its cached answer too
    assert opus["cost"]["by_promptfoo"] == {"sample": pytest.approx(by_promptfoo),
                                           "whole_job": pytest.approx(by_promptfoo / 20 * 5000)}
    assert opus["price_change_90_days"] == {"listing": "claude-opus-5-5", "share": 0.05, "low": 0.04, "high": 0.06}
    # time: 0.5 s + 0.02 s a token on 700 tokens, 5,000 calls 4 at once
    assert opus["time"]["per_call_seconds"]["usual"] == pytest.approx(14.5)
    assert opus["time"]["usual_seconds"] == pytest.approx(14.5 * 1250) and opus["time"]["usual"] == "5.0 hours"
    assert opus["time"]["based_on"] == "19 timed calls in this sample"
    # the pick: the sample cannot tell 14 of 19 from 18 of 20, so the cheaper one, with the break-even
    assert out["pick"] == "openai / gpt-6.1-sol"
    assert out["headline"].startswith("gpt-6.1-sol is the pick: right 14 of 19, 51% to 88%; the sample cannot "
                                      "tell it apart from claude-opus-5.5 (18 of 20, 70% to 97%)")
    assert "costs about $44.10 on openai and takes 4.9 hours usually" in out["headline"]
    gap = 0.9 - 14 / 19
    extra = (1000 * 4 + 700 * 20) / 1e6 - (1000 * 2 + 682 * 10) / 1e6
    assert opus["versus_pick"] == (
        f"Right 16 points more often than gpt-6.1-sol and costs ${extra:.4f} more an item: worth it if a wrong answer "
        f"costs you more than ${extra / gap:.3f} to catch and fix. The sample cannot tell the two apart yet.")
    assert llama["way"] == "ollama" and llama["cost"] is None and "local model" in llama["notes"][0]
    assert llama["versus_pick"] == "No token price to compare with gpt-6.1-sol; it was right 24 points less often."
    assert out["job"]["every_model_in_the_sample"]["usual"] == "14.8 hours"


def test_req_s47_the_cost_of_a_wrong_answer_can_decide_the_pick(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    file = three_models(tmp_path / "sample.json")
    out = call("forecast_job", promptfoo_results=file, items=5000, wrong_answer_cost=0.10, concurrency=10)
    assert out["pick"] == "anthropic / claude-opus-5.5"           # 0.018 + 0.1 x 0.1 beats 0.0088 + 0.26 x 0.1
    assert "when a wrong answer costs $0.10" in out["headline"] and "10 at once" in out["headline"]
    sol = next(m for m in out["models"] if m["model"] == "openai / gpt-6.1-sol")
    assert sol["versus_pick"].startswith("Saves $0.0092 an item against claude-opus-5.5 but was right 16 points less")


def test_req_s47_logged_runs_add_to_the_sample_which_counts_once(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    file = three_models(tmp_path / "sample.json")
    logged = call("log_run", promptfoo_results=file)
    # a failed check is still a timed call; only the call that did not run is left out
    assert logged["logged"] == 58 and logged["skipped"] == {"cached": 1, "failed or no time": 1}
    ways = {(r["model"], r["way"]) for r in speed.load()}
    assert ways == {("anthropic / claude-opus-5.5", "api"), ("openai / gpt-6.1-sol", "api"),
                    ("llama3.1:8b", "ollama")}                     # the way read from each provider
    call("log_run", model="claude-opus-5.5", input_tokens=1000, output_tokens=400, seconds=8.5)
    out = call("forecast_job", promptfoo_results=file, items=100)
    opus = next(m for m in out["models"] if m["model"] == "anthropic / claude-opus-5.5")
    assert opus["time"]["based_on"] == "19 timed calls in this sample and 1 of your logged runs"
    for n in range(60):                                          # only the newest 50 runs count
        call("log_run", model="claude-opus-5.5", input_tokens=1000, output_tokens=400, seconds=8.5)
    out = call("forecast_job", promptfoo_results=file, items=100)
    opus = next(m for m in out["models"] if m["model"] == "anthropic / claude-opus-5.5")
    assert opus["time"]["based_on"] == "19 timed calls in this sample and 31 of your logged runs"


def test_req_s47_prompts_repeats_hosts_and_plans(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    rows = []
    for i in range(6):
        for prompt in (0, 1):
            for _ in range(2):                                   # --repeat 2: two calls a test
                rows.append(result(i, "bedrock:us.anthropic.claude-opus-5-5-v1:0", 300, label="claude-opus-5.5",
                                   prompt=prompt, right=prompt == 0 or i < 3))
        if i < 3:
            rows.append(result(i, "anthropic:claude-agent-sdk", 300, label="claude-sonnet-5.5", reasoning=120,
                               cost=0.02))                      # Claude Code's own figure: 4 times the tokens
    out = call("forecast_job", promptfoo_results=sample(tmp_path / "s.json", rows, prompts=2), items=10)
    opus = [m for m in out["models"] if m["model"] == "anthropic / claude-opus-5.5"]
    assert [m["prompt"] for m in opus] == ["prompt 1", "prompt 2"] and [m["calls"] for m in opus] == [20, 20]
    assert opus[0]["right"]["right"] == 12 and opus[1]["right"]["right"] == 6
    assert opus[0]["cost"]["cheapest"]["host"] == "anthropic"                  # $4/$20, cheaper than Bedrock's
    assert opus[0]["cost"]["as_sampled"]["listing"] == "bedrock/claude-opus-5-5"
    assert opus[0]["cost"]["as_sampled"]["whole_job"] == pytest.approx(20 * (1000 * 4.4 + 300 * 22) / 1e6)
    sonnet = next(m for m in out["models"] if m["model"] == "anthropic / claude-sonnet-5.5")
    assert sonnet["way"] == "claude-code" and sonnet["thinking"] is True and sonnet["calls"] == 10
    assert "on a Claude plan the job uses the plan" in sonnet["cost"]["as_sampled"]["note"]
    assert sonnet["cost"]["as_sampled"]["sample_cost"] == pytest.approx(3 * (1000 * 2 + 300 * 10) / 1e6)
    assert sonnet["cost"]["by_promptfoo"]["whole_job"] == pytest.approx(0.2)
    assert sonnet["cost"]["by_promptfoo"]["note"].endswith("At promptfoo's rate the job is $0.20.")
    assert sonnet["time"]["rough"].startswith("Fewer than 5 timed calls")      # 3 tests of it in the sample
    assert out["pick"] == "anthropic / claude-sonnet-5.5"


def test_req_s47_no_checks_and_bad_input(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    rows = [result(i, p, 400, asserts=False) for i in range(3) for p in ("anthropic:messages:claude-opus-5-5",
                                                                         "openai:chat:gpt-6.1-sol")]
    out = call("forecast_job", promptfoo_results=sample(tmp_path / "s.json", rows), items=30)
    assert out["pick"] == "openai / gpt-6.1-sol" and all(m["right"] is None for m in out["models"])
    assert "has no checks" in out["notes"][0] and "no checks to say how often" in out["headline"]
    out = call("forecast_job", promptfoo_results=str(tmp_path / "s.json"), items=30, wrong_answer_cost=1.0)
    assert out["pick"] == "openai / gpt-6.1-sol" and "no checks to say how often" in out["headline"]
    with pytest.raises(ToolError, match="Not a promptfoo results file"):
        call("forecast_job", promptfoo_results=str(tmp_path / "missing.json"), items=10)
    with pytest.raises(ToolError, match="has no results"):
        call("forecast_job", promptfoo_results=sample(tmp_path / "empty.json", []), items=10)
    with pytest.raises(ToolError):
        call("forecast_job", promptfoo_results=str(tmp_path / "s.json"), items=0)
