"""Your usage on other models: read a coding agent's token export and price the same work elsewhere (REQ-S55).

Readers for the exports that keep token counts on the user's computer:
  ccusage daily --json       {"daily": [{period (or date), modelBreakdowns: [{modelName, inputTokens, outputTokens,
                              cacheCreationTokens, cacheReadTokens}]}]}   (one unit per day and model)
  ccusage session --json     {"session" (20.x) or "sessions": [{period or sessionId, metadata.lastActivity or
                              lastActivity, modelBreakdowns: [...]}]}
  (ccusage 20.0.37 writes `period` and `session`; its guide still shows `date`, `sessions` and `sessionId`, so
  both spellings are read)
  codeburn export -f json    {"schema": "codeburn.export.v2", "records": [{sessionId, timestamp, category, model,
                              inputTokens, outputTokens, cacheWriteTokens, cacheReadTokens}], "periods": [{label,
                              models: [{Model, "Edit Turns", "One-shot Rate (%)"}]}]}
  a plain mix                [{model, date, input, output, cache_read, cache_write}] handed over by the assistant
Only numbers, names and dates are read. Prompts, file names and project paths in the files are never kept.

The statistics are the ones the rest of the plug-in uses: a bootstrap over sessions for a mean cost per session
(the sessions are the units; nothing is assumed about their shape), and Wilson ranges for one-shot rates. Two ranges
that do not overlap, or a difference whose range leaves out zero, is "a real difference"; anything else is "not
enough data to tell apart". Comparing two models the user actually used compares different sessions, so the answer
says that too.
"""
import json
import random
import re
from pathlib import Path

from llmledger_mcp import forecast

MIN_SESSIONS = 5           # sessions a model needs before its cost per session gets a range
RESAMPLES = 1000
SEED = 20261020
# codeburn's task categories, read as the Arena task whose votes say most about that work
CATEGORY_TASK = {"coding": "coding", "debugging": "coding", "feature": "coding", "refactoring": "coding",
                 "testing": "coding", "git": "coding", "build/deploy": "coding", "delegation": "coding",
                 "exploration": "overall", "planning": "overall", "conversation": "overall",
                 "brainstorming": "overall", "general": "overall"}
SYNTHETIC = re.compile(r"^<.*>$")


class BadExport(ValueError):
    """The file is not one of the exports we read; the message says which ones are."""


def _int(x):
    try:
        return max(0, int(x or 0))
    except (TypeError, ValueError):
        return 0


def _unit(day, session, model, tokens, task=None):
    return {"day": str(day)[:10], "session": str(session), "model": str(model),
            "input": _int(tokens.get("input")), "output": _int(tokens.get("output")),
            "cache_read": _int(tokens.get("cache_read")), "cache_write": _int(tokens.get("cache_write")),
            "task": task}


DATE = re.compile(r"\d{4}[-/]\d{2}[-/]\d{2}")


def _day_of(row, by_session):
    """The row's day: ccusage writes `date` (older) or `period` (20.x) for a day, and for a session its last
    activity (at the top or under metadata) or a date inside the session's name."""
    if not by_session:
        return (row.get("date") or row.get("period") or "")[:10]
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    when = row.get("lastActivity") or meta.get("lastActivity") or row.get("firstActivity") or ""
    if when:
        return str(when)[:10]
    hit = DATE.search(str(row.get("period") or row.get("sessionId") or ""))
    return hit.group(0).replace("/", "-") if hit else ""


def _ccusage_rows(rows, by_session):
    out = []
    for row in rows:
        day = _day_of(row, by_session)
        session = (row.get("sessionId") or row.get("period") or day) if by_session else day
        parts = row.get("modelBreakdowns") or []
        if not parts and len(row.get("modelsUsed") or row.get("models") or []) == 1:
            parts = [{"modelName": (row.get("modelsUsed") or row.get("models"))[0], **row}]
        for part in parts:
            name = part.get("modelName") or part.get("model") or ""
            if not name or SYNTHETIC.match(name):
                continue
            out.append(_unit(day, session, name, {
                "input": part.get("inputTokens"), "output": part.get("outputTokens"),
                "cache_read": part.get("cacheReadTokens"), "cache_write": part.get("cacheCreationTokens")}))
    return out


