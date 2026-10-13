import json
from collections import defaultdict
from datetime import datetime, timedelta

from llmledger import outlook, survival
from llmledger.names import canonical

MIN_GROUP = 200
TOKEN_PRICES = ("input_cost_per_token", "output_cost_per_token")


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _per_million(entry, field):
    value = _number(entry.get(field))
    return None if value is None else round(value * 1_000_000, 6)


def _day(text):
    return text[:10]


def _rounded(cells, at_risk, start):
    row = [start, at_risk]
    for outcome in survival.OUTCOMES:
        row.extend(round(value, 4) for value in cells[outcome])
    return row


def _curves(rows, end, resamples):
    result = outlook.outlook(survival.subjects(rows, "main", end),
                             resamples=resamples)
    curves = {str(h): [] for h in outlook.HORIZONS}
    for (horizon, start), (cells, at_risk) in sorted(result.items()):
        curves[str(horizon)].append(_rounded(cells, at_risk, start))
    return curves


def _ranking(rows, end):
    group = survival.subjects(rows, "main", end)
    report = survival.cumulative_incidence(group, [365])
    if 365 not in report:
        return None
    at_risk, row = report[365]
    intervals = survival.bootstrap(group, [365])
    cells = [len(group), at_risk]
    for outcome in survival.EXITS:
        low, high = intervals[(365, outcome)]
        cells.extend(round(v, 4) for v in (row[outcome], low, high))
    return cells


def model_records(rows, last, end):
    table = survival.subject_table(rows, "main", end)
    by_model = defaultdict(list)
    for row in rows:
        by_model[row["model"]].append(row)
    records = []
    events = {}
    for key in sorted(by_model):
        history = by_model[key]
        entry = last.get(key, {})
        maker, name = canonical(key)
        kinds = [row["kind"] for row in history]
        listed = kinds[-1] != "removed"
        added = "" if kinds[0] == "start" else _day(history[0]["when"])
        removed = "" if listed else _day(history[-1]["when"])
        repriced = [
            row for row in history if row["kind"] == "price"
            and _number(json.loads(row["old"])) is not None
            and _number(json.loads(row["new"])) is not None
        ]
        age = None
        first_exit = ""
        if key in table:
            start, when, kind = table[key]
            first_exit = "" if kind == "censored" else kind
            if kind == "censored" and listed:
                age = round((end - start).total_seconds() / 86400, 1)
        records.append([
            key, maker, name, entry.get("litellm_provider", ""),
            entry.get("mode", ""), "listed" if listed else "removed",
            added, removed, entry.get("deprecation_date", ""),
            _per_million(entry, TOKEN_PRICES[0]),
            _per_million(entry, TOKEN_PRICES[1]),
            len(repriced), _day(history[-1]["when"]), first_exit, age,
        ])
        events[key] = [
            [_day(row["when"]), row["kind"], row["field"],
             json.loads(row["old"]), json.loads(row["new"])]
            for row in history
        ]
    return records, events


def build(rows, last, end, resamples=1000):
    records, events = model_records(rows, last, end)
    groups = {"all": rows}
    members = defaultdict(set)
    for record in records:
        members[record[3]].add(record[0])
    for name, keys in members.items():
        subset = [row for row in rows if row["model"] in keys]
        added = sum(1 for row in subset if row["kind"] == "added")
        if name and added >= MIN_GROUP:
            groups[name] = subset
    curves = {name: _curves(subset, end, resamples)
              for name, subset in groups.items()}
    ranking = []
    for name, subset in groups.items():
        if name == "all":
            continue
        cells = _ranking(subset, end)
        if cells is not None:
            ranking.append([name, *cells])
    return {
        "end": end.isoformat(),
        "models": records,
        "events": events,
        "curves": curves,
        "providers": ranking,
        "groups": sorted(name for name in groups if name != "all"),
        "recent": recent(rows, end),
    }


def end_of(rows):
    return max(datetime.fromisoformat(row["when"]) for row in rows)


def recent(rows, end, days=7):
    cutoff = end - timedelta(days=days)
    kinds = {"added", "removed", "price", "deprecation"}
    return [
        [_day(row["when"]), row["model"], row["kind"], row["field"],
         json.loads(row["old"]), json.loads(row["new"])]
        for row in rows
        if row["kind"] in kinds
        and datetime.fromisoformat(row["when"]) > cutoff
    ]
