import json

from llmledger import badges


def test_req_s52_a_badge_per_listed_model_with_prices_outlook_and_retirement(tmp_path):
    machine = {"models": [
        {"key": "gpt-5", "name": "gpt-5", "input": 1.25, "output": 10.0, "retire": None,
         "outlook": {"90": {"price": [0.045, 0.03, 0.06]}}},
        {"key": "azure/eu/gpt-5", "name": "gpt-5", "input": 1.25, "output": 10.0, "retire": None,
         "outlook": {"90": {"price": [0.12, 0.1, 0.15]}}},
        {"key": "host/old:1", "name": "old", "input": 0.05, "output": None, "retire": "2026-12-01", "outlook": None},
    ]}
    assert badges.write(tmp_path, machine) == 3
    b = json.load(open(tmp_path / "gpt-5.json"))
    assert b["schemaVersion"] == 1 and b["label"] == "gpt-5" and b["color"] == "2a78d6"
    assert b["message"] == "$1.25 / $10.00 per 1M · 4.5% chance of a price change in 90 days"
    assert json.load(open(tmp_path / "azure--eu--gpt-5.json"))["color"] == "eda100"
    old = json.load(open(tmp_path / "host--old-1.json"))
    assert old["message"] == "$0.0500 / – per 1M · retirement date 2026-12-01" and old["color"] == "eb6834"


def test_req_s52_the_slug_is_safe_for_a_file_and_an_address():
    assert badges.slug("bedrock/us-east-1/anthropic.claude-3-5-sonnet-20241022-v2:0") == \
        "bedrock--us-east-1--anthropic.claude-3-5-sonnet-20241022-v2-0"
