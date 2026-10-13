import pytest

from llmledger import route_eval


def test_req_s27_wilson_interval_known_answer():
    low, high = route_eval.wilson(50, 100)
    assert low == pytest.approx(0.4038, abs=1e-4) and high == pytest.approx(0.5962, abs=1e-4)
    assert route_eval.wilson(0, 0) == (0.0, 1.0)


def row(language="en", coding=False, math=False, creative_writing=False):
    return {"language": language, "coding": coding, "math": math,
            "creative_writing": creative_writing, "text": ""}


def test_req_s27_a_guess_is_right_when_it_is_one_of_the_tasks():
    assert route_eval.correct("coding", {"coding", "russian"})
    assert route_eval.correct("russian", {"coding", "russian"})
    assert route_eval.correct("webdev", {"coding"})
    assert not route_eval.correct("math", {"coding"})
    assert route_eval.correct("overall", set()) and route_eval.correct("legal", set())
    assert not route_eval.correct("coding", set())


def test_req_s27_score_against_always_overall():
    rows = [row(coding=True), row(math=True), row(), row(language="ru")]
    report = route_eval.score(rows, ["coding", "overall", "overall", "russian"])
    assert report["n"] == 4
    assert report["right"][0] == 3 and report["always_overall"][0] == 1
    coding = report["tasks"]["coding"]
    assert coding["precision"][:2] == [1, 1] and coding["recall"][:2] == [1, 1]
    assert report["tasks"]["math"]["recall"][:2] == [0, 1]
