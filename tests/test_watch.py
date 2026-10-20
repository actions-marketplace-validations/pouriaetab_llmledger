import importlib.util
import json
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("watch", Path(__file__).parent.parent / "action" / "watch.py")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


def machine():
    return {
        "built": "2026-10-20T11:50:44+00:00",
        "models": [
            {"key": "openai/gpt-5", "retire": None, "outlook": {"90": {"price": [0.045, 0.03, 0.06]}}},
            {"key": "host/going", "retire": "2026-12-01", "outlook": None},
            {"key": "host/quiet", "retire": None, "outlook": None},
        ],
        "events": {
            "openai/gpt-5": [["2026-10-18", "price", "input_cost_per_token", 1.25e-06, 1e-06, "", 0],
                             ["2026-09-01", "price", "output_cost_per_token", 1e-05, 8e-06, "", 0]],
            "host/going": [], "host/quiet": [],
        },
    }


def test_req_s51_each_watched_model_is_checked_for_the_three_changes():
    rows = watch.check(machine(), ["openai/gpt-5", "host/going", "host/quiet", "host/gone"], days=7)
    gpt, going, quiet, gone = rows
    assert gpt["price_changes"] == [{"day": "2026-10-18", "field": "input", "old": "$1.25",
                                     "new": "$1.00", "flag": ""}] and gpt["chance_90d"] == 4.5
    assert going["retire"] == "2026-12-01" and not going["price_changes"]
    assert not quiet["price_changes"] and quiet["retire"] is None
    assert not gone["listed"] and "not listed" in gone["note"]


def test_req_s51_a_key_without_litellms_prefix_is_found_and_batch_prices_do_not_count():
    m = machine()
    m["events"]["openai/gpt-5"].append(["2026-10-19", "price", "input_cost_per_token_batches", None, 5e-07, "", 0])
    rows = watch.check(m, ["gpt-5", "openai/gpt-5"], days=7)
    assert rows[0]["listed"] and rows[0]["key"] == "gpt-5 (listed as openai/gpt-5)" and rows[1]["key"] == "openai/gpt-5"
    assert [c["field"] for c in rows[1]["price_changes"]] == ["input"]
    assert [c["field"] for c in watch.check(m, ["openai/gpt-5"], days=7, fields="all")[0]["price_changes"]] == \
        ["input", "input_cost_per_token_batches"]
    # two hosts list the same tail: no guess; a prefix LiteLLM does not use falls back to the bare key
    m["models"].append({"key": "azure/gpt-5", "retire": None, "outlook": None})
    listed = {x["key"]: x for x in m["models"]}
    assert watch.resolve("gpt-5", listed) == ("gpt-5", None)
    listed["gpt-5"] = {"key": "gpt-5"}
    assert watch.resolve("acme/gpt-5", listed)[0] == "gpt-5"


def test_req_s51_the_report_names_the_changes_and_says_when_nothing_changed():
    rows = watch.check(machine(), ["openai/gpt-5", "host/quiet"], days=7)
    text, flagged = watch.report(rows, 7)
    assert flagged and text.startswith("1 of 2 watched models changed")
    assert "- openai/gpt-5: 2026-10-18 input $1.25 -> $1.00 per 1M (4.5% chance" in text
    assert "- host/quiet: no change in the last 7 days" in text
    text, flagged = watch.report(watch.check(machine(), ["host/quiet"]), 7)
    assert not flagged and text.startswith("No change in the 1 watched models")
    # only the kinds asked for count
    _, flagged = watch.report(watch.check(machine(), ["openai/gpt-5"]), 7, watch=("retirement",))
    assert not flagged


def test_req_s51_the_script_exits_1_on_a_change_0_otherwise_2_without_data(tmp_path, capsys):
    data = tmp_path / "data.json"
    data.write_text(json.dumps(machine()))
    assert watch.main(["--models", "openai/gpt-5", "--data", str(data)]) == 1
    assert watch.main(["--models", "host/quiet", "--data", str(data)]) == 0
    assert watch.main(["--models", "openai/gpt-5", "--data", str(tmp_path / "missing.json")]) == 2
    assert "could not read" in capsys.readouterr().out


def test_req_s51_the_action_runs_the_script_with_its_inputs():
    text = (Path(__file__).parent.parent / "action.yml").read_text()
    for needle in ('using: "composite"', "action/watch.py", "inputs.models", "inputs.days", "inputs.watch",
                   "inputs.fail", "outputs:", "changed:", "report:"):
        assert needle in text
