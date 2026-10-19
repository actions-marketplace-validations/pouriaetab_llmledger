"""Local or cloud: buy a computer for an open model, or pay a cloud model per call (local_or_cloud)."""
import asyncio
import os
from pathlib import Path

import pytest

os.environ["LLMLEDGER_DATA"] = str(Path(__file__).with_name("fixture.json"))

from fastmcp import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

from llmledger_mcp.server import mcp  # noqa: E402

JOB = dict(local_model="llama3.1:8b", cloud_models=["claude-opus-5.5", "gpt-6.1-sol"], input_tokens=2000,
           output_tokens=500, calls_per_month=30000, hardware_price=2000)
SOL = (2000 * 2 + 500 * 10) / 1e6 * 30000                         # gpt-6.1-sol: $270 a month


def call(tool, **args):
    async def go():
        async with Client(mcp) as client:
            return (await client.call_tool(tool, args)).data
    return asyncio.run(go())


def log_local_runs():
    for out in (100, 300, 500, 700, 900):                          # 1 s to start and 0.02 s an answer token
        call("log_run", model="llama3.1:8b", input_tokens=2000, output_tokens=out, seconds=1 + out / 50, way="ollama")


def test_req_s48_before_any_local_run_it_says_what_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    out = call("local_or_cloud", **JOB)
    sol, opus = out["cloud"]                                          # cheapest first
    assert sol["model"] == "openai / gpt-6.1-sol" and sol["per_month"] == pytest.approx(SOL)
    assert sol["buying_pays_off_after_months"] == {"before_electricity": round(2000 / SOL, 1)}
    assert opus["price_change_90_days"] == {"listing": "claude-opus-5-5", "share": 0.05, "low": 0.04, "high": 0.06}
    assert out["local"]["runs_used"] == 0 and len(out["local"]["missing"]) == 2
    assert out["headline"] == ("Against gpt-6.1-sol at $270.00 a month, the computer pays for itself after 7.4 months "
                               "at the earliest; electricity is not counted yet, for that give timed runs of "
                               "llama3.1:8b (log_run) and watts (the power the computer draws while it answers: its "
                               "spec sheet or a plug-in power meter).")
    assert out["local"]["electricity_per_kwh"] == 0.1831 and "U.S. Energy Information Administration" in \
        out["local"]["electricity_from"]


def test_req_s48_with_runs_watts_and_a_state_it_counts_electricity(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    log_local_runs()
    out = call("local_or_cloud", **JOB, watts=150, state="texas")
    local = out["local"]
    assert local["per_call_seconds"]["usual"] == pytest.approx(11.0) and local["keeps_up"] is True
    hours = 30000 * 11 / 3600
    power = hours * 150 / 1000 * 0.1588
    assert local["hours_of_work_a_month"]["usual"] == round(hours, 1)
    assert local["electricity_a_month"]["usual"] == pytest.approx(power, rel=1e-4)
    assert local["electricity_from"].startswith("Texas homes, July 2026.")
    sol = out["cloud"][0]
    assert sol["buying_pays_off_after_months"]["usual"] == round(2000 / (SOL - power), 1)
    assert sol["saving_over_months"] == pytest.approx(SOL * 36 - (2000 + power * 36), rel=1e-4)
    assert out["headline"].startswith("Against gpt-6.1-sol at $270.00 a month, the computer pays for itself after "
                                      "about 7.5 months")
    out = call("local_or_cloud", **{**JOB, "calls_per_month": 300000}, watts=150, electricity_price=0.30)
    assert out["local"]["keeps_up"] is False and "cannot keep up" in out["headline"]
    assert out["local"]["electricity_from"] == "the price you gave"


def test_req_s48_when_home_power_costs_more_buying_never_pays_off(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    log_local_runs()
    out = call("local_or_cloud", **{**JOB, "input_tokens": 10, "output_tokens": 500, "calls_per_month": 100},
               watts=1000, electricity_price=50.0)
    assert out["cloud"][0]["buying_pays_off_after_months"]["usual"] is None
    assert out["headline"].startswith("Running it at home costs more each month than gpt-6.1-sol")


def test_req_s48_bad_input_says_what_to_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("LLMLEDGER_RUNS", str(tmp_path / "runs.jsonl"))
    with pytest.raises(ToolError, match="Unknown state"):
        call("local_or_cloud", **JOB, state="Atlantis")
    with pytest.raises(ToolError):
        call("local_or_cloud", **{**JOB, "cloud_models": ["gpt-6.1-sol"] * 6})
    with pytest.raises(ToolError):
        call("local_or_cloud", **JOB, watts=0)
    with pytest.raises(ToolError, match="Not found"):
        call("local_or_cloud", **{**JOB, "cloud_models": ["no-such-model"]})
