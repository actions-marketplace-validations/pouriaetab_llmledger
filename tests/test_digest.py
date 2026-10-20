from llmledger import digest, export


def machine():
    return {
        "built": "2026-10-20T11:50:44+00:00",
        "index": {"date": "2026-10-15", "now_model": "flash", "now_price": 0.14, "then_model": "pro",
                  "then_price": 3.44, "times": 24.6, "unit": "dollars per 1M tokens"},
        "models": [
            {"key": "host/new-model", "maker": "acme", "name": "new-model", "added": "2026-10-18"},
            {"key": "other/new-model", "maker": "acme", "name": "new-model", "added": "2026-10-19"},
            {"key": "host/old-model", "maker": "acme", "name": "old-model", "added": "2025-01-01"},
        ],
        "events": {
            "host/new-model": [["2026-10-18", "added", "", None, None, "", 0]],
            "other/new-model": [["2026-10-19", "added", "", None, None, "", 0]],
            "host/old-model": [["2026-10-16", "price", "input_cost_per_token", 2e-06, 1e-06, "", 0],
                               ["2026-10-16", "price", "output_cost_per_token", 8e-06, 2e-06, "", 0],
                               ["2026-10-17", "price", "cache_read_input_token_cost", 1e-07, 2e-07, "", 0],
                               ["2026-10-01", "price", "input_cost_per_token", 4e-06, 2e-06, "", 0]],
            "host/fixed": [["2026-10-15", "price", "input_cost_per_token", 1e-08, 1e-06, "unit", 0]],
            "host/going": [["2026-10-14", "deprecation", "deprecation_date", None, "2026-12-01", "", 0]],
        },
        "ratings": {"tasks": {"overall": [["acme / new-model", "new", 1500, 1490, 1510, 1000, 3]]}},
    }


def test_req_s50_the_digest_counts_moves_arrivals_and_the_index():
    text = digest.build(machine())
    assert text.startswith("# This week in LLM prices (2026-10-13 to 2026-10-20)")
    assert "2 models added, 2 repriced, 1 got a retirement date, 0 removed" in text   # the count keeps corrections
    # token prices only, one line per model, both fields, the cut as a range; the old change and the unit fix left out
    assert "- host/old-model: input $2.00 to $1.00, output $8.00 to $2.00 per 1M (50 to 75% off)" in text
    assert "host/fixed" not in text and "cache" not in text
    assert "- host/going: 2026-12-01" in text
    # one arrival per grouped name, with its Arena rank
    assert text.count("acme / new-model") == 1 and "#3 for overall" in text
    assert "Top quality costs 24.6x less than a year ago" in text


def test_req_s50_the_index_comes_from_the_latest_leaderboard_with_both_prices():
    trends = {"dates": ["2025-10-01", "2026-10-01", "2026-10-15"],
              "names": ["pro", "flash"],
              "race": [[0, 3.0, 0, 1, 3.0, 0, None, None, None, None],
                       [1, 2.0, 0, 1, 1.0, 1, 0.5, 1, 0, 3.0],
                       [2, 2.0, 0, 1, 1.0, 1, None, None, None, None]]}
    idx = export.price_index(trends)
    assert idx["date"] == "2026-10-01" and idx["now_model"] == "flash" and idx["then_model"] == "pro"
    assert idx["now_price"] == 0.5 and idx["then_price"] == 3.0 and idx["times"] == 6.0
    assert export.price_index(None) is None and export.price_index({"race": []}) is None


def test_req_s50_a_quiet_week_still_reads():
    text = digest.build({"built": "2026-10-20T00:00:00+00:00", "models": [], "events": {}, "ratings": None})
    assert "0 models added, 0 repriced, 0 got a retirement date, 0 removed" in text
    assert "Biggest" not in text and "Not financial" in text
