"""The day's data: downloaded once a day from the llmledger page into a cache folder, so the
plug-in works offline from the last copy, with a snapshot bundled in the package for the
very first run. Standard library only."""
import gzip
import json
import os
import re
import tempfile
import time
import urllib.request
from importlib import resources
from pathlib import Path

URL = "https://pouriaetab.github.io/llmledger/data.json"
MAX_AGE = 24 * 3600


def cache_file():
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "llmledger-mcp" / "data.json"


def _download(url, dest):
    request = urllib.request.Request(url, headers={"User-Agent": "llmledger-mcp"})
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read()
    json.loads(body)                                    # a broken download never replaces a good copy
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as f:
        f.write(body)
    os.replace(f.name, dest)


def _bundled():
    return json.loads(gzip.decompress(resources.files("llmledger_mcp").joinpath("snapshot.json.gz").read_bytes()))


def load(now=None):
    """(data, where it came from). LLMLEDGER_DATA may name a local file or another address."""
    override = os.environ.get("LLMLEDGER_DATA", "")
    if override and not re.match(r"https?://", override):
        return json.loads(Path(override).read_text()), "file " + override
    url, dest = override or URL, cache_file()
    now = now or time.time()
    fresh = dest.exists() and now - dest.stat().st_mtime < MAX_AGE
    if not fresh:
        try:
            _download(url, dest)
            fresh = True
        except Exception:                               # offline or the page is down: use what we have
            pass
    if dest.exists():
        try:
            return json.loads(dest.read_text()), "downloaded" if fresh else "the last download (could not refresh it)"
        except ValueError:
            pass
    return _bundled(), "the copy bundled with this version"


class Shelf:
    """The data, indexed: models by listing and by grouped name, ratings by task."""

    def __init__(self, data, where=""):
        self.data, self.where, self.loaded = data, where, time.time()
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
