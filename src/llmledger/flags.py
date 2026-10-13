import json
from collections import Counter
from datetime import datetime

BULK = 50
UNIT = 100
REVERT_DAYS = 30


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


def _day(row):
    return row["when"][:10]


def mark(rows):
    removed = Counter(_day(row) for row in rows if row["kind"] == "removed")
    for row in rows:
        row["flag"] = ""
        if row["kind"] == "removed" and removed[_day(row)] >= BULK:
            row["flag"] = "bulk"
    last = {}
    for row in rows:
        if row["kind"] != "price":
            continue
        old, new = _number(row["old"]), _number(row["new"])
        if old is None or new is None:
            continue
        if _unit_fix(old, new):
            row["flag"] = "unit"
        key = (row["model"], row["field"])
        before = last.get(key)
        if before is not None and _undoes(before, row):
            for each in (before, row):
                if not each["flag"]:
                    each["flag"] = "reverted"
        last[key] = row
    return rows


def _undoes(first, second):
    if _number(first["old"]) != _number(second["new"]):
        return False
    if _number(first["new"]) != _number(second["old"]):
        return False
    gap = (datetime.fromisoformat(second["when"])
           - datetime.fromisoformat(first["when"]))
    return gap.total_seconds() <= REVERT_DAYS * 86400