def _codeburn(data):
    units = {}
    for rec in data.get("records") or []:
        name = rec.get("model") or ""
        if not name or SYNTHETIC.match(name) or rec.get("supplementary"):
            continue
        day = str(rec.get("timestamp") or "")[:10]
        key = (rec.get("sessionId") or day, name, day)
        u = units.setdefault(key, _unit(day, key[0], name, {}, CATEGORY_TASK.get(rec.get("category") or "", None)))
        u["input"] += _int(rec.get("inputTokens"))
        u["output"] += _int(rec.get("outputTokens")) + _int(rec.get("reasoningTokens"))
        u["cache_read"] += _int(rec.get("cacheReadTokens"))
        u["cache_write"] += _int(rec.get("cacheWriteTokens"))
    efficiency = {}
    periods = {p.get("label"): p for p in data.get("periods") or []}
    period = periods.get("30 Days") or (list(periods.values())[-1] if periods else {})
    for row in period.get("models") or []:
        name, edits, rate = row.get("Model"), _int(row.get("Edit Turns")), row.get("One-shot Rate (%)")
        if name and edits and isinstance(rate, (int, float)):
            efficiency[name] = {"edit_turns": edits, "one_shot": round(edits * rate / 100)}
    return list(units.values()), efficiency


def _mix(rows):
    out = []
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not row.get("model"):
            raise BadExport(f"Mix item {i} needs at least a model and a date.")
        out.append(_unit(row.get("date") or row.get("day") or "", row.get("session") or f"item {i}", row["model"], {
            "input": row.get("input", row.get("input_tokens")), "output": row.get("output", row.get("output_tokens")),
            "cache_read": row.get("cache_read", row.get("cached_tokens")),
            "cache_write": row.get("cache_write", row.get("cache_write_tokens"))}, row.get("task")))
    return out


def read(source):
    """{source, units, efficiency, notes} from a path, a parsed export, or a plain mix list."""
    if isinstance(source, (str, Path)):
        path = Path(source).expanduser()
        if not path.exists():
            raise BadExport(f"No file at {path}.")
        text = path.read_text(encoding="utf-8")
        # `npx ccusage ... > file` can put npx's own install prompt before the JSON: start at the JSON
        starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
        try:
            data = json.loads(text[min(starts):] if starts else text)
        except ValueError as error:
            raise BadExport(f"{path.name} is not JSON: {error}") from None
    else:
        data = source
    if isinstance(data, list):
        return {"source": "a token mix", "units": _mix(data), "efficiency": {}, "notes": []}
    if not isinstance(data, dict):
        raise BadExport("Expected a ccusage or codeburn export, or a list of token mixes.")
    if str(data.get("schema", "")).startswith("codeburn.export"):
        units, efficiency = _codeburn(data)
        notes = [] if data.get("records") else ["This codeburn export has no records; nothing to price."]
        return {"source": f"codeburn ({data['schema']})", "units": units, "efficiency": efficiency, "notes": notes}
    sessions = data.get("sessions") if isinstance(data.get("sessions"), list) else data.get("session")
    if isinstance(sessions, list):
        return {"source": "ccusage session", "units": _ccusage_rows(sessions, True), "efficiency": {}, "notes": []}
    rows = data.get("daily") if isinstance(data.get("daily"), list) else data.get("data")
    if isinstance(rows, list) and (data.get("type") in (None, "daily") or data.get("daily")):
        return {"source": "ccusage daily", "units": _ccusage_rows(rows, False), "efficiency": {}, "notes": []}
    raise BadExport("Not an export we read. Use `ccusage daily --json`, `ccusage session --json`, "
                    "`codeburn export -f json`, or pass a list of {model, date, input, output, cache_read, cache_write}.")


# ---------- statistics ----------
def bootstrap_mean(values, resamples=RESAMPLES, seed=SEED):
    """(mean, low, high): the mean and its 95% bootstrap range over the values, or None under MIN_SESSIONS."""
    if len(values) < MIN_SESSIONS:
        return None
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(resamples))
    return sum(values) / n, means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1]


def bootstrap_difference(a, b, resamples=RESAMPLES, seed=SEED):
    """(difference of means a - b, low, high) over independent resamples of each, or None when either is short."""
    if len(a) < MIN_SESSIONS or len(b) < MIN_SESSIONS:
        return None
    rng = random.Random(seed)
    diffs = sorted(sum(rng.choice(a) for _ in range(len(a))) / len(a) - sum(rng.choice(b) for _ in range(len(b))) / len(b)
                   for _ in range(resamples))
    return sum(a) / len(a) - sum(b) / len(b), diffs[int(0.025 * resamples)], diffs[int(0.975 * resamples) - 1]


def verdict(low, high, what):
    """Plain words for a range: a real difference when zero is outside it."""
    if low > 0 or high < 0:
        return f"a real difference in {what}: the 95% range leaves out zero"
    return f"not enough data to tell the two apart on {what}: the 95% range includes zero"


def one_shot(efficiency, model):
    """{rate, low, high, edit_turns} from codeburn's per-model rows, or None."""
    e = efficiency.get(model)
    if not e or not e["edit_turns"]:
        return None
    rng = forecast.wilson(e["one_shot"], e["edit_turns"])
    return {"rate": round(e["one_shot"] / e["edit_turns"], 4), "low": round(rng[0], 4), "high": round(rng[1], 4),
            "edit_turns": e["edit_turns"], "one_shot_turns": e["one_shot"]}
