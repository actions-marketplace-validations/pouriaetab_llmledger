from datetime import datetime, timezone

from llmledger.page import data_script, load, render

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


def test_page_data_cannot_close_its_script_tag():
    assert "</script>" not in data_script({"name": "</script>"})


def test_req_s21_page_compares_every_change_with_real_changes(tmp_path):
    source = tmp_path / "survival.csv"
    source.write_text(ROWS + ROWS.split("\n", 1)[1].replace("main,", "real_only,"))
    page = render(load(source), INFO)
    assert "<tr><th>Real changes only</th><td>15.3%<small>14.1 to 16.6" in page
    assert "<tr><th>Leaving out corrections</th>" in page


def test_req_s28_page_opens_on_the_prompt_box(tmp_path):
    page = page_for(tmp_path)
    assert page.index('id="tab-ask"') < page.index('id="tab-models"')
    for view in ("ask", "race", "models", "trends", "about"):
        assert f'data-tab="{view}"' in page
    assert 'id="cost-text"' in page and 'id="picks"' in page
    assert "app.js?v=" in page and "data.js?v=" in page


def test_req_s29_page_compares_models_side_by_side(tmp_path):
    page = page_for(tmp_path)
    ask = page[page.index('id="tab-ask"'):page.index('id="tab-models"')]
    assert 'id="which"' in ask and 'id="which-cols"' in ask and 'id="which-sum"' in ask
    for pay in ("api", "claude", "chatgpt"):
        assert f'data-pay="{pay}"' in ask
    assert page.index("pick.js?v=") < page.index("app.js?v=")


def test_req_s30_arena_is_explained_on_the_page(tmp_path):
    page = page_for(tmp_path)
    assert '<div id="arena-help" class="pop" popover>' in page and "What is Arena?" in page
    assert 'id="rate-chart"' in page and 'id="rate-table"' in page


def test_req_s33_trends_view_replays_the_leaderboards(tmp_path):
    page = page_for(tmp_path)
    view = page[page.index('id="tab-race"'):page.index('id="tab-models"')]
    for view_id in ("open", "makers", "price"):
        assert f'data-view="{view_id}"' in view
    for part in ('id="race-chart"', 'id="race-play"', 'id="race-at"', 'id="race-legend"', 'id="race-table"',
                 'id="arrivals"', 'id="changes"', 'href="#week"'):
        assert part in view
    assert page.index("trends.js?v=") < page.index("app.js?v=")


def test_req_s34_cost_vs_quality_sits_on_ask(tmp_path):
    page = page_for(tmp_path)
    ask = page[page.index('id="tab-ask"'):page.index('id="tab-race"')]
    assert 'id="frontier"' in ask and 'id="front-chart"' in ask and 'id="front-list"' in ask
    assert ask.index('id="which"') < ask.index('id="frontier"')
