from datetime import datetime, timezone

from llmledger.catalog import model_records, recent, sources
from llmledger.flags import mark


def row(day, model, kind, field="", old="null", new="null"):
    return {
        "when": f"2026-01-{day:02d}T12:00:00+00:00",
        "sha": "x", "model": model, "kind": kind,
        "field": field, "old": old, "new": new,
    }


ROWS = [
    row(1, "c", "start"),
    row(1, "a", "added"),
    row(2, "b", "added"),
    row(3, "b", "price", "input_cost_per_token", "null", "1e-06"),
    row(5, "a", "price", "input_cost_per_token", "2e-06", "1e-06"),
    row(9, "a", "removed"),
]
LAST = {"a": {"litellm_provider": "openai", "input_cost_per_token": 1e-06,
              "supports_vision": True, "supports_reasoning": False,
              "max_input_tokens": 128000, "input_cost_per_image": 0.002},
        "b": {"litellm_provider": "azure", "input_cost_per_token": 1e-06}}
END = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)


def test_records_describe_each_model():
    records, events = model_records(ROWS, LAST, END)
    a, b, c = records
    assert a[0] == "a" and a[5] == "removed" and a[7] == "2026-01-09"
    assert a[11] == 1 and a[13] == "price" and a[14] is None
    assert b[5] == "listed" and b[9] == 1.0 and b[11] == 0
    assert b[14] == 8.0
    assert c[6] == "" and c[14] is None
    assert len(events["a"]) == 3


def test_req_s19_last_seven_days_lists_every_change():
    rows = recent(ROWS, END, days=7)
    assert [(r[0], r[1], r[2]) for r in rows] == [
        ("2026-01-05", "a", "price"),
        ("2026-01-09", "a", "removed"),
    ]


def test_req_s20_corrections_are_tagged_and_not_counted():
    rows = mark([
        row(1, "a", "added"),
        row(2, "a", "price", "input_cost_per_token", "1e-06", "0.0001"),       # 100 times: a unit fix
        row(3, "a", "price", "input_cost_per_token", "0.0001", "0.00012"),     # in its first week: likely
        row(20, "a", "price", "input_cost_per_token", "0.00012", "0.00024"),   # later and twice: counted
    ])
    records, events = model_records(rows, {}, END)
    assert records[0][11] == 1
    assert [e[5] for e in events["a"]] == ["", "unit", "likely", ""]
    assert [r[6] for r in recent(rows, END, days=30)] == ["", "unit", "likely", ""]


def test_req_s24_records_carry_skills_size_and_media_prices():
    records, _ = model_records(ROWS, LAST, END)
    a, b, _ = records
    assert a[15] == ["vision"] and a[16] == 128000 and a[17] == {"in_img": 0.002}
    assert b[15] == [] and b[16] is None and b[17] is None


def test_req_s29_records_carry_cache_price_and_effort_levels():
    last = {"a": {"supports_reasoning": True, "supports_xhigh_reasoning_effort": True,
                  "supports_max_reasoning_effort": True, "supports_none_reasoning_effort": False,
                  "cache_read_input_token_cost": 2e-07},
            "b": {"supports_reasoning": True, "reasoning_effort_levels": ["max", "Low", "high"],
                  "default_reasoning_effort": "high"},
            "c": {"supports_reasoning": True, "reasoning_effort_levels": []}}
    a, b, c = model_records(ROWS, last, END)[0]
    assert a[18] == 0.2 and a[19] == ["low", "medium", "high", "xhigh", "max"] and a[20] == ""
    assert b[18] is None and b[19] == ["low", "high", "max"] and b[20] == "high"
    assert c[19] is None and c[20] == ""
    records, _ = model_records(ROWS, LAST, END)
    assert records[0][19] is None and records[1][19] is None   # does not think, or not said


def test_req_s43_each_change_keeps_the_litellm_commit_and_cache_write_price():
    rows = [dict(r, sha=f"{n:040x}") for n, r in enumerate(ROWS)]
    last = {"a": {"cache_creation_input_token_cost": 3.75e-06}, "b": {}}
    records, events = model_records(rows, last, END)
    assert records[0][21] == 3.75 and records[1][21] is None              # cache write per 1M tokens
    assert events["a"][1][6] == f"{4:040x}"[:12]                          # the commit that made the change
    commits = sources(events)
    assert events["a"][1][6] == commits.index(f"{4:040x}"[:12])           # written once, then a place in the list
    assert len(commits) == len({r["sha"][:12] for r in rows})
    assert sources(events) == []                                          # already numbers: nothing left to do

