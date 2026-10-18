import json
from collections import Counter
from datetime import datetime

BULK = 50
UNIT = 100
REVERT_DAYS = 30
# D14 likely correction: the rule measured against a labelled sample in docs/corrections (REQ-S37)
FIRST_WEEK = 7
TENFOLD = 10
# What each tag means, for people and programs reading data.json
TEXT = {
    "bulk": "bulk clean up: one of 50 or more models removed on the same day (D10)",
    "unit": "unit fix: a price made 100 times larger or smaller (D11)",
    "reverted": "a price change undone within 30 days, or the change that undid it (D12)",
    "likely": ("likely correction: a price change in the model's first 7 days, from 0, or of 10 times or more "
               "either way (D14); 9 in 10 such first price changes were corrections in a labelled sample"),
}


def _number(text):
    value = json.loads(text)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _unit_fix(old, new):
    if not old or not new:
        return False
    ratio = new / old
    return ratio >= UNIT or ratio <= 1 / UNIT


def tenfold(old, new):
    """From a placeholder 0, or to a number at least 10 times larger or smaller."""
    if not old:
        return True
    ratio = new / old
    return ratio >= TENFOLD or ratio <= 1 / TENFOLD


def likely(old, new, days_in):
    """D14: a price change in the first 7 days after the model was added, or tenfold.
    days_in is None for a model whose time zero is unknown (in the first catalogue version)."""
    return (days_in is not None and days_in <= FIRST_WEEK) or tenfold(old, new)


def _day(row):
    return row["when"][:10]


def mark(rows):
    removed = Counter(_day(row) for row in rows if row["kind"] == "removed")
    for row in rows:
        row["flag"] = ""
        if row["kind"] == "removed" and removed[_day(row)] >= BULK:
            row["flag"] = "bulk"
    day_one = {row["model"] for row in rows if row["kind"] == "start"}
    began = {}
    last = {}
    priced = []
    for row in rows:
        if row["kind"] == "added" and row["model"] not in day_one:
            began.setdefault(row["model"], datetime.fromisoformat(row["when"]))
        if row["kind"] != "price":
            continue
        old, new = _number(row["old"]), _number(row["new"])
        if old is None or new is None:
            continue
        priced.append((row, old, new))
        if _unit_fix(old, new):
            row["flag"] = "unit"
        key = (row["model"], row["field"])
        before = last.get(key)
        if before is not None and _undoes(before, row):
            for each in (before, row):
                if not each["flag"]:
                    each["flag"] = "reverted"
        last[key] = row
    # after every unit fix and revert is known, so a change keeps the stronger tag
    for row, old, new in priced:
        if row["flag"]:
            continue
        start = began.get(row["model"])
        days_in = None if start is None else (
            datetime.fromisoformat(row["when"]) - start).total_seconds() / 86400
        if likely(old, new, days_in):
            row["flag"] = "likely"
    return rows


def _undoes(first, second):
    if _number(first["old"]) != _number(second["new"]):
        return False
    if _number(first["new"]) != _number(second["old"]):
        return False
    gap = (datetime.fromisoformat(second["when"])
           - datetime.fromisoformat(first["when"]))
    return gap.total_seconds() <= REVERT_DAYS * 86400
