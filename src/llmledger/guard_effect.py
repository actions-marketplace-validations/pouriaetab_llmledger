"""Did LiteLLM's cost map guard change how often a price change is a correction?

An interrupted time series (a before-and-after comparison that allows for a trend). LiteLLM
added a CI check of its price file ("the cost map guard", merged 2026-09-04, PR #39835)
that keeps the file and its backup identical and the file valid against a schema. It does
not check that a price is right, so it should not change the share of price changes that
correct the catalogue (the tags of REQ-S20: unit fixes, reverted changes, likely
corrections). This module measures that, instead of assuming it.

Each week is one observation: price changes that week, and how many of them are tagged.
A logistic regression of the tagged share on time, a step at the guard and a change of
slope after it (segmented regression), weighted by the week's changes, over the WEEKS_BEFORE
weeks before the guard and every week after. The step is reported as an odds ratio with a
95% interval from a bootstrap that resamples whole weeks (one bot sync can change hundreds
of rows in a week, so rows are not independent and weeks are the unit). The plain
before-and-after shares and their difference are reported next to it.
"""
import math
import random
from datetime import date, datetime, timedelta

from llmledger import corrections

GUARD_DAY = date(2026, 9, 4)
GUARD = "https://github.com/BerriAI/litellm/pull/39835"
TAGS = ("unit", "reverted", "likely")
WEEKS_BEFORE = 26
RESAMPLES = 1000
SEED = 20261020


def weeks(rows, guard_day=GUARD_DAY, before=WEEKS_BEFORE, end=None):
    """[(week start, price changes, tagged)] for the weeks around the guard, oldest first."""
    counts = {}
    for row in rows:
        if row["kind"] != "price":
            continue
        day = datetime.fromisoformat(row["when"]).date()
        start = day - timedelta(days=day.weekday())
        n, c = counts.get(start, (0, 0))
        counts[start] = (n + 1, c + (1 if row.get("flag", "") in TAGS else 0))
    first = guard_day - timedelta(days=guard_day.weekday()) - timedelta(weeks=before)
    last = end or max(counts)
    out = []
    start = first
    while start <= last:
        n, c = counts.get(start, (0, 0))
        out.append((start, n, c))
        start += timedelta(weeks=1)
    return out


def design(series, guard_day=GUARD_DAY):
    """xs, ys, weights for the segmented regression: intercept, weeks since the start, after the
    guard, weeks since the guard (0 before). A week with no price changes carries no weight."""
    xs, ys, ws = [], [], []
    for i, (start, n, c) in enumerate(series):
        if n == 0:
            continue
        after = 1.0 if start + timedelta(days=6) >= guard_day else 0.0
        since = max(0.0, (start - guard_day).days / 7) if after else 0.0
        xs.append([1.0, float(i), after, since])
        ys.append(c / n)
        ws.append(float(n))
    return xs, ys, ws


def fit(series, guard_day=GUARD_DAY):
    xs, ys, ws = design(series, guard_day)
    if sum(1 for x in xs if x[2] == 1.0) < 2 or sum(1 for x in xs if x[2] == 0.0) < 2:
        return None
    return corrections.fit(xs, ys, ws, ridge=0.01)


def shares(series, guard_day=GUARD_DAY):
    before = [(n, c) for start, n, c in series if start + timedelta(days=6) < guard_day]
    after = [(n, c) for start, n, c in series if start + timedelta(days=6) >= guard_day]
    share = lambda part: (sum(c for _, c in part) / sum(n for n, _ in part)) if sum(n for n, _ in part) else None
    return share(before), share(after), sum(n for n, _ in before), sum(n for n, _ in after)


def bootstrap(series, guard_day=GUARD_DAY, resamples=RESAMPLES, seed=SEED):
    """Resample weeks within each period; the step's odds ratio and the difference of shares."""
    rng = random.Random(seed)
    before = [w for w in series if w[0] + timedelta(days=6) < guard_day]
    after = [w for w in series if w[0] + timedelta(days=6) >= guard_day]
    steps, diffs = [], []
    for _ in range(resamples):
        sample = sorted(rng.choices(before, k=len(before)) + rng.choices(after, k=len(after)))
        beta = fit(sample, guard_day)
        b, a, *_ = shares(sample, guard_day)
        if beta is not None:
            steps.append(beta[2])
        if a is not None and b is not None:
            diffs.append(a - b)
    return corrections.interval(steps) if steps else (None, None), corrections.interval(diffs) if diffs else (None, None)


def build(rows, guard_day=GUARD_DAY, resamples=RESAMPLES):
    series = weeks(rows, guard_day)
    beta = fit(series, guard_day)
    if beta is None:
        return None
    before, after, n_before, n_after = shares(series, guard_day)
    (step_low, step_high), (diff_low, diff_high) = bootstrap(series, guard_day, resamples)
    return {
        "guard": GUARD, "guard_day": guard_day.isoformat(), "weeks_before": WEEKS_BEFORE,
        "weeks": [[start.isoformat(), n, c] for start, n, c in series],
        "share_before": round(before, 4), "share_after": round(after, 4),
        "changes_before": n_before, "changes_after": n_after,
        "difference": [round(after - before, 4), round(diff_low, 4), round(diff_high, 4)],
        "step_odds_ratio": [round(math.exp(beta[2]), 3), round(math.exp(step_low), 3), round(math.exp(step_high), 3)],
        "slope_before_per_week": round(beta[1], 4), "slope_change_per_week": round(beta[3], 4),
        "reading": reading(after - before, diff_low, diff_high),
    }


def reading(diff, low, high):
    if low is None or high is None:
        return "too few weeks to tell"
    if low <= 0 <= high:
        return "no change the data can show"
    return "fewer corrections after the guard" if diff < 0 else "more corrections after the guard"
