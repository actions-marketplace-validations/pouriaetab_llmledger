from datetime import datetime, timedelta

from llmledger import guard_effect, makers

T0 = datetime(2026, 1, 5)


def row(model, kind, day, field="input_cost_per_token", old="1e-06", new="2e-06", flag=""):
    return {"when": (T0 + timedelta(days=day)).isoformat(), "sha": "x", "model": model, "kind": kind,
            "field": field, "old": old, "new": new, "flag": flag}


def catalogue():
    """120 claude models, 90 reprice on day 30; 120 gpt models, 90 are removed on day 60; 5 others."""
    rows = []
    for i in range(120):
        rows += [row(f"claude-{i}", "added", 0)] + ([row(f"claude-{i}", "price", 30)] if i < 90 else [])
        rows += [row(f"gpt-{i}", "added", 0)] + ([row(f"gpt-{i}", "removed", 60, old="null", new="null")] if i < 90 else [])
    for i in range(5):
        rows.append(row(f"mystery-{i}", "added", 0))
    return rows


def test_req_s53_incidence_by_maker_with_small_makers_pooled():
    end = T0 + timedelta(days=400)
    result = makers.build(catalogue(), end, resamples=50)
    by = {r["maker"]: r for r in result["rows"]}
    # the 5 others are too few to be followed at a year, so their pooled row is left out
    assert set(by) == {"anthropic", "openai", "all makers"}
    assert by["anthropic"]["models"] == 120 and by["anthropic"]["year"]["price"][0] == 0.75
    assert by["openai"]["year"]["removed"][0] == 0.75 and by["openai"]["year"]["price"][0] == 0.0
    assert by["anthropic"]["year"]["followed"] == 30
    assert by["all makers"]["models"] == 245
    assert abs(by["all makers"]["year"]["price"][0] - 90 / 245) < 1e-4   # rounded to 4 places
    spread = makers.spread(result)
    assert spread["high"][0] == "anthropic" and spread["low"][0] == "openai"


def test_req_s53_a_maker_row_needs_20_models_still_followed():
    rows = []
    for i in range(110):
        rows += [row(f"claude-{i}", "added", 0), row(f"claude-{i}", "removed", 10, old="null", new="null")]
    result = makers.build(rows, T0 + timedelta(days=400), resamples=20)
    assert [r["maker"] for r in result["rows"]] == ["all makers"]


def guarded(before_share, after_share, weeks_before=10, weeks_after=10, per_week=100):
    rows, day = [], guard_effect.GUARD_DAY - timedelta(weeks=weeks_before)
    i = 0
    for w in range(weeks_before + weeks_after):
        share = before_share if w < weeks_before else after_share
        for k in range(per_week):
            tag = "likely" if k < share * per_week else ""
            rows.append({"when": datetime.combine(day + timedelta(weeks=w, days=1), datetime.min.time()).isoformat(),
                         "model": f"m{i}", "kind": "price", "field": "input_cost_per_token", "old": "1e-06",
                         "new": "2e-06", "flag": tag, "sha": "x"})
            i += 1
    return rows


def test_req_s54_the_guard_series_counts_each_weeks_changes_and_tags():
    series = guard_effect.weeks(guarded(0.2, 0.2, weeks_before=3, weeks_after=2))
    assert len(series) == guard_effect.WEEKS_BEFORE + 2
    assert [n for _, n, _ in series][-5:] == [100] * 5 and [c for _, _, c in series][-5:] == [20] * 5
    assert all(n == 0 for _, n, _ in series[:-5])


def test_req_s54_a_real_drop_is_found_and_no_change_is_called_no_change():
    drop = guard_effect.build(guarded(0.4, 0.1), resamples=100)
    assert drop["reading"] == "fewer corrections after the guard"
    assert drop["share_before"] == 0.4 and drop["share_after"] == 0.1
    assert drop["difference"][2] < 0 and drop["step_odds_ratio"][2] < 1
    same = guard_effect.build(guarded(0.2, 0.2), resamples=100)
    assert same["reading"] == "no change the data can show"
    assert same["difference"][1] <= 0 <= same["difference"][2]


def test_req_s54_too_few_weeks_gives_nothing():
    assert guard_effect.build(guarded(0.2, 0.2, weeks_before=1, weeks_after=1), resamples=10) is None
