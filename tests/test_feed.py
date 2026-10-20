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
