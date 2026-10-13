import math

from llmledger.outlook import conditional, outlook

TOY = [
    (10, "price"), (20, "removed"), (30, "censored"),
    (40, "price"), (50, "retirement"), (60, "censored"),
]


def test_req_s17_outlook_known_answer():
    result = outlook(TOY, horizons=(40,), step=20, min_at_risk=1,
                     resamples=20)
    cells, at_risk = result[(40, 20)]
    assert at_risk == 1
    assert math.isclose(cells["price"][0], 1 / 3, abs_tol=1e-12)
    assert math.isclose(cells["retirement"][0], 1 / 3, abs_tol=1e-12)
    assert math.isclose(cells["removed"][0], 0, abs_tol=1e-12)
    assert math.isclose(cells["none"][0], 1 / 3, abs_tol=1e-12)


def test_conditional_shares_add_up_to_one():
    now = {"price": 0.1, "retirement": 0.05, "removed": 0.05, "none": 0.8}
    later = {"price": 0.2, "retirement": 0.1, "removed": 0.1, "none": 0.6}
    row = conditional(now, later)
    assert math.isclose(sum(row.values()), 1, abs_tol=1e-12)
    assert math.isclose(row["price"], 0.125, abs_tol=1e-12)


def test_req_s7_outlook_hides_too_few_at_risk():
    assert outlook(TOY, horizons=(40,), step=20, resamples=5) == {}
