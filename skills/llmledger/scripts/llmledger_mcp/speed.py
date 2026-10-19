"""How long a job takes, learned from the user's own runs (standard library only).

Each run (a model, how it was called, its prompt and answer tokens, and the seconds it took) is one line in a
file on the user's computer; nothing is sent anywhere. A run comes from log_run, or from a promptfoo results file
(promptfoo eval -o results.json: each result's latencyMs and tokenUsage). No public speed table is used, so an
estimate starts at the first run.

For one model and one way of calling it, the time of a call is fitted as a fixed start plus a time per answer
token, by the Theil-Sen estimator (the median of the slopes between pairs of runs), which one odd run cannot pull
far. The usual time is the fit times the median ratio of real to fitted time over the runs, and a slow day the
90th percentile of that ratio; with fewer than 5 runs, a slow day is at least twice the usual time.
"""
import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path

WAYS = ("api", "claude-code", "claude-code-session", "ollama", "other")
WAY_TEXT = {"api": "the provider's API", "claude-code": "Claude Code started fresh for each call",
            "claude-code-session": "a Claude Code session kept open", "ollama": "a local model in Ollama",
            "other": "some other way"}
RECENT = 50          # runs used per model and way: the newest ones
FEW = 5              # under this many runs, an estimate is rough


class SpeedError(ValueError):
    """A run or a request that cannot be used; the message says why."""


def runs_file():
    override = os.environ.get("LLMLEDGER_RUNS")
    if override:
        return Path(override)
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "llmledger-mcp" / "runs.jsonl"


def load(path=None):
    path = Path(path or runs_file())
    if not path.exists():
        return []
    runs = []
    for line in path.read_text().splitlines():
        try:
            runs.append(json.loads(line))
        except ValueError:
            continue                                   # a half-written line is skipped, never fatal
    return runs


def _save(new, path=None):
    path = Path(path or runs_file())
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for run in new:
            f.write(json.dumps(run, separators=(",", ":")) + "\n")


def name(model, resolve=None):
    """One name per model: the catalogue's grouped name when it knows the model, otherwise as typed."""
    text = str(model or "").strip()
    if resolve:
        group = resolve(text)
        if group:
            return group
    return text.lower()


def check(way, input_tokens, output_tokens, seconds=None):
    if way not in WAYS:
        raise SpeedError(f"Unknown way {way!r}; use one of: " + ", ".join(WAYS))
    if input_tokens < 0 or output_tokens < 0:
        raise SpeedError("Token counts cannot be negative.")
    if seconds is not None and not seconds > 0:
        raise SpeedError("Seconds must be more than 0.")


def log(model, input_tokens, output_tokens, seconds, way="api", thinking=False, task=None, resolve=None,
        path=None, now=None):
    check(way, input_tokens, output_tokens, seconds)
    run = {"at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"), "model": name(model, resolve),
           "way": way, "thinking": bool(thinking), "task": task or None, "input": int(input_tokens),
           "output": int(output_tokens), "seconds": round(float(seconds), 3), "source": "log_run"}
    _save([run], path)
    return run


def _model_of(result):
    provider = result.get("provider") or {}
    if isinstance(provider, str):
        provider = {"id": provider}
    label = (provider.get("label") or "").strip()
    return label or str(provider.get("id") or "").split(":")[-1]


def from_promptfoo(results_path, way="api", thinking=False, resolve=None, path=None):
    """Every result of a promptfoo results file as a run, once: (runs added, results skipped and why)."""
    check(way, 0, 0)
    try:
        report = json.loads(Path(results_path).read_text())
        results = report["results"]["results"]
        eval_id = report.get("evalId") or Path(results_path).name
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SpeedError(f"Not a promptfoo results file ({error}); write one with promptfoo eval -o results.json.")
    seen = {run.get("source") for run in load(path)}
    added, skipped = [], {"cached": 0, "failed or no time": 0, "no tokens (not a model call)": 0, "already logged": 0}
    for index, result in enumerate(results):
        source = f"promptfoo:{eval_id}:{index}"
        response = result.get("response") or {}
        usage = result.get("tokenUsage") or response.get("tokenUsage") or {}
        if source in seen:
            skipped["already logged"] += 1
        elif response.get("cached"):
            skipped["cached"] += 1
        elif result.get("error") or response.get("error") or not (result.get("latencyMs") or 0) > 0:
            skipped["failed or no time"] += 1
        elif not (usage.get("prompt") or usage.get("completion")):
            skipped["no tokens (not a model call)"] += 1
        else:
            added.append({"at": report["results"].get("timestamp") or datetime.now(timezone.utc).isoformat(),
                          "model": name(_model_of(result), resolve), "way": way, "thinking": bool(thinking),
                          "task": None, "input": int(usage.get("prompt") or 0),
                          "output": int(usage.get("completion") or 0),
                          "seconds": round(result["latencyMs"] / 1000, 3), "source": source})
    _save(added, path)
    return added, {k: v for k, v in skipped.items() if v}


