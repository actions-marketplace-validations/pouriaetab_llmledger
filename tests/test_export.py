from datetime import datetime, timezone

from llmledger import export

CURVES = {"all": {"90": [[0, 100, 0.1, 0.05, 0.15, 0.02, 0.01, 0.03, 0.03, 0.02, 0.04, 0.85, 0.8, 0.9],
                         [7, 90, 0.08, 0.04, 0.12, 0.02, 0.01, 0.03, 0.02, 0.01, 0.03, 0.88, 0.83, 0.93]],
                  "365": []}}


def record(key, status="listed", added="2026-01-01", exit_="", age=9.5, host="openai"):
    return [key, "openai", key, host, "chat", status, added, "", "", 1.0, 2.0, 0, "2026-01-01", exit_, age,
            ["tools"], 128000, None, 0.1, ["low", "medium", "high"], "medium"]


DATA = {"models": [record("a"), record("b", status="removed"), record("c", exit_="price", age=None)],
        "events": {"a": [["2026-01-01", "added", "", None, None, ""]], "b": [], "c": []},
        "curves": CURVES,
        "arena": {"date": "2026-10-15", "source": "s", "labels": [["overall", "Everything"]],
                  "tasks": {"overall": [["openai / a", "a", 1500.0, 1490.0, 1510.0, 1000, 1]]}}}
INFO = {"built": datetime(2026, 10, 16, tzinfo=timezone.utc), "sha": "abc",
        "when": datetime(2026, 10, 15, tzinfo=timezone.utc)}


def test_req_s31_data_json_lists_listed_models_with_prices_and_outlook():
    out = export.machine(DATA, INFO)
    assert out["schema"] == 1 and [m["key"] for m in out["models"]] == ["a", "c"]
    a = out["models"][0]
    assert a["input"] == 1.0 and a["cache_read"] == 0.1 and a["context"] == 128000
    assert a["effort"] == ["low", "medium", "high"] and a["effort_default"] == "medium"
    # 9.5 days old: the row for models that reached 7 days without a change
    assert a["outlook"]["90"] == {"followed": 90, "price": [0.08, 0.04, 0.12], "retirement": [0.02, 0.01, 0.03],
                                  "removed": [0.02, 0.01, 0.03], "none": [0.88, 0.83, 0.93]}
    assert a["outlook"]["group"] == "all" and "365" not in a["outlook"]
    assert out["models"][1]["outlook"] is None          # already changed once
    assert set(out["events"]) == {"a", "c"} and out["ratings"]["tasks"]["overall"][0][2] == 1500.0
    assert "MIT" in out["credits"]["prices"] and "CC BY 4.0" in out["credits"]["ratings"]
