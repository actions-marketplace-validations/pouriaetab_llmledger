import xml.etree.ElementTree as ET

from llmledger import feed

ATOM = "{http://www.w3.org/2005/Atom}"


def machine():
    return {
        "built": "2026-10-20T11:50:44+00:00",
        "sources": ["abc1234", "def5678"],
        "events": {
            "openai/gpt-5": [["2026-10-19", "price", "input_cost_per_token", 1.25e-06, 1e-06, "", 0],
                             ["2026-09-01", "added", "", None, None, "", 1]],
            "fireworks_ai/inkling": [["2026-10-20", "deprecation", "deprecation_date", None, "2026-11-07", "", 1]],
            "old/model": [["2026-01-01", "removed", "", None, None, "bulk", 0]],
        },
    }


def test_req_s49_one_entry_a_day_newest_first_with_counts_and_commit_links():
    root = ET.fromstring(feed.build(machine()))
    entries = root.findall(ATOM + "entry")
    titles = [e.find(ATOM + "title").text for e in entries]
    assert titles == ["20 October 2026: 1 retirement date", "19 October 2026: 1 price change"]
    content = entries[1].find(ATOM + "content").text
    assert "openai/gpt-5: input $1.25 &rarr; $1.00 per 1M" in content
    assert "https://github.com/BerriAI/litellm/commit/abc1234" in content
    assert all(e.find(ATOM + "updated").text.endswith("T00:00:00Z") for e in entries)


def test_req_s49_only_the_last_14_days_and_a_flag_is_shown():
    m = machine()
    m["events"]["openai/gpt-5"].append(["2026-10-18", "price", "output_cost_per_token", 1e-05, 1e-03, "unit", 1])
    text = feed.build(m)
    assert "old/model" not in text and "2026-01-01" not in text
    assert "(unit)" in text


def test_req_s49_the_feed_is_well_formed_without_events():
    root = ET.fromstring(feed.build({"built": "2026-10-20T00:00:00+00:00", "sources": [], "events": {}}))
    assert root.findall(ATOM + "entry") == []
    assert root.find(ATOM + "updated").text == "2026-10-20T00:00:00+00:00"


def test_req_s49_a_price_table_and_a_price_per_query_or_image_are_shown_as_they_are():
    # LiteLLM's change of 28 October 2026 (3afe779125) gave Azure rows a web search price as a table
    # of context sizes; the refresh of 29 October stopped on it (issue #73).
    table = {"search_context_size_high": 0.014, "search_context_size_low": 0.014, "search_context_size_medium": 0.014}
    m = machine()
    m["events"]["azure/eu/gpt-4.1"] = [["2026-10-19", "price", "search_context_cost_per_query", None, table, "", 1]]
    m["events"]["openai/gpt-image-2"] = [["2026-10-19", "price", "input_cost_per_image", 0.04, 0.05, "", 1],
                                         ["2026-10-19", "price", "input_cost_per_pixel", 2.5e-06, 3e-06, "", 1],
                                         ["2026-10-19", "price", "input_cost_per_token", 5e-06, 4e-06, "", 1]]
    root = ET.fromstring(feed.build(m))
    content = root.findall(ATOM + "entry")[1].find(ATOM + "content").text
    assert ("azure/eu/gpt-4.1: search context cost per query none &rarr; "
            "{&quot;search_context_size_high&quot;: 0.014, &quot;search_context_size_low&quot;: 0.014, "
            "&quot;search_context_size_medium&quot;: 0.014} <a") in content
    assert ("openai/gpt-image-2: input cost per image $0.04 &rarr; $0.05, input cost per pixel $0.0000025 &rarr; "
            "$0.000003, input $5.00 &rarr; $4.00 per 1M tokens <a") in content
    assert "openai/gpt-5: input $1.25 &rarr; $1.00 per 1M" in content


def test_req_s49_every_price_value_has_a_text():
    assert feed.price("input_cost_per_token", 1.25e-06) == "$1.25"
    assert feed.price("input_cost_per_token", None) == "none"
    assert feed.price("output_cost_per_second", 0.1) == "$0.10"
    assert feed.price("input_cost_per_query", 0) == "$0"
    assert feed.price("tiered_pricing", [{"range": [0, 256000.0], "input_cost_per_token": 4e-07}]) == \
        '[{"range": [0, 256000.0], "input_cost_per_token": 4e-07}]'
    assert feed.price("input_cost_per_token", True) == "true"
    assert feed.price("input_cost_per_audio_token", 4e-05) == "$40.00"
    assert feed.price("output_cost_per_reasoning_token", 1.2e-05) == "$12.00"
