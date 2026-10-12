import math
import random

import pytest

from llmledger.simulate import SCENARIOS, draw, truth
from llmledger.survival import cumulative_incidence


def test_truth_matches_the_hand_calculation():
    row = truth(SCENARIOS["slow"], 365)
    assert math.isclose(row["none"], 0.6222, abs_tol=1e-4)
    assert math.isclose(row["price"], 0.1453, abs_tol=1e-4)
    assert math.isclose(row["removed"], 0.0872, abs_tol=1e-4)


@pytest.mark.parametrize("name", SCENARIOS)
def test_truth_sums_to_one(name):
    for day in (30, 365, 730):
        row = truth(SCENARIOS[name], day)
        assert math.isclose(sum(row.values()), 1, abs_tol=1e-12)


@pytest.mark.parametrize("name", SCENARIOS)
def test_req_s13_estimator_recovers_known_truth(name):
    rates = SCENARIOS[name]
    sample = draw(50000, rates, random.Random(20261013))
    report = cumulative_incidence(sample, [365])
    _, est = report[365]
    for outcome, value in truth(rates, 365).items():
        assert abs(est[outcome] - value) < 0.01