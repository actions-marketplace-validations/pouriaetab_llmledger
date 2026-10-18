import json
from collections import Counter

import pytest

from llmledger import corrections as K


def event(when, model, kind, field="", old="null", new="null", sha="a"):
    return {"when": when, "sha": sha, "model": model, "kind": kind, "field": field, "old": old, "new": new}


ROWS = [
    event("2025-01-01T00:00:00+00:00", "old-model", "start"),
    event("2025-01-01T00:00:00+00:00", "old-model", "price", "input_cost_per_token", "1e-06", "2e-06", "s0"),
    event("2025-01-02T00:00:00+00:00", "quick", "added", sha="s1"),
    event("2025-01-02T00:00:00+00:00", "slow", "added", sha="s1"),
    event("2025-01-02T00:00:00+00:00", "never", "added", sha="s1"),
    # a new price field is not a price change (D5); the first number-to-number change is
    event("2025-01-03T00:00:00+00:00", "quick", "price", "cache_read_input_token_cost", "null", "1e-07", "s2"),
    event("2025-01-05T00:00:00+00:00", "quick", "price", "input_cost_per_token", "0.001", "1e-06", "s3"),
    event("2025-01-05T00:00:00+00:00", "slow", "price", "output_cost_per_token", "4e-06", "4e-06", "s3"),
    event("2025-03-01T00:00:00+00:00", "slow", "price", "output_cost_per_token", "4e-06", "3e-06", "s4"),
    event("2025-04-01T00:00:00+00:00", "quick", "price", "input_cost_per_token", "1e-06", "2e-06", "s5"),
]


def test_req_s37_first_price_changes_and_strata():
    pop = {p["model"]: p for p in K.population(ROWS)}
    assert set(pop) == {"quick", "slow"}                      # day-one models and unchanged ones are left out
    assert pop["quick"]["days_in"] == 3.0 and pop["quick"]["stratum"] == "first_week"
    assert pop["quick"]["flag"] == "unit" and pop["quick"]["batch"] == 1     # 1,000 times: a unit fix (D11)
    assert pop["slow"]["days_in"] == 58.0 and pop["slow"]["stratum"] == "later"
    assert pop["slow"]["when"].startswith("2025-03-01")       # an unchanged number is not a change


def test_req_s37_the_sample_is_the_same_every_time():
    pop = [{"model": f"m{i}", "when": f"2025-01-{i % 28 + 1:02d}", "field": "f", "stratum": "first_week" if i < 30 else "later"}
           for i in range(90)]
    one, two = K.draw(pop, per_stratum=10), K.draw(pop, per_stratum=10)
    assert one == two and len(one) == 20
    assert Counter(p["stratum"] for p in one) == {"first_week": 10, "later": 10}
    assert K.draw(pop, per_stratum=10, seed=8) != one


def case(days, old, new, flag="", label="correction", stratum="first_week", sha="x", batch=1):
    return {"days_in": str(days), "old": str(old), "new": str(new), "flag": flag, "label": label, "stratum": stratum,
            "sha": sha, "batch": str(batch)}


def test_req_s37_rules_known_answers():
    assert K.rules(case(3, 1e-6, 2e-6)) == {"tags": False, "first_week": True, "tags_or_first_week": True,
                                             "first_week_or_tenfold": True}
    assert K.rules(case(30, 1e-6, 2e-6, "reverted"))["tags"] is True
    late_tenfold = K.rules(case(30, 1e-6, 1e-7))
    assert late_tenfold["first_week"] is False and late_tenfold["first_week_or_tenfold"] is True
    assert K.rules(case(30, 0, 1e-7))["first_week_or_tenfold"] is True          # from a placeholder 0
    assert K.rules(case(30, 1e-6, 5e-7)) == {"tags": False, "first_week": False, "tags_or_first_week": False,
                                              "first_week_or_tenfold": False}


def test_req_s37_weighted_scores_known_answer():
    # three cases called a correction (two right), one correction missed; weights 1, 1, 2, 4
    precision, recall = K.scores([True, True, True, False], [True, True, False, True], [1, 1, 2, 4])
    assert precision == pytest.approx(2 / 4) and recall == pytest.approx(2 / 6)
    assert K.scores([False], [False], [1]) == (None, None)
    assert K.interval([0.1, 0.5, 0.9, None]) == [0.1, 0.9]


def test_req_s37_model_learns_a_clear_pattern():
    # early and large changes are corrections, late and small ones are not
    cases = [case(d, 1e-6, r * 1e-6, label="correction" if d < 5 else "repricing")
             for d, r in [(1, 100), (2, 50), (3, 0.01), (4, 20), (40, 0.8), (60, 1.2), (90, 0.9), (200, 1.5)]]
    beta = K.fit([K.features(c) for c in cases], [float(c["label"] == "correction") for c in cases], [1.0] * 8)
    assert beta[1] < 0 and beta[2] > 0                        # fewer days and a bigger change: more likely a correction
    assert K.predict(beta, K.features(case(2, 1e-6, 1e-4))) > 0.5 > K.predict(beta, K.features(case(300, 1e-6, 9e-7)))


def test_req_s37_labelled_sample_is_complete():
    cases = K.load_sample()
    assert len(cases) == 200
    assert Counter(c["stratum"] for c in cases) == {"first_week": 100, "later": 100}
    assert {c["label"] for c in cases} <= set(K.LABELS)
    assert all(c["reason"].strip() and c["commit"].strip() for c in cases)
    assert all(float(c["days_in"]) <= K.FIRST_WEEK for c in cases if c["stratum"] == "first_week")
    assert all(float(c["days_in"]) > K.FIRST_WEEK for c in cases if c["stratum"] == "later")
    assert len({(c["model"], c["field"], c["when"]) for c in cases}) == 200


def test_req_s37_report_rebuilds_from_the_sample():
    saved = json.loads(K.OUT.read_text())
    rebuilt = K.report(K.load_sample(), saved["population"]["strata"], saved["population"]["events_through"])
    assert rebuilt == saved
    main = saved["main"]
    assert main["cases"] == sum(saved["sample"]["labels"][k] for k in ("correction", "repricing"))
    for rule in main["rules"].values():
        low, high = rule["precision_95"]
        assert low <= rule["precision"] <= high
