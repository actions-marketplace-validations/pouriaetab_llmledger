import pytest

from llmledger import guard, pipeline


def build(listed, removed=0, end="2026-10-17T06:56:22+00:00"):
    return {"end": end, "models": [["m"] * 5 + ["listed"]] * listed + [["m"] * 5 + ["removed"]] * removed}


LIVE = build(1000, 200)


def test_req_s38_a_normal_day_passes():
    assert guard.problems(build(1010, 210, end="2026-10-18T06:00:00+00:00"), LIVE) == []
    assert guard.problems(build(800, 400), LIVE) == []           # a big clean up: 20% of the listed models


def test_req_s38_a_step_back_is_named():
    assert guard.problems(build(1000, 180), LIVE) == ["it knows 1,180 models, the live page 1,200"]
    assert guard.problems(build(1000, 200, end="2026-10-16T00:00:00+00:00"), LIVE) == [
        "its data ends 2026-10-16T00:00:00+00:00, before the live page's 2026-10-17T06:56:22+00:00"]
    assert guard.problems(build(740, 460), LIVE) == ["it lists 740 models, the live page 1,000"]


def test_req_s38_a_broken_build_is_not_published(monkeypatch):
    monkeypatch.delenv("LLMLEDGER_SKIP_LIVE_CHECK", raising=False)
    monkeypatch.setattr(guard, "live", lambda url: LIVE)
    with pytest.raises(SystemExit, match="nothing was published: it knows 120 models"):
        guard.check(build(100, 20), "https://example.org/data.js")
    guard.check(build(1000, 200), "https://example.org/data.js")
    monkeypatch.setenv("LLMLEDGER_SKIP_LIVE_CHECK", "1")
    guard.check(build(100, 20), "https://example.org/data.js")     # on purpose, for example after a history rewrite


def test_req_s38_no_live_page_means_nothing_to_compare(monkeypatch):
    monkeypatch.delenv("LLMLEDGER_SKIP_LIVE_CHECK", raising=False)
    monkeypatch.setattr(guard.arena, "_get_text", lambda url: (_ for _ in ()).throw(OSError("offline")))
    assert guard.live("https://example.org/data.js") is None
    guard.check(build(1, 0), "https://example.org/data.js")
    page = 'window.LLMLEDGER = {"end": "2026-10-17", "models": []};\n'
    monkeypatch.setattr(guard.arena, "_get_text", lambda url: page)
    assert guard.live("https://example.org/data.js") == {"end": "2026-10-17", "models": []}
    reads = iter([OSError("cut off"), page])                      # a read cut off half way is tried again

    def flaky(url):
        got = next(reads)
        if isinstance(got, Exception):
            raise got
        return got
    monkeypatch.setattr(guard.arena, "_get_text", flaky)
    assert guard.live("https://example.org/data.js") == {"end": "2026-10-17", "models": []}


def test_req_s38_the_pipeline_checks_before_it_writes_the_page():
    source = __import__("inspect").getsource(pipeline.main)
    assert source.index("guard.check(data") < source.index("page.main(")
