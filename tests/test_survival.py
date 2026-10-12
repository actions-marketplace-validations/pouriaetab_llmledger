import math

from llmledger.survival import (
    bootstrap,
    cumulative_incidence,
    subjects,
)

TOY = [
    (10, "price"), (20, "removed"), (30, "censored"),
    (40, "price"), (50, "retirement"), (60, "censored"),
]

def row(day, model, kind, field="", old="null", new="null"):
    return {
        "when": f"2026-01-{day:02d}T00:00:00+00:00",
        "sha": "x", "model": model, "kind": kind,
        "field": field, "old": old, "new": new,
    }


def test_req_s11_known_answer():
    report = cumulative_incidence(TOY, [60], min_at_risk=1)
    at_risk, est = report[60]
    assert at_risk == 1
    assert math.isclose(est["price"], 7 / 18, abs_tol=1e-12)
    assert math.isclose(est["removed"], 1 / 6, abs_tol=1e-12)
    assert math.isclose(est["retirement"], 2 / 9, abs_tol=1e-12)
    assert math.isclose(est["none"], 2 / 9, abs_tol=1e-12)


def test_drill_two_exits_on_the_same_day():
    drill = [
        (5, "price"), (5, "removed"), (12, "censored"),
        (20, "price"), (20, "retirement"), (30, "censored"),
        (40, "censored"),
    ]
    report = cumulative_incidence(drill, [40], min_at_risk=1)
    _, est = report[40]
    assert math.isclose(est["price"], 9 / 28, abs_tol=1e-12)
    assert math.isclose(est["removed"], 1 / 7, abs_tol=1e-12)
    assert math.isclose(est["retirement"], 5 / 28, abs_tol=1e-12)
    assert math.isclose(est["none"], 5 / 14, abs_tol=1e-12)


def test_req_s5_totals_sum_to_one():
    report = cumulative_incidence(
        TOY, [15, 35, 60], min_at_risk=1
    )
    for _, est in report.values():
        assert math.isclose(sum(est.values()), 1, abs_tol=1e-9)


def test_req_s7_too_few_at_risk_is_not_reported():
    assert cumulative_incidence(TOY, [60]) == {}


def test_req_s1_day_one_models_are_excluded():
    rows = [
        row(1, "old", "start"),
        row(1, "new", "added"),
        row(5, "old", "removed"),
        row(10, "old", "added"),
    ]
    assert subjects(rows) == [(9.0, "censored")]


def test_req_s2_only_the_first_appearance_counts():
    rows = [
        row(1, "m", "added"),
        row(11, "m", "removed"),
        row(21, "m", "added"),
    ]
    assert subjects(rows) == [(10.0, "removed")]


def test_req_s3_removal_wins_a_tie():
    rows = [
        row(1, "m", "added"),
        row(6, "m", "price", "input_cost_per_token",
            "1e-06", "2e-06"),
        row(6, "m", "removed"),
    ]
    assert subjects(rows) == [(5.0, "removed")]


def test_d5_a_new_price_field_is_not_a_price_change():
    rows = [
        row(1, "m", "added"),
        row(3, "m", "price", "input_cost_per_token",
            "null", "1e-06"),
    ]
    assert subjects(rows) == [(2.0, "censored")]


def test_d6_only_a_first_retirement_date_is_an_exit():
    rows = [
        row(1, "a", "added"),
        row(1, "c", "added"),
        row(4, "a", "deprecation", "deprecation_date",
            "null", '"2026-12-01"'),
        row(4, "c", "deprecation", "deprecation_date",
            '"2026-12-01"', '"2027-01-01"'),
    ]
    assert subjects(rows) == [(3.0, "retirement"),
                              (3.0, "censored")]


def test_req_s10_definitions_differ_as_specified():
    rows = [
        row(1, "m", "added"),
        row(3, "m", "price", "cache_read_input_token_cost",
            "1e-07", "2e-07"),
        row(9, "other", "added"),
    ]
    assert subjects(rows, "main") == [(2.0, "price"),
                                      (0.0, "censored")]
    assert subjects(rows, "headline") == [(8.0, "censored"),
                                          (0.0, "censored")]
    assert subjects(rows, "no_first_week") == [(8.0, "censored"),
                                               (0.0, "censored")]


def test_req_s8_s9_intervals_are_ordered_and_repeatable():
    first = bootstrap(TOY, [60], min_at_risk=1, resamples=50)
    second = bootstrap(TOY, [60], min_at_risk=1, resamples=50)
    assert first == second
    for low, high in first.values():
        assert low <= high

