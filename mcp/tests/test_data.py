"""The day's download, against fake llmledger pages on this computer: a good one, a failing one, a slow one
and one that sends gzip. No internet.

Nov 14, 2026: the plug-in answered from a 10 day old copy, did not say why the download failed, and blamed
the daily rebuild, though the page had been rebuilt that day."""
import gzip
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from llmledger_mcp import data, tools

FIXTURE = Path(__file__).with_name("fixture.json")


class Page:
    """A fake llmledger page on 127.0.0.1. mode: "ok", "fail" (HTTP 500), "slow" (answers after 2 s), "gzip"
    or "html" (a sign in page in place of the data, as some networks send)."""

    def __init__(self, mode):
        self.mode, self.asked = mode, []
        page = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                page.asked.append(self.headers.get("Accept-Encoding"))
                try:
                    if page.mode == "fail":
                        self.send_error(500, "Internal Server Error")
                        return
                    if page.mode == "slow":
                        time.sleep(2)
                    body = b"<html>Sign in to use this network</html>" if page.mode == "html" else FIXTURE.read_bytes()
                    self.send_response(200)
                    if page.mode == "gzip" and "gzip" in (self.headers.get("Accept-Encoding") or ""):
                        body = gzip.compress(body)
                        self.send_header("Content-Encoding", "gzip")
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):      # the slow page's caller gave up
                    pass

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/data.json"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def page(tmp_path, monkeypatch):
    pages = []

    def start(mode="ok"):
        pages.append(Page(mode))
        monkeypatch.setenv("LLMLEDGER_DATA", pages[-1].url)
        return pages[-1]
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(name, "127.0.0.1,localhost")
    yield start
    for p in pages:
        p.close()


def test_the_download_asks_for_gzip_and_unpacks_it(page):
    p = page("gzip")
    d, where, trouble = data.load()
    assert where == "downloaded" and trouble is None and d == json.loads(FIXTURE.read_text())
    assert p.asked == ["gzip"]
    assert json.loads(data.cache_file().read_text()) == d          # the copy on disk is plain JSON


def test_a_failed_download_says_why_and_waits_before_the_next_try(page):
    p = page("ok")
    data.load()                                                     # a good copy from today
    p.mode = "fail"
    later = time.time() + 2 * data.MAX_AGE                          # two days on: the copy is old
    d, where, trouble = data.load(now=later)
    assert where == "the last download (could not refresh it)" and d["models"]
    assert trouble == {"error": "HTTP Error 500: Internal Server Error", "since": later, "tried": later}
    assert json.loads(data.status_file().read_text()) == trouble    # kept for the next process (the skill's script)
    assert len(p.asked) == 2
    # a minute later: no new try, the same reason
    assert data.load(now=later + 60)[2] == trouble and len(p.asked) == 2
    # after RETRY_AFTER: tried again, and the failures still count from the first one
    again = data.load(now=later + data.RETRY_AFTER + 1)[2]
    assert len(p.asked) == 3 and again["since"] == later and again["tried"] == later + data.RETRY_AFTER + 1
    # the page answers again: today's data, and nothing kept about the failures
    p.mode = "ok"
    d, where, trouble = data.load(now=later + 2 * data.RETRY_AFTER + 2)
    assert where == "downloaded" and trouble is None and not data.status_file().exists() and len(p.asked) == 4


def test_a_page_that_is_not_the_data_never_replaces_the_copy(page):
    p = page("ok")
    good = data.load()[0]
    p.mode = "html"
    d, where, trouble = data.load(now=time.time() + 2 * data.MAX_AGE)
    assert d == good and trouble["error"] == "what came back was not the day's data"


def test_a_slow_page_times_out_and_the_bundled_copy_answers(page, monkeypatch):
    monkeypatch.setattr(data, "TIMEOUT", 0.3)
    page("slow")
    start = time.time()
    d, where, trouble = data.load()
    assert time.time() - start < 1.5
    assert where == "the copy bundled with this version" and d["models"] and trouble["error"] == "timed out"


def test_no_copy_at_all_says_why_the_download_failed(page, monkeypatch):
    monkeypatch.setattr(data, "_bundled", lambda: (_ for _ in ()).throw(FileNotFoundError()))   # the skill has none
    page("fail")
    with pytest.raises(RuntimeError, match=r"could not be downloaded \(HTTP Error 500: Internal Server Error\)"):
        data.load()


def test_a_broken_status_file_is_not_a_crash(page):
    page("ok")
    data.status_file().parent.mkdir(parents=True, exist_ok=True)
    data.status_file().write_text('{"since": "yesterday"}')
    assert data.load()[1:] == ("downloaded", None)


def test_answers_say_why_the_copy_is_old_and_do_not_blame_the_rebuild():
    raw = json.loads(FIXTURE.read_text())
    built = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    since = datetime(2026, 11, 5, 14, 2, tzinfo=timezone.utc).timestamp()
    trouble = {"error": "The read operation timed out", "since": since, "tried": since}
    old_copy = tools.footer(data.Shelf(dict(raw, built=built), "the last download (could not refresh it)", trouble))
    assert old_copy["data"]["offline"] == (
        f"Today's data could not be downloaded: answering from the last download (could not refresh it), prices as of "
        f"{built[:10]}. The download has failed since 2026-11-05 14:02 UTC: The read operation timed out. "
        "It is tried again after 15 minutes.")
    assert old_copy["data"]["warning"] == (
        "This copy is 10 days old because a newer one could not be downloaded, so prices, ratings and changes may be "
        "out of date. The llmledger page itself may be newer.")
    # downloaded today but old: then the page itself has not been rebuilt
    old_page = tools.footer(data.Shelf(dict(raw, built=built), "downloaded"))["data"]
    assert "offline" not in old_page and old_page["warning"].startswith(
        "This data is 10 days old: the llmledger page has not been rebuilt since")


def test_the_plugin_looks_again_soon_when_it_answers_from_an_old_copy(monkeypatch):
    from llmledger_mcp import server
    monkeypatch.setenv("LLMLEDGER_DATA", str(FIXTURE))
    raw = json.loads(FIXTURE.read_text())
    old = data.Shelf(raw, "the last download (could not refresh it)")
    old.loaded = time.time() - data.RETRY_AFTER - 1
    monkeypatch.setattr(server, "_SHELF", old)
    assert server.shelf() is not old and server.shelf().where == "file " + str(FIXTURE)
    today = data.Shelf(raw, "downloaded")
    today.loaded = time.time() - data.RETRY_AFTER - 1
    monkeypatch.setattr(server, "_SHELF", today)
    assert server.shelf() is today                                  # today's download is kept for a day
