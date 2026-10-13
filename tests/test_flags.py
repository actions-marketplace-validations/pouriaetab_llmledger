from datetime import datetime, timedelta, timezone

from llmledger.flags import mark
from llmledger.survival import subjects

DAY_ZERO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def row(day, model, kind, field="", old="null", new="null", sha=None):
    return {
        "when": (DAY_ZERO + timedelta(days=day)).isoformat(),
        "sha": sha or f"v{day}", "model": model, "kind": kind,
        "field": field, "old": old, "new": new,
    }


def price(day, model, old, new):
    return row(day, model, "price", "input_cost_per_token", old, new)


def test_req_s20_bulk_clean_up_starts_at_50_removals_in_a_day():
    fifty = [row(9, f"m{i}", "removed", sha=f"v{i % 3}") for i in range(50)]
    forty_nine = [row(10, f"n{i}", "removed") for i in range(49)]
    rows = mark(fifty + forty_nine)
    assert {r["flag"] for r in rows[:50]} == {"bulk"}
    assert {r["flag"] for r in rows[50:]} == {""}


def test_req_s20_unit_fix_is_100_times_either_way():
    rows = mark([
        price(1, "up", "1e-06", "0.0001"),
        price(1, "down", "0.0001", "1e-06"),
        price(1, "big", "1e-06", "5e-05"),
        price(1, "new", "null", "1e-06"),
    ])
    assert [r["flag"] for r in rows] == ["unit", "unit", "", ""]


def test_req_s20_a_change_undone_within_30_days_is_reverted():
    rows = mark([
        price(1, "a", "1e-06", "2e-06"),
        price(31, "a", "2e-06", "1e-06"),
        price(1, "b", "1e-06", "2e-06"),
        price(32, "b", "2e-06", "1e-06"),
        price(1, "c", "1e-06", "2e-06"),
        price(5, "c", "2e-06", "3e-06"),
    ])
    assert [r["flag"] for r in rows] == ["reverted", "reverted", "", "", "", ""]


def test_req_s21_real_changes_only():
    rows = mark([
        row(0, "bulk", "added"),
        row(10, "bulk", "removed", sha="big"),
        *[row(10, f"x{i}", "removed", sha="big") for i in range(49)],
        row(0, "fix", "added"),
        price(5, "fix", "1e-06", "0.0001"),
        row(0, "real", "added"),
        price(20, "real", "1e-06", "2e-06"),
        row(30, "end", "added"),
    ])
    assert subjects(rows, "main") == [
        (10.0, "removed"), (5.0, "price"), (20.0, "price"), (0.0, "censored"),
    ]
    assert subjects(rows, "real_only") == [
        (10.0, "censored"), (30.0, "censored"), (20.0, "price"),
        (0.0, "censored"),
    ]
