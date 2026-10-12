import json

from llmledger.events import _diff


def kinds(rows):
    return [(r["model"], r["kind"], r["field"]) for r in rows]


def test_added_and_removed_models():
    before = {"a": {"mode": "chat"}}
    after = {"b": {"mode": "chat"}}
    rows = _diff("t", "sha", before, after)
    assert kinds(rows) == [
        ("b", "added", ""),
        ("a", "removed", ""),
    ]


def test_same_number_written_differently_is_not_a_change():
    before = {"m": {"input_cost_per_token": 1e-06}}
    after = {"m": {"input_cost_per_token": 0.000001}}
    assert _diff("t", "sha", before, after) == []


def test_price_change_keeps_old_and_new_values():
    before = {"m": {"input_cost_per_token": 5e-06}}
    after = {"m": {"input_cost_per_token": 2.5e-06}}
    [change] = _diff("t", "sha", before, after)
    assert change["kind"] == "price"
    assert json.loads(change["old"]) == 5e-06
    assert json.loads(change["new"]) == 2.5e-06


def test_retirement_date_is_recorded():
    before = {"m": {}}
    after = {"m": {"deprecation_date": "2026-12-01"}}
    [change] = _diff("t", "sha", before, after)
    assert change["kind"] == "deprecation"
    assert change["new"] == '"2026-12-01"'


def test_other_fields_are_ignored():
    before = {"m": {"supports_vision": False}}
    after = {"m": {"supports_vision": True}}
    assert _diff("t", "sha", before, after) == []


def test_a_rename_is_one_removal_and_one_addition():
    before = {"replicateopenai/x": {}}
    after = {"replicate/openai/x": {}}
    rows = _diff("t", "sha", before, after)
    assert kinds(rows) == [
        ("replicate/openai/x", "added", ""),
        ("replicateopenai/x", "removed", ""),
    ]