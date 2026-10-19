from datetime import date

from llmledger import unpriced


def arena_row(name, org, votes=1000, rating=1400.0):
    return {"model_name": name, "organization": org, "category": "overall", "rating": rating,
            "vote_count": votes, "leaderboard_publish_date": "2026-10-15"}


def seen(name, day):
    return {"name": name, "maker": "", "open": False, "rating": 1400.0, "date": day}


def record(key, maker, name, added):
    return [key, maker, name, "host", "chat", "listed", added]


RECORDS = [
    record("openai/gpt-early", "openai", "gpt-early", "2026-05-01"),       # priced before Arena showed it
    record("x/gpt-late", "openai", "gpt-late", "2026-06-11"),              # priced 10 days after
    record("old/gpt-old", "openai", "gpt-old", ""),                        # in the first catalogue version
    record("g/gemini-9-flash-preview", "google", "gemini-9-flash-preview", "2026-01-01"),
]
TABLES = {"text_style_control": [
    arena_row("gpt-early", "openai"), arena_row("gpt-late", "openai"), arena_row("gpt-old", "openai"),
    arena_row("brand-new (High)", "meta", votes=500), arena_row("brand-new (Max)", "meta", votes=900),
    arena_row("gemini-9-flash", "google"),                                # not matched, but a close name is priced
    arena_row("long-gone", "acme"),
    {**arena_row("gpt-early", "openai"), "category": "coding"},           # other categories are ignored
]}
HISTORY = [
    seen("gpt-old", "2024-08-28"),            # on Arena's first leaderboard: its first day is unknown
    seen("gpt-early", "2026-05-10"), seen("gpt-late", "2026-06-01"), seen("gpt-late", "2026-07-01"),
    seen("brand-new (Max)", "2026-10-13"), seen("brand-new-high", "2026-10-15"),
    seen("gemini-9-flash", "2026-09-01"), seen("long-gone", "2025-01-01"),
]
TODAY = date(2026, 10, 19)


def test_req_s42_close_names_for_names_the_rules_cannot_match():
    names = ["gemini-9-flash-preview", "nova-pro", "gpt-5.5", "muse-glimmer-30b", "abc"]
    assert unpriced.close_names("gemini-9-flash", names) == ["gemini-9-flash-preview"]
    assert unpriced.close_names("amazon-nova-pro-v1.0", names) == ["nova-pro"]
    assert unpriced.close_names("muse-glimmer", names) == ["muse-glimmer-30b"]
    assert unpriced.close_names("granite-4.2-30b", names) == []


def test_req_s42_recent_models_without_a_price():
    out = unpriced.build(TABLES, HISTORY, RECORDS, "2023-09-06", TODAY)
    assert out["date"] == "2026-10-15" and out["history_from"] == "2024-08-28"
    # one line for a model Arena lists at two effort levels: its earliest day and its most votes
    assert out["models"][0] == ["brand-new (Max)", "meta", "2026-10-13", 6, 900, 1400.0, []]
    assert [m[0] for m in out["models"]] == ["brand-new (Max)", "gemini-9-flash"]   # long-gone is over 180 days
    assert out["models"][1][6] == ["gemini-9-flash-preview"]
    assert out["not_priced"] == 3


def test_req_s42_how_soon_a_price_comes():
    out = unpriced.build(TABLES, HISTORY, RECORDS, "2023-09-06", TODAY)
    timing = out["timing"]
    # timed: gpt-early (0 days), gpt-late (10 days), brand-new (not priced, 6 days so far), long-gone (not priced);
    # gpt-old is left out (first day unknown), gemini-9-flash too (it may be priced under its close name)
    assert timing["models"] == 4 and timing["priced"] == 2 and timing["left_out_close_names"] == 1
    assert unpriced.MIN_AT_RISK > 4 and timing["within"] == {}          # too few to estimate in this small example
    makers = {r[0]: r for r in out["by_maker"]}
    assert makers == {}                                                  # no maker has 5 models here


def test_req_s42_estimates_on_enough_models():
    tables = {"text_style_control": [arena_row(f"m{i}", "acme") for i in range(40)]}
    history = [seen("on-the-first-board", "2024-08-28")] + [seen(f"m{i}", "2026-01-01") for i in range(40)]
    # 10 priced before, 20 priced 0 to 19 days after Arena first showed them, 10 never
    records = [record(f"h/m{i}", "acme", f"m{i}", "2025-12-01" if i < 10 else f"2026-01-{i - 9:02d}")
               for i in range(30)]
    out = unpriced.build(tables, history, records, "2023-09-06", TODAY)
    within = out["timing"]["within"]
    assert within["0"][0] == 11 / 40 and within["7"][0] == 18 / 40
    assert "30" not in within                         # only the 10 never priced are still followed: too few
    for low, high in ([v[1], v[2]] for v in within.values()):
        assert low <= high
    assert out["by_maker"] == [["acme", 40, 0.275, 10.0, 10]]


def test_req_s42_no_arena_means_no_list(monkeypatch):
    assert unpriced.build(None, HISTORY, RECORDS, "2023-09-06", TODAY) is None
    assert unpriced.build(TABLES, None, RECORDS, "2023-09-06", TODAY) is None
    page = 'window.LLMLEDGER = {"models": [], "unpriced": {"date": "2026-10-15"}};\n'
    monkeypatch.setattr(unpriced.arena, "_get_text", lambda url: page)
    assert unpriced.previous("https://example.org/data.js") == {"date": "2026-10-15"}
