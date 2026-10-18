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
    assert [r["flag"] for r in rows] == ["unit", "unit", "likely", ""]   # 50 times is a likely correction (D14)


def test_req_s20_likely_correction_is_the_first_week_or_ten_times():
    rows = mark([
        row(0, "early", "added"), price(7, "early", "1e-06", "2e-06"),       # day 7: still the first week
        row(0, "later", "added"), price(8, "later", "1e-06", "2e-06"),       # day 8: not
        row(0, "ten", "added"), price(30, "ten", "1e-06", "1e-05"),          # 10 times up
        row(0, "tenth", "added"), price(30, "tenth", "1e-06", "1e-07"),      # 10 times down
        row(0, "nine", "added"), price(30, "nine", "1e-06", "9e-06"),        # 9 times: not
        row(0, "zero", "added"), price(30, "zero", "0", "1e-06"),            # from a placeholder 0
        row(0, "free", "added"), price(30, "free", "1e-06", "0"),            # to 0
        row(0, "unit", "added"), price(2, "unit", "1e-06", "0.0001"),        # a unit fix keeps its own tag
        row(0, "back", "added"), price(3, "back", "1e-06", "2e-06"), price(9, "back", "2e-06", "1e-06"),
        price(30, "old", "1e-06", "2e-06"),                                  # time zero unknown: only the size counts
        price(30, "old", "2e-06", "4e-05"),
    ])
    flagged = [(r["model"], r["flag"]) for r in rows if r["kind"] == "price"]
    assert flagged == [("early", "likely"), ("later", ""), ("ten", "likely"), ("tenth", "likely"), ("nine", ""),
                       ("zero", "likely"), ("free", "likely"), ("unit", "unit"), ("back", "reverted"),
                       ("back", "reverted"), ("old", ""), ("old", "likely")]


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


def test_req_s21_leaving_out_likely_corrections_as_well():
    rows = mark([
        row(0, "early", "added"),
        price(3, "early", "1e-06", "2e-06"),       # first week: left out
        price(40, "early", "2e-06", "3e-06"),      # the next change counts
        row(0, "ten", "added"),
        price(20, "ten", "1e-06", "1e-05"),        # 10 times: left out, and nothing after it
        row(0, "real", "added"),
        price(20, "real", "1e-06", "2e-06"),
        row(50, "end", "added"),
    ])
    assert subjects(rows, "real_only") == [(3.0, "price"), (20.0, "price"), (20.0, "price"), (0.0, "censored")]
    assert subjects(rows, "likely_real") == [(40.0, "price"), (50.0, "censored"), (20.0, "price"), (0.0, "censored")]

