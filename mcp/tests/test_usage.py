"""Your usage on other models (usage.py and the price_my_usage tool, REQ-S55)."""
import asyncio
import copy
import json
import os
from pathlib import Path

import pytest

os.environ["LLMLEDGER_DATA"] = str(Path(__file__).with_name("fixture.json"))

from fastmcp import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

from llmledger_mcp import data, tools, usage  # noqa: E402
from llmledger_mcp.server import mcp  # noqa: E402

FIXTURE = json.loads(Path(__file__).with_name("fixture.json").read_text())


def call(tool, **args):
    async def go():
        async with Client(mcp) as client:
            return (await client.call_tool(tool, args)).data
    return asyncio.run(go())


def shelf(changes=None):
    d = copy.deepcopy(FIXTURE)
    for key, events in (changes or {}).items():
        d["events"][key] = events
    return data.Shelf(d, "file")


def breakdown(model, i, o, w=0, r=0):
    return {"modelName": model, "inputTokens": i, "outputTokens": o, "cacheCreationTokens": w, "cacheReadTokens": r,
            "cost": 0.0}


def ccusage_daily(path):
    """Two days as `ccusage daily --json` writes them: one with two models, one with one and no breakdown list."""
    path.write_text(json.dumps({"daily": [
        {"date": "2026-10-10", "inputTokens": 3000, "outputTokens": 1300, "cacheCreationTokens": 500,
         "cacheReadTokens": 20000, "totalTokens": 24800, "totalCost": 1.0,
         "modelsUsed": ["claude-opus-5-5", "claude-sonnet-5-5"],
         "modelBreakdowns": [breakdown("claude-opus-5-5", 2000, 800, 500, 20000), breakdown("claude-sonnet-5-5", 1000, 500)]},
        {"date": "2026-10-11", "inputTokens": 1000, "outputTokens": 400, "cacheCreationTokens": 0, "cacheReadTokens": 0,
         "totalTokens": 1400, "totalCost": 0.1, "modelsUsed": ["claude-opus-5-5"], "modelBreakdowns": []},
        {"date": "2026-10-12", "inputTokens": 10, "outputTokens": 1, "cacheCreationTokens": 0, "cacheReadTokens": 0,
         "totalTokens": 11, "totalCost": 0, "modelsUsed": ["<synthetic>"], "modelBreakdowns": [breakdown("<synthetic>", 10, 1)]},
    ], "totals": {"inputTokens": 4010}}))
    return str(path)


def ccusage_session(path, n=6, model="claude-opus-5-5"):
    rows = [{"sessionId": f"s{i}", "projectPath": "/home/x/proj", "firstActivity": f"2026-10-0{1 + i % 9}T09:00:00Z",
             "lastActivity": f"2026-10-0{1 + i % 9}T10:00:00Z", "inputTokens": 1000 + 100 * i, "outputTokens": 400,
             "cacheCreationTokens": 0, "cacheReadTokens": 0, "totalTokens": 1400 + 100 * i, "totalCost": 0.1,
             "modelsUsed": [model], "modelBreakdowns": [breakdown(model, 1000 + 100 * i, 400)]} for i in range(n)]
    path.write_text(json.dumps({"sessions": rows, "totals": {}}))
    return str(path)


