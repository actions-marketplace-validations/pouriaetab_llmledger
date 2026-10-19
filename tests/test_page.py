from datetime import datetime, timezone
from pathlib import Path

from llmledger import page as page_module
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
    body = ROWS.split("\n", 1)[1]
    source.write_text(ROWS + body.replace("main,", "real_only,") +
                      body.replace("main,", "likely_real,").replace("0.152978,0.14143,0.165948", "0.1,0.09,0.11"))
    page = render(load(source), INFO)
    assert "<tr><th>Leaving out unit fixes and undone changes</th><td>15.3%<small>14.1 to 16.6" in page
    assert "<tr><th>Leaving out likely corrections as well</th><td>10.0%<small>9.0 to 11.0" in page
    assert "Leaving out likely corrections, 10.0% (9.0 to 11.0) changed price within a year." in page
    assert "Real changes only" not in page     # no estimate here leaves out every correction


def test_req_s21_page_says_when_the_estimate_without_corrections_is_missing(tmp_path):
    page = page_for(tmp_path)
    assert "rather than change what a host charges.\n</p>" in page and "Leaving out likely corrections," not in page


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


def test_req_s36_one_page_or_natural_scrolling(tmp_path):
    page = page_for(tmp_path)
    style = page[page.index("<style>"):page.index("</style>")]
    # the page scrolls the normal way when a view is long: no window-high body, no views that scroll inside
    assert "100dvh" not in style and "height: 100vh" not in style and "body { display: flex" not in style
    assert "main > section:not([hidden]) { flex: 1 1 auto" not in style
    # nothing is cut: no line limits, no ellipsis on what people read, no lists or panels that scroll inside
    assert "line-clamp" not in style
    for rule in (".card .name", ".card .host", ".vs .name", ".rate .nm", ".feed a", ".feed small", ".pick label"):
        line = next(x for x in style.splitlines() if x.startswith(rule + " {"))
        assert "ellipsis" not in line and "nowrap" not in line, line
    assert ".feed { list-style: none; margin: 0; padding: 0; }" in style
    assert ".dock-body { padding: 12px 16px 16px; min-width: 0; }" in style
    assert "grid-auto-flow: column" not in style and "scroll-snap" not in style
    assert "sheet" not in page
    # the extras on Ask are tabs in one panel under the answers, the open one shown in place
    ask = page[page.index('id="tab-ask"'):page.index('id="tab-race"')]
    for panel in ("which", "frontier", "rates", "every", "more-options", "how"):
        assert f'data-dock="{panel}"' in ask and f'id="{panel}"' in ask
    assert '<details class="more"' not in page
    # charts have a height of their own instead of filling what is left of the window
    assert ".chart.fill { position: relative; height: 360px; }" in style
    # a model's details open in a drawer outside the views, so they show over any view
    assert page.index('id="detail"') > page.index("</main>")


def test_req_s36_about_rows_and_the_prompt_box(tmp_path):
    page = page_for(tmp_path)
    about = page[page.index('id="tab-about"'):page.index("</main>")]
    # About is a short line and rows that open on a click, all closed at first
    assert about.count("<details") == about.count("<summary>") == 3
    assert "<details open" not in about and "<section" not in about[1:]
    app = (Path(page_module.__file__).parent / "app.js").read_text()
    # a part a copy of the page adds to About (with a heading of its own) becomes one more closed row,
    # and a link marked data-scope opens it
    assert 'document.querySelectorAll("#tab-about > section")' in app
    assert 'closest("a[data-scope]")' in app and "row.open = true" in app
    # the prompt box grows with the prompt (up to 40% of the window), and nothing is hidden to make room
    assert "ta.style.height = Math.min(ta.scrollHeight + 2" in app
    assert "tight" not in app and "tight" not in page


def test_req_s39_old_data_is_named_on_the_page(tmp_path):
    page = page_for(tmp_path)
    assert '<main>\n<p id="stale" class="stale" role="status" hidden></p>' in page
    app = (Path(page_module.__file__).parent / "app.js").read_text()
    assert "const STALE_DAYS = 3;" in app and "Date.parse(D.built || D.end)" in app
    assert "the daily rebuild has not run since" in app


def test_req_s20_tags_and_the_outlook_say_what_a_correction_is(tmp_path):
    app = (Path(page_module.__file__).parent / "app.js").read_text()
    assert 'likely: "likely correction"' in app and "function correctionNote()" in app
    assert "correctionNote() + " in app
    page = page_for(tmp_path)
    assert "<b>likely\ncorrections</b>" in page and "likely corrections are not counted" in page


def test_req_s40_a_failed_refresh_opens_one_issue_and_a_good_one_closes_it():
    flow = (Path(page_module.__file__).parents[2] / ".github" / "workflows" / "refresh.yml").read_text()
    job = flow[flow.index("  report:"):]
    assert "needs: [build, deploy]" in job and "if: always()" in job
    assert 'gh issue create --title "Daily refresh failed"' in job and '[ -z "$open" ]' in job
    assert 'gh issue close "$n"' in job and '[ "$BUILD" = "success" ] && [ "$DEPLOY" = "success" ]' in job


def test_req_s42_price_history_has_a_not_yet_priced_panel(tmp_path):
    page = page_for(tmp_path)
    view = page[page.index('id="tab-trends"'):page.index('id="tab-about"')]
    assert 'data-panel="unpriced"' in view and 'id="panel-unpriced"' in view
    assert 'id="unpriced-list"' in view and 'id="unpriced-timing"' in view
    app = (Path(page_module.__file__).parent / "app.js").read_text()
    assert "function renderUnpriced()" in app and "Arena could not be read for this build." in app
    assert '"cacheWrite"]' in app
    # each change in a model's timeline links the LiteLLM change behind it
    assert '"https://github.com/BerriAI/litellm/commit/" + esc(D.sources[e[6]])' in app.replace("'", '"')
    assert 'table(["Date", "Change", "Before", "After", "Source"], events, "timeline")' in app


def test_req_s36_table_headers_follow_the_theme(tmp_path):
    # table_protocol.js paints the sticky headers with var(--panel, #fff): without --panel, dark mode had white
    # headers with light grey text
    style = page_for(tmp_path).split("</style>")[0]
    assert "--panel: var(--card);" in style
    proto = (Path(page_module.__file__).parent / "table_protocol.js").read_text()
    assert "background:var(--panel" in proto

