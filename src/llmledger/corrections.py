"""How well do simple rules, and a small model, tell catalogue corrections from real price changes? (issue #7)

A first price change (D5) of a model added after the first catalogue version is labelled by reading the evidence
for it (docs/corrections/labelling-guide.md): a correction when the number was wrong when it was entered, a
repricing when it was right and the host's price changed later, unclear when the evidence cannot tell. The
labelled sample (docs/corrections/sample.csv) is a stratified random sample: 100 first changes from a model's
first 7 days and 100 from later. Rules and the model are scored on the labelled cases against the population,
weighting each stratum by its size, with 95% intervals from a bootstrap that resamples whole LiteLLM commits
within each stratum (one commit often changes many rows at once, so rows are not independent).
"""
import csv
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from llmledger import flags, survival

HERE = Path(__file__).parent
SAMPLE = HERE.parent.parent / "docs" / "corrections" / "sample.csv"
OUT = HERE / "corrections_eval.json"
FIRST_WEEK = flags.FIRST_WEEK
PER_STRATUM = 100
SEED = 7
RESAMPLES = 2000
FOLDS = 5
LABELS = ("correction", "repricing", "unclear")
COLUMNS = ("stratum", "model", "when", "sha", "field", "old", "new", "days_in", "flag", "batch", "label", "reason",
           "commit")


def population(rows):
    """Every model's first price change (D5: a number to a different number), for models added after the first
    catalogue version, with its days since the model was added, its tag (D10 to D12) and the number of price
    changes in the same LiteLLM commit."""
    rows = sorted(rows, key=lambda r: r["when"])
    flags.mark(rows)
    day_one = {r["model"] for r in rows if r["kind"] == "start"}
    added, first, batch = {}, {}, Counter()
    for r in rows:
        if r["kind"] == "added" and r["model"] not in day_one:
            added.setdefault(r["model"], r["when"])
    for r in rows:
        if r["kind"] != "price":
            continue
        old, new = json.loads(r["old"]), json.loads(r["new"])
        if not (survival._is_number(old) and survival._is_number(new) and old != new):
            continue
        batch[r["sha"]] += 1
        if r["model"] in added and r["model"] not in first:
            first[r["model"]] = r
    out = []
    for model, r in first.items():
        days = (datetime.fromisoformat(r["when"]) - datetime.fromisoformat(added[model])).total_seconds() / 86400
        out.append({"model": model, "when": r["when"], "sha": r["sha"], "field": r["field"], "old": r["old"],
                    "new": r["new"], "days_in": round(days, 3), "flag": r["flag"], "batch": batch[r["sha"]],
                    "stratum": "first_week" if days <= FIRST_WEEK else "later"})
    return sorted(out, key=lambda p: (p["when"], p["model"], p["field"]))


def draw(pop, per_stratum=PER_STRATUM, seed=SEED):
    """The stratified random sample: the same rows every time for the same population."""
    rng = random.Random(seed)
    out = []
    for stratum in ("first_week", "later"):
        part = [p for p in pop if p["stratum"] == stratum]
        out += rng.sample(part, min(per_stratum, len(part)))
    return out


def _ratio(case):
    old, new = float(case["old"]), float(case["new"])
    return new / old if old else None


def rules(case):
    """Each rule's call: True means 'a correction'. first_week_or_tenfold is the page's likely correction tag
    (D14, flags.likely), so the scores below are the scores of that tag on first price changes."""
    days = float(case["days_in"])
    tagged = case["flag"] in ("unit", "reverted")
    return {"tags": tagged, "first_week": days <= FIRST_WEEK, "tags_or_first_week": tagged or days <= FIRST_WEEK,
            "first_week_or_tenfold": flags.likely(float(case["old"]), float(case["new"]), days)}


RULE_TEXT = {
    "tags": "The page's current tags: a unit fix (100 times or more) or a change undone within 30 days (D11, D12)",
    "first_week": "Any first change in a model's first 7 days",
    "tags_or_first_week": "Either of the two above",
    "first_week_or_tenfold": "A first change in the first 7 days, or one of 10 times or more either way (or from 0)",
}


def features(case):
    """Inputs to the model: none of them is read from the commit message the labels rest on."""
    ratio = _ratio(case)
    size = 3.0 if not ratio else min(3.0, abs(math.log10(ratio)))
    lower = 1.0 if float(case["new"]) < float(case["old"]) else 0.0
    return [1.0, math.log1p(float(case["days_in"])), size, math.log1p(int(case["batch"])), lower]


FEATURE_TEXT = ["intercept", "log(1 + days since added)", "size of the change, |log10(new / old)| (up to 3)",
                "log(1 + price changes in the same commit)", "1 if the price went down"]


