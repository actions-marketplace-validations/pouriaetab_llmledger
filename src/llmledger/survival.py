import csv
import json
import random
import statistics
from bisect import bisect_left
from datetime import datetime

from llmledger import flags

EXITS = ("price", "retirement", "removed")
OUTCOMES = EXITS + ("none",)
TIE_ORDER = {"cleanup": 0, "removed": 0, "retirement": 1, "price": 2}
HEADLINE = {"input_cost_per_token", "output_cost_per_token"}
DEFINITIONS = ("main", "headline", "no_first_week", "real_only", "likely_real")
# The tags each definition leaves out (D11 unit fix, D12 reverted, D14 likely correction); both also
# censor a model removed in a bulk clean up (D10) on that day.
LEFT_OUT = {"real_only": ("unit", "reverted"), "likely_real": ("unit", "reverted", "likely")}
DAYS = (30, 90, 180, 365, 730)

def _is_number(value):
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float))


def _exit_kind(row, definition, days_in):
    left_out = LEFT_OUT.get(definition, ())
    flag = row.get("flag", "") if left_out else ""
    if flag in left_out:
        return None
    if row["kind"] == "removed":
        return "cleanup" if flag == "bulk" else "removed"
    if row["kind"] == "deprecation":
        if row["old"] == "null" and row["new"] != "null":
            return "retirement"
        return None
    if row["kind"] != "price":
        return None
    old = json.loads(row["old"])
    new = json.loads(row["new"])
    if not (_is_number(old) and _is_number(new)):
        return None
    if definition == "headline" and row["field"] not in HEADLINE:
        return None
    if definition == "no_first_week" and days_in <= 7:
        return None
    return "price"


def subject_table(rows, definition="main", end=None):
    if end is None:
        end = max(datetime.fromisoformat(row["when"]) for row in rows)
    day_one = {
        row["model"] for row in rows if row["kind"] == "start"
    }
    began = {}
    first_exit = {}
    for row in rows:
        model = row["model"]
        if model in day_one:
            continue
        when = datetime.fromisoformat(row["when"])
        if row["kind"] == "added":
            began.setdefault(model, when)
            continue
        if model not in began:
            continue
        days_in = (when - began[model]).total_seconds() / 86400
        kind = _exit_kind(row, definition, days_in)
        if kind is None:
            continue
        best = first_exit.get(model)
        if best is None or (when, TIE_ORDER[kind]) < (
            best[0], TIE_ORDER[best[1]]
        ):
            first_exit[model] = (when, kind)
    table = {}
    for model, start in began.items():
        if model in first_exit:
            when, kind = first_exit[model]
        else:
            when, kind = end, "censored"
        if kind == "cleanup":
            kind = "censored"
        table[model] = (start, when, kind)
    return table


def subjects(rows, definition="main", end=None):
    return [
        ((when - start).total_seconds() / 86400, kind)
        for start, when, kind in subject_table(rows, definition, end).values()
    ]


def cumulative_incidence(subjects, days, min_at_risk=100):
    ordered = sorted(subjects)
    times = [time for time, _ in ordered]
    n = len(ordered)
    survival = 1.0
    incidence = {cause: 0.0 for cause in EXITS}
    report = {}
    i = 0
    for day in sorted(days):
        while i < n and times[i] <= day:
            now = times[i]
            at_risk = n - i
            leaving = {cause: 0 for cause in EXITS}
            while i < n and times[i] == now:
                kind = ordered[i][1]
                if kind in leaving:
                    leaving[kind] += 1
                i += 1
            for cause in EXITS:
                share = leaving[cause] / at_risk
                incidence[cause] += survival * share
            survival *= 1 - sum(leaving.values()) / at_risk
        still_watched = n - bisect_left(times, day)
        if still_watched >= min_at_risk:
            row = dict(incidence)
            row["none"] = survival
            report[day] = (still_watched, row)
    return report

def bootstrap(subjects, days, min_at_risk=100,
              resamples=1000, seed=20261001):
    rng = random.Random(seed)
    draws = {}
    for _ in range(resamples):
        sample = rng.choices(subjects, k=len(subjects))
        report = cumulative_incidence(sample, days, min_at_risk)
        for day, (_, row) in report.items():
            for outcome, value in row.items():
                draws.setdefault((day, outcome), []).append(value)
    intervals = {}
    for key, values in draws.items():
        cuts = statistics.quantiles(values, n=40)
        intervals[key] = (cuts[0], cuts[-1])
    return intervals

def main(source="data/events.csv", out="data/survival.csv"):
    with open(source, newline="") as f:
        rows = flags.mark(list(csv.DictReader(f)))
    header = ["definition", "days", "outcome", "estimate",
              "ci_low", "ci_high", "at_risk"]
    sizes = {}
    with open(out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for definition in DEFINITIONS:
            group = subjects(rows, definition)
            sizes[definition] = len(group)
            report = cumulative_incidence(group, DAYS)
            intervals = bootstrap(group, DAYS)
            print(f"\n{definition}: {len(group)} models")
            for day, (at_risk, row) in report.items():
                assert abs(sum(row.values()) - 1) < 1e-9
                line = []
                for outcome in OUTCOMES:
                    low, high = intervals[(day, outcome)]
                    writer.writerow([
                        definition, day, outcome,
                        round(row[outcome], 6),
                        round(low, 6), round(high, 6), at_risk,
                    ])
                    line.append(f"{outcome} {row[outcome]:.1%}")
                print(f"  {day:>4} days  " + "  ".join(line))
    return sizes


if __name__ == "__main__":
    main()
