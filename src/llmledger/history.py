import json
import subprocess
from datetime import datetime, timezone

FILE = "model_prices_and_context_window.json"
REF = "origin/main"
RESERVED = {"sample_spec", "fallback_generalizations"}

def _git(repo, *args):
    result = subprocess.run(
        ("git", *args),
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout

def commits(repo, path=FILE):
    log = _git(
        repo, "log", "--first-parent", "--format=%H %ct",
        REF, "--", path,
    )

    rows = []
    for line in reversed(log.strip().split("\n")):
        if not line:
            continue
        sha, seconds = line.split(" ")
        when = datetime.fromtimestamp(int(seconds), tz=timezone.utc)
        rows.append((sha, when))
    return rows

def snapshot(repo, sha, path=FILE):
    raw = _git(repo, "show", f"{sha}:{path}")
    duplicates = []
    def keep_last(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                duplicates.append(key)
            seen.add(key)
        return dict(pairs)
    parsed = json.loads(raw, object_pairs_hook=keep_last)
    models = {
        key: value
        for key, value in parsed.items()
        if key not in RESERVED
    }
    return models, duplicates

def prefetch(repo, path=FILE):
    promisor = subprocess.run(
        ("git", "config", "--get", "remote.origin.promisor"),
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if promisor.stdout.strip() != "true":
        return 0
    names = [f"{sha}:{path}" for sha, _ in commits(repo, path)]
    blobs = sorted(set(_git(repo, "rev-parse", *names).split()))
    subprocess.run(
        ("git", "-c", "fetch.negotiationAlgorithm=noop", "fetch", "origin",
         "--no-tags", "--no-write-fetch-head", "--recurse-submodules=no",
         "--filter=blob:none", "--stdin"),
        cwd=repo,
        input="\n".join(blobs) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    return len(blobs)