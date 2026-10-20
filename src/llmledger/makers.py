"""Competing risks by maker: which makers' models get repriced, retired or removed first.

The same subjects as the main result (REQ-S5 to S8), split by the maker that the naming
rules give each model (REQ-S18). For every maker with at least MIN_SUBJECTS models, the
Aalen-Johansen cumulative incidence of each first exit within a year, with a 95% bootstrap
interval; makers with fewer models are pooled as "other makers". The main result is the
reference row. Written to data["makers"] and shown on the Price history view.
"""
import statistics
from datetime import datetime

from llmledger import names, survival

MIN_SUBJECTS = 100
DAY = 365
RESAMPLES = 1000
SEED = 20261020


def subjects_by_maker(rows, definition="main", end=None):
    """{maker: [(days, kind), ...]} from the subject table, makers below MIN_SUBJECTS pooled."""
    table = survival.subject_table(rows, definition, end)
    groups = {}
    for model, (start, when, kind) in table.items():
        maker = names.canonical(model)[0]
        groups.setdefault(maker, []).append(((when - start).total_seconds() / 86400, kind))
    out, pooled = {}, []
    for maker, group in groups.items():
        if len(group) >= MIN_SUBJECTS and maker != "other":
            out[maker] = group
        else:
            pooled.extend(group)
    if pooled:
        out["other makers"] = pooled
    return out


def incidence(group, day=DAY, resamples=RESAMPLES, seed=SEED):
    """{outcome: [estimate, low, high]} at `day`, or None when too few are followed that long."""
    report = survival.cumulative_incidence(group, (day,), min_at_risk=survival_min(group))
    if day not in report:
        return None
    followed, row = report[day]
    bands = survival.bootstrap(group, (day,), min_at_risk=survival_min(group), resamples=resamples, seed=seed)
    return {"followed": followed, **{
        outcome: [round(row[outcome], 4), round(bands[(day, outcome)][0], 4), round(bands[(day, outcome)][1], 4)]
        for outcome in survival.OUTCOMES if (day, outcome) in bands}}


def survival_min(group):
    """A maker's row is reported while at least 20 of its models are still followed (the main
    result asks for 100 of 5,000)."""
    return 20


def build(rows, end=None, resamples=RESAMPLES):
    """[{maker, models, year: {outcome: [est, low, high]}}] largest makers first, main result last."""
    out = []
    groups = subjects_by_maker(rows, "main", end)
    for maker, group in sorted(groups.items(), key=lambda kv: (kv[0] == "other makers", -len(kv[1]), kv[0])):
        year = incidence(group, resamples=resamples)
        if year is None:
            continue
        out.append({"maker": maker, "models": len(group), "year": year})
    everyone = survival.subjects(rows, "main", end)
    out.append({"maker": "all makers", "models": len(everyone), "year": incidence(everyone, resamples=resamples)})
    return {"day": DAY, "min_subjects": MIN_SUBJECTS, "rows": out}


def spread(result, outcome="price"):
    """The largest and smallest one-year estimate among the named makers, for the page's one line."""
    named = [r for r in result["rows"] if r["maker"] not in ("other makers", "all makers") and r["year"]]
    if len(named) < 2:
        return None
    top = max(named, key=lambda r: r["year"][outcome][0])
    low = min(named, key=lambda r: r["year"][outcome][0])
    return {"outcome": outcome, "high": [top["maker"], top["year"][outcome]], "low": [low["maker"], low["year"][outcome]],
            "median": statistics.median(r["year"][outcome][0] for r in named)}
