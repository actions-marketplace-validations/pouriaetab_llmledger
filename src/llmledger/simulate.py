import csv
import math
import random
import statistics

from llmledger.survival import EXITS, bootstrap, cumulative_incidence

SCENARIOS = {
    "slow": {"price": 0.0005, "retirement": 0.0005, "removed": 0.0003},
    "fast": {"price": 0.001, "retirement": 0.001, "removed": 0.0006},
}
FOLLOW_UP = 1100
DAYS = (90, 180, 365)
SIZES = (500, 2000)
REPLICATIONS = 200
RESAMPLES = 200
SEED = 20261013


def truth(rates, day):
    total = sum(rates.values())
    none = math.exp(-total * day)
    row = {cause: rates[cause] / total * (1 - none) for cause in EXITS}
    row["none"] = none
    return row


def draw(n, rates, rng, follow_up=FOLLOW_UP):
    total = sum(rates.values())
    causes = list(rates)
    weights = [rates[cause] for cause in causes]
    subjects = []
    for _ in range(n):
        exit_day = rng.expovariate(total)
        watched = rng.uniform(0, follow_up)
        if exit_day <= watched:
            cause = rng.choices(causes, weights)[0]
            subjects.append((exit_day, cause))
        else:
            subjects.append((watched, "censored"))
    return subjects


def check(n, rates, rng, replications=REPLICATIONS, resamples=RESAMPLES):
    errors = {}
    hits = {}
    for _ in range(replications):
        sample = draw(n, rates, rng)
        report = cumulative_incidence(sample, DAYS)
        intervals = bootstrap(sample, DAYS, resamples=resamples,
                              seed=rng.randrange(2**32))
        for day, (_, row) in report.items():
            true_row = truth(rates, day)
            for outcome, value in row.items():
                key = (day, outcome)
                low, high = intervals[key]
                errors.setdefault(key, []).append(value - true_row[outcome])
                hits.setdefault(key, []).append(
                    low <= true_row[outcome] <= high
                )
    rows = []
    for (day, outcome), errs in sorted(errors.items()):
        rows.append({
            "n": n,
            "days": day,
            "outcome": outcome,
            "truth": round(truth(rates, day)[outcome], 6),
            "bias": round(statistics.fmean(errs), 6),
            "rmse": round(math.sqrt(statistics.fmean(
                e * e for e in errs)), 6),
            "coverage": round(statistics.fmean(hits[(day, outcome)]), 3),
        })
    return rows


if __name__ == "__main__":
    rng = random.Random(SEED)
    rows = []
    for name, rates in SCENARIOS.items():
        for n in SIZES:
            result = check(n, rates, rng)
            rows.extend({"scenario": name, **row} for row in result)
            worst = max(abs(row["bias"]) for row in result)
            cover = [row["coverage"] for row in result]
            rmse = next(row["rmse"] for row in result
                        if row["days"] == 365 and row["outcome"] == "price")
            print(f"{name}  n={n:>4}  largest bias {worst:.4f}  "
                  f"price rmse at 365 days {rmse:.4f}  "
                  f"coverage {min(cover):.0%} to {max(cover):.0%}")
    with open("data/simulation.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)