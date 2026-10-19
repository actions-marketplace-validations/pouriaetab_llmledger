from llmledger import trends

D1, D2 = "2025-01-01", "2026-01-10"


def row(name, maker, rating, day, open_=False):
    return {"name": name, "maker": maker, "open": open_, "rating": rating, "date": day}


ROWS = [
    row("gpt-5", "openai", 1300, D1), row("qwen3", "alibaba", 1250, D1, True),
    row("llama-4", "meta", 1200, D1, True), row("small-model", "x", 1100, D1),
    row("claude-opus-4-6", "anthropic", 1350, D2), row("gpt-5", "openai", 1310, D2),
    row("qwen3", "alibaba", 1290, D2, True), row("Llama 4", "meta", 1220, D2, True),
    row("small-model", "x", 1100, D2),
]
# [key, maker, name, host, mode, status, added, removed, retire, input $/1M, output $/1M]
RECORDS = [
    ["openai/gpt-5", "openai", "gpt-5", "openai", "chat", "listed", "2024-12-01", "", "", 1.0, 10.0],
    ["azure/gpt-5", "openai", "gpt-5", "azure", "chat", "listed", "", "", "", 0.0, 0.0],
    ["anthropic/claude-opus-4.6", "anthropic", "claude-opus-4.6", "anthropic", "chat", "listed",
     "2025-12-01", "", "", 5.0, 25.0],
    ["qwen3", "alibaba", "qwen3", "together", "chat", "listed", "", "", "", 0.2, 0.6],
    ["meta/llama-4", "meta", "llama-4", "meta", "chat", "removed", "", "2025-06-01", "", 0.1, 0.1],
]
EVENTS = {
    "openai/gpt-5": [["2024-12-01", "added", "", None, None, ""],
                     ["2025-06-01", "price", "input_cost_per_token", 2e-6, 1e-6, ""]],
    "qwen3": [["2025-03-01", "price", "input_cost_per_token", 2e-5, 2e-7, "unit"]],
}


def test_req_s33_renamed_arena_models_keep_one_line():
    assert trends.same("Claude Opus 4.6 (High)") == trends.same("claude-opus-4-6-high") == "claude-opus-4-6-high"
    assert trends.same("Gemini 4 Argon (High)") == "gemini-4-argon-high"
    assert trends.same("gemini-2.5-pro") == trends.same("gemini-2-5-pro")
    assert trends.is_open("MIT") and trends.is_open("Llama 3.1 Community")
    assert not trends.is_open("Proprietary") and not trends.is_open("") and not trends.is_open(None)


def test_req_s33_a_price_is_rolled_back_to_the_day():
    gpt, free, claude, qwen, llama = RECORDS
    assert trends.price_at(gpt, EVENTS["openai/gpt-5"], D2) == (3 * 1.0 + 10.0) / 4
    assert trends.price_at(gpt, EVENTS["openai/gpt-5"], D1) == (3 * 2.0 + 10.0) / 4    # before the cut
    assert trends.price_at(gpt, EVENTS["openai/gpt-5"], "2024-11-30") is None          # not listed yet
    assert trends.price_at(free, [], D1) is None                                        # free is not a price
    assert trends.price_at(claude, [], D1) is None
    assert abs(trends.price_at(qwen, EVENTS["qwen3"], D1) - 0.3) < 1e-9                # a unit fix is not undone
    assert trends.price_at(llama, [], D1) == 0.1 and trends.price_at(llama, [], D2) is None   # removed


def test_req_s33_lines_makers_and_the_price_race():
    out = trends.build(ROWS, RECORDS, EVENTS)
    names = out["names"]
    assert out["dates"] == [D1, D2] and out["date"] == D2 and out["mix"] == [3, 1]
    lines = {names[n]: (out["makers"][m], o, pts) for n, m, o, pts in out["lines"]}
    assert set(lines) == {"gpt-5", "qwen3", "Llama 4", "small-model", "claude-opus-4-6"}
    assert lines["Llama 4"] == ("meta", 1, [0, 1200, 1, 1220])           # one line under its newest name
    assert out["makers"][:5] == ["alibaba", "meta", "openai", "x", "anthropic"]   # most often in the top 5 first
    best = {out["makers"][m]: pts for m, pts in out["best"]}
    assert best["anthropic"] == [1, 1350, names.index("claude-opus-4-6")]
    first, second = out["race"]
    assert first[:6] == [0, 4.0, names.index("gpt-5"), 1, 0.1, names.index("Llama 4")]   # newest name
    assert first[6:] == [None, None, None, None]                         # no leaderboard a year earlier
    assert second[:6] == [1, 10.0, names.index("claude-opus-4-6"), 1, 0.3, names.index("qwen3")]
    # last year's first (gpt-5, 4.00 then) is matched today by gpt-5 itself at 3.25
    assert second[6:] == [3.25, names.index("gpt-5"), names.index("gpt-5"), 4.0]


def test_req_s33_no_history_means_no_trends(monkeypatch):
    assert trends.build([], RECORDS, EVENTS) is None
    assert trends.fetch("file:///nowhere/full.parquet") is None


def test_req_s33_yesterdays_trends_are_kept_when_arena_is_down(monkeypatch):
    page = 'window.LLMLEDGER = {"models": [], "trends": {"date": "2026-10-15", "dates": []}};\n'
    monkeypatch.setattr(trends.arena, "_get_text", lambda url: page)
    assert trends.previous("https://example.org/data.js")["date"] == "2026-10-15"
    monkeypatch.setattr(trends.arena, "_get_text", lambda url: (_ for _ in ()).throw(OSError("down")))
    assert trends.previous("https://example.org/data.js") is None


def test_req_s33_a_likely_correction_is_not_rolled_back():
    record = ["x/m", "x", "m", "x", "chat", "listed", "2025-01-01", "", "", 1.0, 4.0]
    events = [["2025-01-01", "added", "", None, None, ""],
              ["2025-01-03", "price", "input_cost_per_token", 1e-5, 1e-6, "likely"],   # a typo fixed in week one
              ["2025-06-01", "price", "output_cost_per_token", 2e-6, 4e-6, ""]]       # a real increase
    assert trends.price_at(record, events, "2025-01-02") == trends.blend(1.0, 2.0)
    assert trends.price_at(record, events, "2025-07-01") == trends.blend(1.0, 4.0)


def test_req_s33_a_change_with_its_source_rolls_back_the_same():
    record = ["x/m", "x", "m", "x", "chat", "listed", "2025-01-01", "", "", 1.0, 4.0]
    events = [["2025-01-01", "added", "", None, None, "", 0],
              ["2025-06-01", "price", "output_cost_per_token", 2e-6, 4e-6, "", 1]]
    assert trends.price_at(record, events, "2025-03-01") == trends.blend(1.0, 2.0)

