"""The day's data: downloaded once a day from the llmledger page into a cache folder, so the
plug-in works offline from the last copy, with a snapshot bundled in the package for the
very first run. Standard library only.

When a download fails, why and since when are kept next to the copy (download.json), so an
answer can say so, and the next try waits RETRY_AFTER instead of slowing every answer down."""
import gzip
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from importlib import resources
from pathlib import Path

URL = "https://pouriaetab.github.io/llmledger/data.json"
MAX_AGE = 24 * 3600
TIMEOUT = 20                                            # seconds without an answer from the page
DEADLINE = 60                                           # seconds for the whole download
RETRY_AFTER = 15 * 60                                   # after a failed download, wait this long


def cache_file():
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "llmledger-mcp" / "data.json"


def status_file():
    """Since when downloads fail, the last try and why; there only while they fail."""
    return cache_file().with_name("download.json")


def reason(error):
    """Why a download failed, in a few words: 'HTTP Error 404: Not Found', 'timed out'."""
    inner = error if isinstance(error, urllib.error.HTTPError) else getattr(error, "reason", None) or error
    return (str(inner) or type(inner).__name__)[:200]


def _download(url, dest):
    request = urllib.request.Request(url, headers={"User-Agent": "llmledger-mcp", "Accept-Encoding": "gzip"})
    start, parts = time.time(), []
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        while chunk := response.read(1 << 16):
            parts.append(chunk)
            if time.time() - start > DEADLINE:
                raise TimeoutError(f"the download took more than {DEADLINE} seconds")
        body = b"".join(parts)
        if response.headers.get("Content-Encoding") == "gzip":     # about 0.4 MB instead of 4.9 MB
            body = gzip.decompress(body)
    try:
        json.loads(body)                                # a broken download never replaces a good copy
    except ValueError:
        raise ValueError("what came back was not the day's data") from None
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as f:
        f.write(body)
    os.replace(f.name, dest)


def _bundled():
    return json.loads(gzip.decompress(resources.files("llmledger_mcp").joinpath("snapshot.json.gz").read_bytes()))


def _failing():
    try:
        status = json.loads(status_file().read_text())
        return status if all(isinstance(status.get(k), (int, float)) for k in ("since", "tried")) else None
    except (OSError, ValueError, AttributeError):       # none yet, or not what this version writes
        return None


def load(now=None):
    """(data, where it came from, None or why it is not today's download: {"error", "since", "tried"}).
    LLMLEDGER_DATA may name a local file or another address."""
    override = os.environ.get("LLMLEDGER_DATA", "")
    if override and not re.match(r"https?://", override):
        return json.loads(Path(override).read_text()), "file " + override, None
    url, dest = override or URL, cache_file()
    now = now or time.time()
    fresh = dest.exists() and now - dest.stat().st_mtime < MAX_AGE
    trouble = None
    if not fresh:
        trouble = _failing()
        if not (trouble and 0 <= now - trouble.get("tried", 0) < RETRY_AFTER):   # failed a moment ago: wait
            try:
                _download(url, dest)
                fresh, trouble = True, None
                status_file().unlink(missing_ok=True)
            except Exception as error:                  # offline or the page is down: use what we have
                trouble = {"error": reason(error), "since": (trouble or {}).get("since", now), "tried": now}
                try:
                    status_file().parent.mkdir(parents=True, exist_ok=True)
                    status_file().write_text(json.dumps(trouble))
                except OSError:
                    pass
    if dest.exists():
        try:
            where = "downloaded" if fresh else "the last download (could not refresh it)"
            return json.loads(dest.read_text()), where, trouble
        except ValueError:
            pass
    try:
        return _bundled(), "the copy bundled with this version", trouble
    except (FileNotFoundError, ModuleNotFoundError):    # the Agent Skill carries no copy
        why = f" ({trouble['error']})" if trouble else ""
        raise RuntimeError(f"No data yet: {url} could not be downloaded{why} and no copy is saved. "
                           "Check the internet connection and try again.") from None


class Shelf:
    """The data, indexed: models by listing and by grouped name, ratings by task."""

    def __init__(self, data, where="", trouble=None):
        self.data, self.where, self.trouble, self.loaded = data, where, trouble, time.time()
        self.models = [m for m in data["models"]]
        self.by_key = {m["key"]: m for m in self.models}
        self.groups = {}
        for m in self.models:
            self.groups.setdefault(m["maker"] + " / " + m["name"], []).append(m)
        ratings = data.get("ratings") or {}
        self.labels = dict(ratings.get("labels") or [])
        self.ratings = ratings.get("tasks") or {}
        self.rating_date = ratings.get("date", "")

    @staticmethod
    def norm(text):
        text = str(text).lower()
        text = re.sub(r"(\d)[-_p](?=\d(?![\d.bkm]))", r"\1.", text)   # 4-5 and 4p5 are versions: 4.5
        return re.sub(r"[-_:/@\s]+", " ", re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)).strip()

    def resolve(self, name):
        """The grouped name ("maker / name") for what a person typed, or a list of close ones."""
        if name in self.groups:
            return name, []
        if name in self.by_key:
            m = self.by_key[name]
            return m["maker"] + " / " + m["name"], []
        want = self.norm(name)
        exact = [g for g in self.groups if self.norm(g) == want or self.norm(g.split(" / ", 1)[1]) == want]
        if exact:
            return exact[0], []
        words = want.split()
        close = [g for g in self.groups
                 if all(any(t.startswith(w) for t in self.norm(g + " " + " ".join(m["key"] for m in self.groups[g])).split())
                        for w in words)]
        if len(close) == 1:
            return close[0], []
        close.sort(key=lambda g: (-self.rating_of("overall", g)[2] if self.rating_of("overall", g) else 0, len(g)))
        return None, close[:8]

    def rating_of(self, task, group):
        return next((r for r in self.ratings.get(task, []) if r[0] == group), None)

    def rank_of(self, task, group, priced):
        rows = [r for r in self.ratings.get(task, []) if r[0] in priced]
        ids = [r[0] for r in rows]
        return (ids.index(group) + 1 if group in ids else None), len(ids)