def _solve(a, b):
    n = len(b)
    m = [row[:] + [v] for row, v in zip(a, b)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[j][n] / m[j][j] for j in range(n)]


def fit(xs, ys, weights, ridge=1.0, steps=100):
    """Weighted logistic regression by Newton's method, with a small ridge penalty (not on the intercept)."""
    beta = [0.0] * len(xs[0])
    for _ in range(steps):
        grad = [0.0] * len(beta)
        hess = [[0.0] * len(beta) for _ in beta]
        for x, y, w in zip(xs, ys, weights):
            p = 1 / (1 + math.exp(-sum(b * v for b, v in zip(beta, x))))
            for j, xj in enumerate(x):
                grad[j] += w * (y - p) * xj
                for k, xk in enumerate(x):
                    hess[j][k] += w * p * (1 - p) * xj * xk
        for j in range(1, len(beta)):
            grad[j] -= ridge * beta[j]
            hess[j][j] += ridge
        step = _solve(hess, grad)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-9:
            break
    return beta


def predict(beta, x):
    return 1 / (1 + math.exp(-sum(b * v for b, v in zip(beta, x))))


def cross_validated(cases, weights, folds=FOLDS, seed=SEED):
    """Out-of-fold chances of 'a correction', with folds made of whole commits so that rows of one commit are never
    both learned from and scored."""
    commits = sorted({c["sha"] for c in cases})
    random.Random(seed).shuffle(commits)
    fold = {sha: i % folds for i, sha in enumerate(commits)}
    out = {}
    for k in range(folds):
        train = [i for i, c in enumerate(cases) if fold[c["sha"]] != k]
        beta = fit([features(cases[i]) for i in train], [float(cases[i]["label"] == "correction") for i in train],
                   [weights[i] for i in train])
        for i, c in enumerate(cases):
            if fold[c["sha"]] == k:
                out[i] = predict(beta, features(c))
    return [out[i] for i in range(len(cases))]


def scores(calls, truth, weights):
    """Precision and recall for 'a correction', each case weighted by its stratum's size over its sample size."""
    tp = sum(w for c, t, w in zip(calls, truth, weights) if c and t)
    called = sum(w for c, w in zip(calls, weights) if c)
    real = sum(w for t, w in zip(truth, weights) if t)
    return (tp / called if called else None), (tp / real if real else None)


