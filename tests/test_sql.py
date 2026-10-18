from datetime import datetime, timedelta, timezone

import pytest

from llmledger import sql
from llmledger.survival import DEFINITIONS

DAY_ZERO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def row(day, model, kind, field="", old="null", new="null"):
    return {
        "when": (DAY_ZERO + timedelta(days=day)).isoformat(),
        "sha": f"v{day}", "model": model, "kind": kind,
        "field": field, "old": old, "new": new,
    }


def price(day, model, old, new):
    return row(day, model, "price", "input_cost_per_token", old, new)

# Each model tests one rule, so a wrong rule shows up as one wrong model.
ROWS = [
    row(0, "day-one", "start"),
    row(0, "a", "added"),
    price(4, "a", "1e-06", "2e-06"),
    row(0, "tie", "added"),
    price(6, "tie", "1e-06", "2e-06"),
    row(6, "tie", "removed"),
    row(0, "both", "added"),
    price(5, "both", "1e-06", "2e-06"),
    row(5, "both", "deprecation", "deprecation_date", "null", '"2027-01-01"'),
    row(0, "week", "added"),
    price(8, "week", "1e-06", "2e-06"),
    row(0, "retired", "added"),
    row(9, "retired", "deprecation", "deprecation_date", "null", '"2027-01-01"'),
    row(0, "new-field", "added"),
    row(3, "new-field", "price", "input_cost_per_token", "null", "1e-06"),
    row(0, "cache", "added"),
    row(20, "cache", "price", "cache_read_input_token_cost", "1e-07", "2e-07"),
    row(0, "unit", "added"),
    price(12, "unit", "1.5e-07", "1.5e-05"),
    row(0, "down", "added"),
    price(12, "down", "3e-07", "3e-09"),
    row(0, "jump", "added"),
    price(5, "jump", "1e-06", "2e-06"),
    price(10, "jump", "2e-06", "4e-06"),
    row(0, "fix-then-jump", "added"),
    price(5, "fix-then-jump", "1e-08", "1e-06"),
    price(10, "fix-then-jump", "5e-07", "1e-08"),
    row(0, "fix-then-step", "added"),
    price(5, "fix-then-step", "1e-08", "1e-06"),
    price(10, "fix-then-step", "1e-06", "2e-06"),
    row(0, "back", "added"),
    price(5, "back", "1e-06", "2e-06"),
    price(10, "back", "3e-06", "1e-06"),
    row(0, "flip-flop", "added"),
    price(1, "flip-flop", "1e-06", "2e-06"),
    price(5, "flip-flop", "2e-06", "1e-06"),
    price(38, "flip-flop", "1e-06", "2e-06"),
    row(0, "late-undo", "added"),
    price(2, "late-undo", "1e-06", "2e-06"),
    price(36, "late-undo", "2e-06", "1e-06"),
    row(0, "moved", "added"),
    row(3, "moved", "deprecation", "deprecation_date", '"2027-01-01"', '"2027-06-01"'),
    row(0, "undone", "added"),
    price(5, "undone", "1e-06", "2e-06"),
    price(35, "undone", "2e-06", "1e-06"),
    row(0, "bulk", "added"),
    *[row(15, name, "removed") for name in ["bulk"] + [f"x{i}" for i in range(49)]],
    row(0, "ten", "added"),
    price(20, "ten", "1e-06", "1e-05"),
    row(0, "nine", "added"),
    price(20, "nine", "1e-06", "9e-06"),
    row(0, "zero", "added"),
    price(20, "zero", "0", "1e-06"),
    row(30, "late", "added"),
    row(40, "end", "added"),
]


@pytest.mark.parametrize("definition", DEFINITIONS)
def test_req_s22_sql_and_python_agree(definition):
    rows = [dict(r) for r in ROWS]
    sql.check(rows)
    ours = sql.sql_table(sql.load(rows), definition)
    assert ours == sql.python_table(rows, definition)
    assert "day-one" not in ours and len(ours) == 23


def test_req_s22_sql_known_answer():
    rows = [dict(r) for r in ROWS]
    main = sql.sql_table(sql.load(rows), "main")
    real = sql.sql_table(sql.load(rows), "real_only")
    assert main["a"] == (4.0, "price")
    assert main["tie"] == (6.0, "removed")
    assert main["both"] == (5.0, "retirement")
    week = sql.sql_table(sql.load(rows), "no_first_week")
    assert week["week"] == (8.0, "price") and week["a"] == (40.0, "censored")
    assert main["retired"] == (9.0, "retirement")
    assert main["new-field"] == (40.0, "censored")
    assert main["bulk"] == (15.0, "removed")
    assert real["bulk"] == (15.0, "censored")
    assert main["unit"] == (12.0, "price") and main["undone"] == (5.0, "price")
    assert real["unit"] == real["down"] == real["undone"] == (40.0, "censored")
    assert real["jump"] == (5.0, "price")
    assert real["fix-then-jump"] == real["fix-then-step"] == (10.0, "price")
    assert real["back"] == (5.0, "price")
    assert real["flip-flop"] == (38.0, "price")
    assert real["late-undo"] == (2.0, "price")
    assert main["moved"] == (40.0, "censored")
    assert main["late"] == (10.0, "censored")
    likely = sql.sql_table(sql.load(rows), "likely_real")
    assert main["a"] == (4.0, "price") and likely["a"] == (40.0, "censored")      # first week
    assert likely["week"] == (8.0, "price")
    assert likely["jump"] == (10.0, "price")                                       # the next change counts
    assert main["ten"] == main["zero"] == (20.0, "price")
    assert likely["ten"] == likely["zero"] == (40.0, "censored")                   # 10 times, and from 0
    assert likely["nine"] == (20.0, "price")
    assert likely["unit"] == likely["undone"] == (40.0, "censored")                # tags left out as in real_only
    assert likely["bulk"] == (15.0, "censored")


def test_req_s22_a_disagreement_stops_the_check(monkeypatch):
    rows = [dict(r) for r in ROWS]
    wrong = sql.python_table(rows, "main") | {"a": (4.0, "removed")}
    monkeypatch.setattr(sql, "python_table", lambda rows, definition: wrong)
    with pytest.raises(AssertionError, match="disagree on 1 models"):
        sql.check(rows)