def codeburn(path, sessions=6, second="claude-sonnet-5-5", second_sessions=5, with_models=True):
    """A `codeburn export -f json` file (schema v2): records per call, and per-model rows with one-shot rates."""
    records = []
    for i in range(sessions):
        for k in range(3):
            records.append({"project": "/home/x/proj", "sessionId": f"a{i}", "timestamp": f"2026-10-1{i % 9}T12:0{k}:00Z",
                            "category": "debugging" if k else "coding", "provider": "claude-code",
                            "model": "claude-opus-5-5", "inputTokens": 700, "outputTokens": 300 + 50 * i,
                            "reasoningTokens": 0, "cacheWriteTokens": 100, "cacheReadTokens": 5000, "cost": 0.01, "savings": 0})
    for i in range(second_sessions):
        records.append({"project": "/home/x/other", "sessionId": f"b{i}", "timestamp": f"2026-10-1{i}T15:00:00Z",
                        "category": "planning", "provider": "claude-code", "model": second, "inputTokens": 2000,
                        "outputTokens": 600, "reasoningTokens": 50, "cacheWriteTokens": 0, "cacheReadTokens": 0,
                        "cost": 0.01, "savings": 0})
    records.append({"sessionId": "a0", "timestamp": "2026-10-10T12:05:00Z", "category": "coding", "model": "claude-opus-5-5",
                    "inputTokens": 999999, "outputTokens": 0, "cacheWriteTokens": 0, "cacheReadTokens": 0, "cost": 0,
                    "supplementary": True})
    models = [{"Period": "30 Days", "Model": "claude-opus-5-5", "Cost (USD)": 1.0, "API Calls": 18, "Edit Turns": 40,
               "One-shot Rate (%)": 75.0, "Retries/Edit": 0.3},
              {"Period": "30 Days", "Model": second, "Cost (USD)": 0.5, "API Calls": 5, "Edit Turns": 20,
               "One-shot Rate (%)": 50.0, "Retries/Edit": 0.8}] if with_models else []
    path.write_text(json.dumps({"schema": "codeburn.export.v2", "generated": "2026-10-20T00:00:00Z",
                                "currency": {"code": "USD", "rate": 1, "symbol": "$"}, "summary": [],
                                "periods": [{"label": "7 Days", "daily": [], "activity": [], "models": []},
                                            {"label": "30 Days", "daily": [], "activity": [], "models": models}],
                                "projects": [], "sessions": [], "records": records, "tools": [], "mcp": [], "shellCommands": []}))
    return str(path)


# ---------- readers ----------
def test_req_s55_ccusage_daily_rows_become_units_per_day_and_model(tmp_path):
    got = usage.read(ccusage_daily(tmp_path / "d.json"))
    assert got["source"] == "ccusage daily"
    units = got["units"]
    # the day with two models gives two units, the day with one model and no breakdown list uses the day's totals,
    # and the synthetic model is left out
    assert [(u["day"], u["model"], u["input"], u["output"], u["cache_write"], u["cache_read"]) for u in units] == [
        ("2026-10-10", "claude-opus-5-5", 2000, 800, 500, 20000), ("2026-10-10", "claude-sonnet-5-5", 1000, 500, 0, 0),
        ("2026-10-11", "claude-opus-5-5", 1000, 400, 0, 0)]
    assert all(u["session"] == u["day"] for u in units) and all(u["task"] is None for u in units)


