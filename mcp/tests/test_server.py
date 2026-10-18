"""Known-answer tests for each tool, through FastMCP's in-memory client (no network)."""
import asyncio
import json
import os
from pathlib import Path

import pytest

os.environ["LLMLEDGER_DATA"] = str(Path(__file__).with_name("fixture.json"))

from fastmcp import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

from llmledger_mcp.server import mcp  # noqa: E402


def call(tool, **args):
    async def go():
        async with Client(mcp) as client:
            return (await client.call_tool(tool, args)).data
    return asyncio.run(go())


def test_the_five_tools_a_resource_and_a_prompt_are_listed():
    async def go():
        async with Client(mcp) as client:
            tools = {t.name: t for t in await client.list_tools()}
            resources = [str(r.uri) for r in await client.list_resources()]
            prompts = [p.name for p in await client.list_prompts()]
            snap = json.loads((await client.read_resource("llmledger://snapshot"))[0].text)
            return tools, resources, prompts, snap
    tools, resources, prompts, snap = asyncio.run(go())
    assert sorted(tools) == ["compare_models", "estimate_cost", "find_models", "price_history", "suggest_for_project"]
    assert all(t.annotations.read_only_hint for t in tools.values())
    assert resources == ["llmledger://snapshot"] and prompts == ["pick_a_model"]
    assert snap["models_listed"] == 6 and snap["rated_tasks"] == {"overall": 4, "coding": 3}
    assert "MIT" in snap["credits"]["prices"]


def test_find_models_ranks_by_rating_and_applies_limits():
    out = call("find_models", task="coding", limit=5)
    assert [m["model"] for m in out["models"]] == [
        "anthropic / claude-fable-5.1", "anthropic / claude-opus-5.5", "anthropic / claude-sonnet-5.5", "openai / gpt-6.1-sol"]
    assert out["models"][1]["listing"] == "claude-opus-5-5"          # the cheapest listing, not bedrock's
    assert out["models"][3]["rating"] is None and out["rated_for_task"] == 3
    cheap = call("find_models", task="overall", max_output_price=15, needs=["vision"])
    assert [m["model"] for m in cheap["models"]] == ["openai / gpt-6.1-sol"]


def test_compare_models_picks_and_explains():
    out = call("compare_models", models=["opus 5.5", "claude-fable-5-1", "claude-sonnet-5.5"], task="coding",
               input_tokens=1000, output_tokens=800)
    assert out["pick"] == "anthropic / claude-opus-5.5"
    assert out["headline"] == ("claude-opus-5.5 is the pick: the votes cannot tell it apart from the highest rated, "
                               "claude-fable-5.1, and it costs less.")
    opus, fable, sonnet = out["models"]
    assert opus["cost_per_task"] == pytest.approx((1000 * 4 + 800 * 20) / 1e6)
    assert fable["versus_pick"] == ("Costs 2.5× as much as claude-opus-5.5; it only costs less if it needs under 40% "
                                    "of the answer tokens.")
    plan = call("compare_models", models=["claude-opus-5.5", "claude-fable-5.1"], task="coding", pay="claude",
                answer_tokens={"claude-fable-5.1": 300})
    # opus: 1,000 in at $4 and 800 out at $20 = $0.020; fable with 300 answer tokens: $0.010 + $0.015 = $0.025
    assert [m["plan_use"] for m in plan["models"]] == [1.0, 1.25]
    assert plan["notes"] and "estimate" in plan["notes"][0]


def test_unknown_names_say_what_is_close():
    with pytest.raises(ToolError, match="Not found: 'claude' \\(did you mean"):
        call("compare_models", models=["claude", "gpt-6.1-sol"])


def test_estimate_cost_per_call_day_and_month_with_cache():
    out = call("estimate_cost", models=["claude-opus-5.5"], input_tokens=10000, output_tokens=1000,
               cached_tokens=8000, calls_per_day=100)
    m = out["models"][0]
    per_call = (2000 * 4 + 8000 * 0.2 + 1000 * 20) / 1e6
    assert m["per_call"] == pytest.approx(per_call) and m["per_30_days"] == pytest.approx(per_call * 3000)
    assert m["cache_priced"] is True