def _quantile(values, q):
    values = sorted(values)
    position = q * (len(values) - 1)
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def fit(runs):
    """(start seconds, seconds per answer token) by Theil-Sen; with one run or one answer length, no start."""
    points = [(r["output"], r["seconds"]) for r in runs]
    slopes = [(y2 - y1) / (x2 - x1) for i, (x1, y1) in enumerate(points) for x2, y2 in points[i + 1:] if x2 != x1]
    if slopes:
        slope = max(0.0, statistics.median(slopes))
        start = max(0.0, statistics.median(y - slope * x for x, y in points))
        if start + slope * statistics.median(x for x, _ in points) > 0:
            return start, slope
    return 0.0, statistics.median(y / max(x, 1) for x, y in points)


def estimate(runs, output_tokens):
    """Seconds for one call: (usual, slow day), from runs of one model and way."""
    start, slope = fit(runs)
    ratios = [r["seconds"] / max(start + slope * r["output"], 1e-9) for r in runs]
    base = start + slope * output_tokens
    usual = base * statistics.median(ratios)
    slow = base * _quantile(ratios, 0.9)
    if len(runs) < FEW:
        slow = max(slow, 2 * usual)
    return usual, slow


def _short(seconds):
    if seconds < 90:
        return f"{seconds:.1f} seconds"
    if seconds < 5400:
        return f"{seconds / 60:.1f} minutes"
    return f"{seconds / 3600:.1f} hours"


def estimate_time(model, input_tokens, output_tokens, calls=1, way="api", thinking=False, concurrency=1,
                  resolve=None, path=None):
    check(way, input_tokens, output_tokens)
    if calls < 1 or concurrency < 1:
        raise SpeedError("calls and concurrency must be 1 or more.")
    key = name(model, resolve)
    mine = [r for r in load(path) if r.get("model") == key]
    runs = [r for r in mine if r.get("way") == way and bool(r.get("thinking")) == bool(thinking)][-RECENT:]
    out = {"model": key, "way": way, "thinking": bool(thinking), "runs_used": len(runs)}
    if not runs:
        others = sorted({(r["way"], bool(r.get("thinking"))) for r in mine})
        out["estimate"] = None
        out["note"] = (f"No runs of {key} called through {WAY_TEXT[way]}" + (" with thinking on" if thinking else "") +
                       " yet. Time one call and give it to log_run (or log a promptfoo results file): estimates come "
                       "from your own runs only.")
        if others:
            out["runs_of_this_model"] = [{"way": w, "thinking": t} for w, t in others]
        return out
    usual, slow = estimate(runs, output_tokens)
    rounds = -(-calls // concurrency)
    out["per_call_seconds"] = {"usual": round(usual, 2), "slow_day": round(slow, 2)}
    out["job"] = {"calls": calls, "at_once": concurrency, "usual": _short(usual * rounds),
                  "slow_day": _short(slow * rounds), "usual_seconds": round(usual * rounds, 1),
                  "slow_day_seconds": round(slow * rounds, 1)}
    start, slope = fit(runs)
    out["based_on"] = (f"Your {len(runs)} run{'s' if len(runs) != 1 else ''} of this model this way: about "
                       f"{start:.2f} s to start and {slope * 1000:.1f} s per 1,000 answer tokens.")
    if len(runs) < FEW:
        out["rough"] = f"Fewer than {FEW} runs: the slow day is set to at least twice the usual time."
    if input_tokens > 4 * max(r["input"] for r in runs):
        out["note"] = "This prompt is much longer than any timed run; reading it may add time the runs do not show."
    return out