def interval(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return [round(values[round(0.025 * (len(values) - 1))], 3), round(values[round(0.975 * (len(values) - 1))], 3)]


def _bootstrap(cases, statistic, resamples=RESAMPLES, seed=SEED):
    """Resample whole commits within each stratum, then recompute the statistic on the rows they bring."""
    rng = random.Random(seed)
    groups = defaultdict(lambda: defaultdict(list))
    for i, c in enumerate(cases):
        groups[c["stratum"]][c["sha"]].append(i)
    out = []
    for _ in range(resamples):
        rows = []
        for stratum in sorted(groups):
            shas = sorted(groups[stratum])
            for sha in (rng.choice(shas) for _ in shas):
                rows += groups[stratum][sha]
        out.append(statistic(rows))
    return out


def evaluate(cases, strata, unclear="drop"):
    """Scores for every rule and the model. unclear: 'drop' (the main result), 'repricing' or 'correction'."""
    if unclear == "drop":
        cases = [c for c in cases if c["label"] != "unclear"]
    else:
        cases = [{**c, "label": unclear if c["label"] == "unclear" else c["label"]} for c in cases]
    n = Counter(c["stratum"] for c in cases)
    sampled = Counter(c["stratum"] for c in cases)
    weight = [strata[c["stratum"]] / n[c["stratum"]] for c in cases]
    truth = [c["label"] == "correction" for c in cases]
    model = cross_validated(cases, weight)
    calls = {name: [rules(c)[name] for c in cases] for name in RULE_TEXT}
    calls["model"] = [p >= 0.5 for p in model]

    def rated(rows, name):
        return scores([calls[name][i] for i in rows], [truth[i] for i in rows], [weight[i] for i in rows])

    def left(rows, name):
        """The share of corrections among the changes the rule does not call one: what it leaves in."""
        kept = [i for i in rows if not calls[name][i]]
        total = sum(weight[i] for i in kept)
        return sum(weight[i] for i in kept if truth[i]) / total if total else None

    out = {}
    for name in calls:
        precision, recall = rated(range(len(cases)), name)
        boot = _bootstrap(cases, lambda rows, name=name: rated(rows, name) + (left(rows, name),))
        rest = left(range(len(cases)), name)
        out[name] = {"precision": round(precision, 3), "precision_95": interval([b[0] for b in boot]),
                     "recall": round(recall, 3), "recall_95": interval([b[1] for b in boot]),
                     "corrections_left": None if rest is None else round(rest, 3),
                     "corrections_left_95": interval([b[2] for b in boot])}

    def share(rows, stratum=None):
        picked = [i for i in rows if stratum is None or cases[i]["stratum"] == stratum]
        total = sum(weight[i] for i in picked)
        return sum(weight[i] for i in picked if truth[i]) / total if total else None

    corrections = {}
    for stratum in (None, "first_week", "later"):
        key = stratum or "all"
        boot = _bootstrap(cases, lambda rows, s=stratum: share(rows, s))
        corrections[key] = {"share": round(share(range(len(cases)), stratum), 3), "share_95": interval(boot),
                            "labelled": sum(1 for c in cases if stratum is None or c["stratum"] == stratum)}
    return {"cases": len(cases), "by_stratum": dict(sampled), "corrections": corrections, "rules": out}


def load_sample(path=SAMPLE):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_sample(cases, path=SAMPLE):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(cases)


def report(cases, strata, events_through):
    decided = [c for c in cases if c["label"] != "unclear"]
    weights = [strata[c["stratum"]] / Counter(d["stratum"] for d in decided)[c["stratum"]] for c in decided]
    beta = fit([features(c) for c in decided], [float(c["label"] == "correction") for c in decided], weights)
    return {
        "question": "Is a model's first price change a correction of the first entry or a real price change? (issue #7)",
        "population": {"first_price_changes": sum(strata.values()), "strata": strata,
                       "events_through": events_through, "first_week_days": FIRST_WEEK},
        "sample": {"per_stratum": PER_STRATUM, "seed": SEED, "labels": dict(Counter(c["label"] for c in cases)),
                   "labels_by_stratum": {s: dict(Counter(c["label"] for c in cases if c["stratum"] == s))
                                         for s in strata}},
        "method": ("Stratified random sample; weighted by stratum size; 95% intervals from a bootstrap of whole "
                   f"commits within strata ({RESAMPLES} resamples); the model is a weighted logistic regression "
                   f"scored by {FOLDS}-fold cross-validation with folds of whole commits."),
        "rules_text": RULE_TEXT,
        "main": evaluate(cases, strata),
        "unclear_as_repricing": evaluate(cases, strata, unclear="repricing"),
        "unclear_as_correction": evaluate(cases, strata, unclear="correction"),
        "model": {"features": FEATURE_TEXT, "coefficients": [round(b, 3) for b in beta],
                  "call": "a correction when its chance is 0.5 or more"},
    }


def summary(result):
    """The part of the report the page and data.json carry: the share of first price changes that are
    corrections, and how the likely correction tag (D14) does."""
    main = result["main"]
    tag = main["rules"]["first_week_or_tenfold"]
    return {"labelled": sum(result["sample"]["labels"].values()), "events_through": result["population"]["events_through"],
            "first_week_days": result["population"]["first_week_days"],
            **{k: {"share": v["share"], "share_95": v["share_95"]} for k, v in main["corrections"].items()},
            "likely_tag": {k: tag[k] for k in ("precision", "precision_95", "recall", "recall_95",
                                               "corrections_left", "corrections_left_95")}}


def main(events="data/events.csv", sample=SAMPLE, out=OUT):
    """With the labelled sample in place, recompute the report. The population counts come from the events the
    sample was drawn from (kept in the report), so the report can be rebuilt from the sample alone."""
    cases = load_sample(sample)
    old = json.loads(Path(out).read_text()) if Path(out).exists() else None
    if Path(events).exists():
        with open(events, newline="") as f:
            rows = list(csv.DictReader(f))
        drawn = {(p["model"], p["when"], p["field"]) for p in draw(population(rows))}
        through = max(r["when"] for r in rows)
        if old and old["population"]["events_through"] != through:
            through = old["population"]["events_through"]   # newer events: keep the frame the sample came from
            strata = old["population"]["strata"]
        else:
            pop = population(rows)
            strata = dict(Counter(p["stratum"] for p in pop))
            missing = [c for c in cases if (c["model"], c["when"], c["field"]) not in drawn]
            if missing:
                raise SystemExit(f"{len(missing)} labelled rows are not in the sample drawn from {events}")
    else:
        strata, through = old["population"]["strata"], old["population"]["events_through"]
    result = report(cases, strata, through)
    Path(out).write_text(json.dumps(result, indent=1) + "\n")
    return result


if __name__ == "__main__":
    main()
