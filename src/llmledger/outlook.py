import random
import statistics

from llmledger.survival import EXITS, OUTCOMES, cumulative_incidence

HORIZONS = (90, 365)
STEP = 7


def conditional(now, later):
    alive = now["none"]
    if alive <= 0:
        return None
    row = {cause: (later[cause] - now[cause]) / alive for cause in EXITS}
    row["none"] = later["none"] / alive
    return row


def _table(subjects, starts, horizons, min_at_risk):
    points = sorted({s + h for s in starts for h in (0, *horizons)})
    report = cumulative_incidence(subjects, points, min_at_risk=1)
    table = {}
    for horizon in horizons:
        for start in starts:
            end = start + horizon
            if start not in report or end not in report:
                continue
            at_risk = report[end][0]
            if at_risk < min_at_risk:
                continue
            row = conditional(report[start][1], report[end][1])
            if row is not None:
                table[(horizon, start)] = (row, at_risk)
    return table


def outlook(subjects, horizons=HORIZONS, step=STEP, min_at_risk=100,
            resamples=1000, seed=20261001):
    longest = max(time for time, _ in subjects)
    starts = range(0, int(longest) + 1, step)
    table = _table(subjects, starts, horizons, min_at_risk)
    rng = random.Random(seed)
    draws = {}
    for _ in range(resamples):
        sample = rng.choices(subjects, k=len(subjects))
        again = _table(sample, starts, horizons, 1)
        for key in table:
            if key in again:
                for outcome, value in again[key][0].items():
                    draws.setdefault((key, outcome), []).append(value)
    result = {}
    for key, (row, at_risk) in table.items():
        cells = {}
        for outcome in OUTCOMES:
            values = draws.get((key, outcome), [row[outcome]] * 2)
            cuts = statistics.quantiles(values, n=40)
            cells[outcome] = (row[outcome], cuts[0], cuts[-1])
        result[key] = (cells, at_risk)
    return result
