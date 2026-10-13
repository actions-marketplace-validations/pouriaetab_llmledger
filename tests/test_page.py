from datetime import datetime, timezone

from llmledger.page import load, render

ROWS = """definition,days,outcome,estimate,ci_low,ci_high,at_risk
main,365,price,0.152978,0.14143,0.165948,1197
main,365,retirement,0.159206,0.145113,0.172802,1197
main,365,removed,0.094291,0.085481,0.103624,1197
main,365,none,0.593525,0.575173,0.611424,1197
"""
INFO = {
    "models": 5100,
    "since": datetime(2023, 9, 6, 23, 31, tzinfo=timezone.utc),
    "sha": "7dc7f101d9553be32888d726947ea85ec3caa70b",
    "when": datetime(2026, 10, 12, 21, 31, tzinfo=timezone.utc),
    "built": datetime(2026, 10, 13, 6, 20, tzinfo=timezone.utc),
    "python": "3.14.7",
}


def page_for(tmp_path):
    source = tmp_path / "survival.csv"
    source.write_text(ROWS)
    return render(load(source), INFO)


def test_page_shows_estimates_with_intervals(tmp_path):
    page = page_for(tmp_path)
    assert "15.3%<small>14.1 to 16.6</small>" in page
    assert "59.4%<small>57.5 to 61.1</small>" in page
    assert "1,197" in page


def test_req_s15_page_names_the_data_it_was_built_from(tmp_path):
    page = page_for(tmp_path)
    assert "commit/7dc7f101d9553be32888d726947ea85ec3caa70b" in page
    assert "12 October 2026, 21:31 UTC" in page
    assert "5,100 models" in page
    assert "Python 3.14.7" in page


def test_every_placeholder_is_filled(tmp_path):
    assert "$" not in page_for(tmp_path)