def test_price_history_lists_changes_per_1m_and_the_outlook():
    out = call("price_history", model="claude-opus-5.5")
    bedrock = next(x for x in out["listings"] if x["listing"] == "bedrock/claude-opus-5-5")
    assert bedrock["changes"][1] == {"day": "2026-09-01", "change": "price", "field": "input_cost_per_token",
                                     "before": 5.0, "after": 4.4, "flag": None}
    first = next(x for x in out["listings"] if x["listing"] == "claude-opus-5-5")
    assert first["outlook"]["90"]["price"] == [0.05, 0.04, 0.06]


def test_suggest_for_project_reads_the_prompt():
    out = call("suggest_for_project", prompt="Debug this Python service and refactor the slow parts")
    assert out["task"] == "Coding" and out["why"][:2] == ["debug", "python"]
    best = out["picks"][0]
    assert best["role"] == "best value" and best["model"] == "anthropic / claude-opus-5.5" and best["effort"] == "xhigh"
    plan = call("suggest_for_project", prompt="Write a short poem", pay="chatgpt")
    assert [p["model"] for p in plan["picks"]] == ["openai / gpt-6.1-sol"] and plan["picks"][0]["plan_use"] == 1.0


def test_a_free_listing_is_never_the_price():
    from llmledger_mcp import data, server
    raw = json.loads(Path(__file__).with_name("fixture.json").read_text())
    raw["models"].append(dict(raw["models"][0], key="freehost/claude-opus-5-5", host="freehost",
                              input=0.0, output=0.0, cache_read=None))
    m, cost = server.listing(data.Shelf(raw, "test"), "anthropic / claude-opus-5.5", input_tokens=100, output_tokens=100)
    assert m["host"] == "anthropic" and cost > 0


def test_price_history_explains_its_flags_and_says_corrections_are_counted(monkeypatch):
    from llmledger_mcp import data, server
    raw = json.loads(Path(__file__).with_name("fixture.json").read_text())
    raw["events"]["bedrock/claude-opus-5-5"].append(["2026-09-03", "price", "output_cost_per_token", 2.5e-05, 2.5e-06, "likely"])
    monkeypatch.setattr(server, "_SHELF", data.Shelf(raw, "test"))     # data older than the tag text: built-in meanings
    out = call("price_history", model="bedrock/claude-opus-5-5")
    assert list(out["flags"]) == ["likely"] and "first 7 days" in out["flags"]["likely"]
    assert not any("labelled sample, " in n for n in out["notes"])     # no measured shares in this data
    raw["units"] = {"flags": {"likely": "likely correction (from the data)"}}
    raw["corrections"] = {"first_week": {"share": 0.856}, "later": {"share": 0.514}}
    monkeypatch.setattr(server, "_SHELF", data.Shelf(raw, "test"))
    out = call("price_history", model="bedrock/claude-opus-5-5")
    assert out["flags"] == {"likely": "likely correction (from the data)"}
    assert any("86% of first price changes in a model's first week and 51% of later ones" in n for n in out["notes"])


def test_old_data_says_how_old_it_is():
    from datetime import datetime, timezone

    from llmledger_mcp import data, server
    now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    assert server.age_days("2026-10-16T12:00:00+00:00", now) == 4
    assert server.age_days("2026-10-18T13:00:00+00:00", now) == 1
    assert server.age_days(None, now) is None and server.age_days("not a date", now) is None
    assert server.age_days("2026-10-16T12:00:00", now) is None          # no time zone: unknown, not a crash
    raw = json.loads(Path(__file__).with_name("fixture.json").read_text())
    fresh = server.footer(data.Shelf(dict(raw, built=datetime.now(timezone.utc).isoformat()), "test"))
    assert "warning" not in fresh["data"]
    old = server.footer(data.Shelf(dict(raw, built="2026-01-01T00:00:00+00:00"), "test"))
    assert old["data"]["warning"].startswith("This data is ") and "days old" in old["data"]["warning"]
