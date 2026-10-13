from llmledger import arena


def row(name, rating, category="overall", organization="", low=None, high=None):
    return {"model_name": name, "organization": organization, "rating": rating,
            "rating_lower": rating - 5 if low is None else low,
            "rating_upper": rating + 5 if high is None else high,
            "vote_count": 1000.0, "rank": 1, "category": category,
            "leaderboard_publish_date": "2026-10-09"}


def test_req_s25_arena_names_are_tried_longest_first():
    assert arena.candidates("qwen3.8-max") == ["qwen3.8-max", "qwen3.8"]
    assert arena.candidates("claude-opus-4-5-20251101-high-32k")[-1] == "claude-opus-4.5"
    assert arena.candidates("muse-spark-1.2 (xHigh)") == ["muse-spark-1.2"]
    assert arena.candidates("deepseek-v4-pro-high-preview")[-1] == "deepseek-v4-pro"


def test_req_s25_matching_prefers_the_arena_maker():
    groups = {"claude-opus-4.6": {"anthropic"}, "llama-4": {"meta", "other"}}
    assert arena.match("claude-opus-4-6-high", "anthropic", groups) == "anthropic / claude-opus-4.6"
    assert arena.match("llama-4", "meta", groups) == "meta / llama-4"
    assert arena.match("unknown-model-9", "x", groups) is None


def test_req_s25_best_variant_kept_and_unmatched_left_out():
    records = [["anthropic.claude-opus-4-6", "anthropic", "claude-opus-4.6"],
               ["openai/gpt-5.5", "openai", "gpt-5.5"]]
    tables = {"text_style_control": [
        row("claude-opus-4-6", 1490, organization="anthropic"),
        row("claude-opus-4-6-high", 1500, organization="anthropic"),
        row("gpt-5.5", 1480, organization="openai"),
        row("gpt-5.5", 1520, category="coding", organization="openai"),
        row("not-in-catalogue", 1600),
    ]}
    out = arena.build(tables, records)
    assert [r[:3] for r in out["tasks"]["overall"]] == [
        ["anthropic / claude-opus-4.6", "claude-opus-4-6-high", 1500],
        ["openai / gpt-5.5", "gpt-5.5", 1480]]
    assert out["tasks"]["coding"][0][:3] == ["openai / gpt-5.5", "gpt-5.5", 1520]
    assert out["tasks"]["vision"] == []
    assert (out["matched"], out["total"], out["date"]) == (3, 4, "2026-10-09")


def test_req_s25_arena_down_means_no_ratings(monkeypatch):
    def down(url, tries=4):
        raise OSError("no network")
    monkeypatch.setattr(arena, "_get", down)
    assert arena.fetch() is None


def test_req_s25_yesterdays_ratings_are_kept_when_arena_is_down(monkeypatch):
    page = 'window.LLMLEDGER = {"models": [], "arena": {"date": "2026-10-12", "tasks": {}}};\n'
    monkeypatch.setattr(arena, "_get_text", lambda url: page)
    assert arena.previous("https://example.org/data.js")["date"] == "2026-10-12"
    monkeypatch.setattr(arena, "_get_text", lambda url: (_ for _ in ()).throw(OSError("down")))
    assert arena.previous("https://example.org/data.js") is None