def test_req_s55_ccusage_20_writes_period_and_session_and_both_are_read(tmp_path):
    """ccusage 20.0.37 (checked on a real export, 20 Oct 2026): daily rows carry `period`, not `date`; sessions sit
    under `session`, named by `period`, with the time under metadata.lastActivity."""
    (tmp_path / "d.json").write_text(json.dumps({"daily": [
        {"agent": "all", "period": "2026-04-11", "metadata": {"agents": ["codex"]}, "inputTokens": 96335, "outputTokens": 21005,
         "cacheCreationTokens": 0, "cacheReadTokens": 1024128, "totalTokens": 1141468, "totalCost": 0.81, "modelsUsed": ["gpt-5.4"],
         "modelBreakdowns": [breakdown("gpt-5.4", 96335, 21005, 0, 1024128)]}], "totals": {}}))
    units = usage.read(tmp_path / "d.json")["units"]
    assert [(u["day"], u["session"], u["model"], u["cache_read"]) for u in units] == [("2026-04-11", "2026-04-11", "gpt-5.4", 1024128)]
    (tmp_path / "s.json").write_text(json.dumps({"session": [
        {"agent": "codex", "period": "2026/04/15/rollout-2026-04-15T08-04-02-019d913d", "metadata": {"lastActivity": "2026-08-16T23:13:01.124Z"},
         "inputTokens": 100, "outputTokens": 10, "cacheCreationTokens": 0, "cacheReadTokens": 0, "totalTokens": 110, "totalCost": 0.1,
         "modelsUsed": ["gpt-5.4"], "modelBreakdowns": [breakdown("gpt-5.4", 100, 10)]},
        {"agent": "claude", "period": "a5e1ee06-fdb4-491f-9878-38d5a3a84f28", "metadata": {}, "inputTokens": 100, "outputTokens": 10,
         "cacheCreationTokens": 0, "cacheReadTokens": 0, "totalTokens": 110, "totalCost": 0.1, "modelsUsed": ["claude-opus-5-5"],
         "modelBreakdowns": [breakdown("claude-opus-5-5", 100, 10)]},
        {"agent": "claude", "period": "2026/05/01/rollout-x", "metadata": {}, "inputTokens": 100, "outputTokens": 10,
         "cacheCreationTokens": 0, "cacheReadTokens": 0, "totalTokens": 110, "totalCost": 0.1, "modelsUsed": ["claude-opus-5-5"],
         "modelBreakdowns": [breakdown("claude-opus-5-5", 100, 10)]}], "totals": {}}))
    got = usage.read(tmp_path / "s.json")
    assert got["source"] == "ccusage session"
    # the day: last activity first, else a date in the session's name, else empty (the tool then uses today)
    assert [(u["session"][:10], u["day"]) for u in got["units"]] == [("2026/04/15", "2026-08-16"), ("a5e1ee06-f", ""), ("2026/05/01", "2026-05-01")]


def test_req_s55_rows_without_a_date_are_priced_today_and_say_so():
    out = tools.price_my_usage(shelf(), mix=[{"model": "claude-opus-5-5", "date": "", "input": 1000, "output": 400}], task="coding")
    assert any("1 of 1 rows carry no date; they are priced at today's prices (2026-10-16)" in n for n in out["notes"])
    assert out["days"] == ["2026-10-16", "2026-10-16"] and out["you_paid"]["cost"] == (1000 * 4 + 400 * 20) / 1e6


def test_req_s55_ccusage_sessions_are_the_units(tmp_path):
    got = usage.read(ccusage_session(tmp_path / "s.json", n=3))
    assert got["source"] == "ccusage session"
    assert [(u["session"], u["day"], u["input"]) for u in got["units"]] == [("s0", "2026-10-01", 1000), ("s1", "2026-10-02", 1100),
                                                                            ("s2", "2026-10-03", 1200)]


def test_req_s55_codeburn_records_are_summed_per_session_and_day_with_the_task(tmp_path):
    got = usage.read(codeburn(tmp_path / "c.json", sessions=2, second_sessions=1))
    assert got["source"] == "codeburn (codeburn.export.v2)"
    a0 = next(u for u in got["units"] if u["session"] == "a0")
    # three calls summed; the supplementary accounting row is left out; the task is coding (two of three calls debugging)
    assert (a0["input"], a0["output"], a0["cache_write"], a0["cache_read"], a0["task"]) == (2100, 900, 300, 15000, "coding")
    b0 = next(u for u in got["units"] if u["session"] == "b0")
    assert b0["task"] == "overall" and b0["output"] == 650          # reasoning tokens count as output
    # the per-model rows give one-shot counts for the Wilson range
    assert got["efficiency"] == {"claude-opus-5-5": {"edit_turns": 40, "one_shot": 30},
                                 "claude-sonnet-5-5": {"edit_turns": 20, "one_shot": 10}}


def test_req_s55_a_plain_mix_and_bad_input(tmp_path):
    got = usage.read([{"model": "claude-opus-5-5", "date": "2026-10-10", "input": 10, "output": 5, "cache_read": 100}])
    assert got["units"][0]["cache_read"] == 100 and got["units"][0]["session"] == "item 1"
    with pytest.raises(usage.BadExport, match="model and a date"):
        usage.read([{"date": "2026-10-10"}])
    with pytest.raises(usage.BadExport, match="No file"):
        usage.read(tmp_path / "missing.json")
    # text before the JSON (npx's "Ok to proceed? (y)" prompt lands in the file) is skipped
    (tmp_path / "npx.json").write_text("Need to install the following packages:\nccusage@20.0.37\nOk to proceed? (y) "
                                      + json.dumps({"daily": [], "totals": {}}))
    assert usage.read(tmp_path / "npx.json")["source"] == "ccusage daily"
    (tmp_path / "x.json").write_text("{not json")
    with pytest.raises(usage.BadExport, match="not JSON"):
        usage.read(tmp_path / "x.json")
    (tmp_path / "y.json").write_text(json.dumps({"hello": 1}))
    with pytest.raises(usage.BadExport, match="Not an export we read"):
        usage.read(tmp_path / "y.json")


# ---------- statistics ----------
def test_req_s55_bootstrap_ranges_and_the_verdict():
    assert usage.bootstrap_mean([1.0, 2.0, 3.0, 4.0]) is None                     # under MIN_SESSIONS
    mean, low, high = usage.bootstrap_mean([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert mean == 3.5 and low < 3.5 < high and 1.0 <= low and high <= 6.0
    same = usage.bootstrap_mean([2.0] * 8)
    assert same == (2.0, 2.0, 2.0)
    d = usage.bootstrap_difference([10.0, 11.0, 9.0, 10.0, 12.0], [1.0, 2.0, 1.0, 2.0, 1.5])
    assert d[1] > 0 and "real difference" in usage.verdict(d[1], d[2], "cost")
    d = usage.bootstrap_difference([1.0, 3.0, 2.0, 1.0, 3.0], [2.0, 1.0, 3.0, 2.0, 1.0])
    assert d[1] <= 0 <= d[2] and "not enough data" in usage.verdict(d[1], d[2], "cost")
    assert usage.bootstrap_difference([1.0] * 5, [1.0] * 4) is None
    assert usage.one_shot({"m": {"edit_turns": 40, "one_shot": 30}}, "m")["rate"] == 0.75
    assert usage.one_shot({}, "m") is None and usage.one_shot({"m": {"edit_turns": 0, "one_shot": 0}}, "m") is None


# ---------- the tool ----------
def mix(n_opus=6, n_sonnet=5, day="2026-10-10"):
    rows = [{"model": "claude-opus-5-5", "date": day, "input": 2000, "output": 800, "cache_read": 20000,
             "cache_write": 3000, "session": f"s{i}"} for i in range(n_opus)]
    rows += [{"model": "claude-sonnet-5-5", "date": day, "input": 2000, "output": 800, "cache_read": 20000,
              "session": f"t{i}"} for i in range(n_sonnet)]
    return rows


def test_req_s55_the_same_work_is_priced_on_every_rated_model_at_each_days_price():
    s = shelf({"claude-sonnet-5-5": [["2026-10-11", "price", "input_cost_per_token", 1e-06, 2e-06, "", 0]]})
    out = tools.price_my_usage(s, mix=mix(day="2026-10-10"), task="coding")
    # opus at its own host: (2000 + 3000 cache write at the input price 4) + 20000 * 0.2 + 800 * 20 = $0.04 a session
    opus = next(r for r in out["you_paid"]["models"] if r["model"] == "anthropic / claude-opus-5.5")
    assert opus["cost"] == 0.24 and opus["sessions"] == 6 and opus["listing"] == "claude-opus-5-5"
    assert opus["per_session"] == {"mean": 0.04, "low": 0.04, "high": 0.04}
    # sonnet on 10 Oct cost $1 input, not today's $2: 2000 * 1 + 20000 * 0.1 + 800 * 10 = $0.012 a session
    sonnet = next(r for r in out["you_paid"]["models"] if r["model"] == "anthropic / claude-sonnet-5.5")
    assert sonnet["cost"] == 0.06 and out["you_paid"]["cost"] == 0.3
    rows = {r["model"]: r for r in out["every_model"]}
    # the whole work (11 sessions) on sonnet at that day's price: 6 * (2000 + 3000 + 2000 + 8000) / 1e6 + 5 * 0.012
    assert rows["anthropic / claude-sonnet-5.5"]["cost"] == 0.15
    assert rows["anthropic / claude-sonnet-5.5"]["versus_yours"] == {"saving": 0.15, "share": 0.5}
    assert rows["anthropic / claude-fable-5.1"]["cost"] > rows["anthropic / claude-opus-5.5"]["cost"] > rows["anthropic / claude-sonnet-5.5"]["cost"]
    assert [r["cost"] for r in out["every_model"]] == sorted(r["cost"] for r in out["every_model"])
    assert out["task"] == "Coding" and out["sessions"] == 11 and out["days"] == ["2026-10-10", "2026-10-10"]
    assert out["tokens"] == {"input": 22000, "output": 8800, "cache_read": 220000, "cache_write": 18000}
    assert "Every model is priced at your token counts" in " ".join(out["notes"])


def test_req_s55_cheaper_models_that_keep_the_rating_and_the_headline():
    s = shelf()
    # for everything (overall), gpt-6.1-sol's rating range reaches opus's low end and costs less than sonnet + opus paid
    out = tools.price_my_usage(s, mix=mix(), task="overall")
    assert [r["model"] for r in out["cheaper_and_as_good"]] == ["openai / gpt-6.1-sol"]
    assert out["headline"].startswith("Your 11 sessions (2026-10-10) on anthropic / claude-opus-5.5 ($0.24, 6 sessions) and "
                                      "anthropic / claude-sonnet-5.5 ($0.07, 5 sessions) cost $0.31 at each day's prices. "
                                      "1 rated model would have done it for less while keeping the rating; the cheapest is "
                                      "openai / gpt-6.1-sol at $0.19, 39% less.")
    # for coding the fixture rates sonnet far below opus, so nothing both cheaper and as good
    out = tools.price_my_usage(s, mix=mix(), task="coding")
    assert out["cheaper_and_as_good"] == [] and "No rated model" in out["headline"]
    sonnet = next(r for r in out["every_model"] if r["model"] == "anthropic / claude-sonnet-5.5")
    assert sonnet["keeps_rating"] is False


def test_req_s55_two_models_for_real_or_not_enough_data():
    s = shelf()
    # the same sessions on two models: a paired difference, real when the prices differ
    out = tools.price_my_usage(s, mix=mix(), task="coding", compare=["claude-opus-5-5", "gpt-6.1-sol"])
    t = out["tests"][0]
    assert t["kind"] == "same work" and t["sessions"] == 11 and t["difference_per_session"]["low"] > 0
    assert "real difference" in t["verdict"] and "same 11 sessions" in t["note"]
    # as used: opus sessions against sonnet sessions, with the caveat that the work differed
    out = tools.price_my_usage(s, mix=mix(), task="coding")
    t = out["tests"][0]
    assert t["kind"] == "as used" and t["sessions"] == [6, 5] and "real difference" in t["verdict"]
    assert "Different sessions" in t["note"] and "one_shot" not in t
    # too few sessions: no range, and the verdict says how many are needed
    out = tools.price_my_usage(s, mix=mix(n_opus=3, n_sonnet=2), task="coding")
    assert out["tests"][0]["difference_per_session"] is None and "5 each needed" in out["tests"][0]["verdict"]
    assert out["you_paid"]["models"][0]["per_session"]["low"] is None


def test_req_s55_a_codeburn_export_brings_one_shot_rates(tmp_path):
    out = tools.price_my_usage(shelf(), export=codeburn(tmp_path / "c.json"))
    assert out["source"].startswith("codeburn") and out["task"] == "Coding"            # most units were coding work
    opus = out["you_paid"]["models"][0]
    assert opus["model"] == "anthropic / claude-opus-5.5" and opus["one_shot"]["rate"] == 0.75
    assert opus["one_shot"]["low"] < 0.75 < opus["one_shot"]["high"] and opus["one_shot"]["edit_turns"] == 40
    t = out["tests"][0]
    assert t["kind"] == "as used" and "not enough data" in t["one_shot"]["verdict"]    # 30/40 and 10/20 overlap
    assert t["one_shot"]["rates"][1]["rate"] == 0.5


def test_req_s55_a_model_listed_after_the_usage_is_priced_at_its_first_price(tmp_path):
    s = shelf({"gpt-6.1-sol": [["2026-09-10", "added", "", None, None, "", 0],
                                ["2026-10-01", "price", "input_cost_per_token", 1e-06, 2e-06, "", 0]]})
    out = tools.price_my_usage(s, mix=mix(day="2026-08-15"), task="overall")
    sol = next(r for r in out["every_model"] if r["model"] == "openai / gpt-6.1-sol")
    assert "Listed since 2026-09-10: 11 of your 11 rows are from before that" in sol["note"]
    # priced at $1 input (the price it was added at), not today's $2
    assert sol["cost"] == 6 * (2000 * 1 + 3000 * 1 + 20000 * 0.1 + 800 * 10) / 1e6 + 5 * (2000 * 1 + 20000 * 0.1 + 800 * 10) / 1e6


def test_req_s55_unknown_models_and_bad_input(tmp_path):
    s = shelf()
    out = tools.price_my_usage(s, mix=mix() + [{"model": "mystery-9000", "date": "2026-10-10", "input": 5, "output": 5}])
    assert any("mystery-9000 (10 tokens)" in n for n in out["notes"])
    with pytest.raises(tools.NotFound, match="None of the models"):
        tools.price_my_usage(s, mix=[{"model": "mystery-9000", "date": "2026-10-10", "input": 5, "output": 5}])
    with pytest.raises(tools.NotFound, match="either export"):
        tools.price_my_usage(s)
    with pytest.raises(tools.NotFound, match="exactly two"):
        tools.price_my_usage(s, mix=mix(), compare=["claude-opus-5-5"])
    with pytest.raises(tools.NotFound, match="Unknown task"):
        tools.price_my_usage(s, mix=mix(), task="juggling")
    with pytest.raises(tools.NotFound, match="Nothing to price"):
        tools.price_my_usage(s, mix=[{"model": "claude-opus-5-5", "date": "2026-10-10", "input": 0, "output": 0}])
    (tmp_path / "empty.json").write_text(json.dumps({"schema": "codeburn.export.v2", "records": [], "periods": []}))
    with pytest.raises(tools.NotFound, match="no records"):
        tools.price_my_usage(s, export=str(tmp_path / "empty.json"))


def test_req_s55_through_the_tool(tmp_path):
    out = call("price_my_usage", export=ccusage_session(tmp_path / "s.json"), task="coding", limit=2)
    assert out["source"] == "ccusage session" and out["sessions"] == 6
    assert len(out["every_model"]) <= 3 and any(r["model"] == "anthropic / claude-opus-5.5" for r in out["every_model"])
    assert out["data"]["prices_as_of"] == "2026-10-16"
    with pytest.raises(ToolError, match="either export"):
        call("price_my_usage")
    with pytest.raises(ToolError, match="No file"):
        call("price_my_usage", export=str(tmp_path / "nope.json"))
