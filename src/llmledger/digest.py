"""This week in LLM prices: a short post written from the data, published as site/digest.md.

Seven days of the catalogue in plain words: how many models arrived, were repriced, got a
retirement date or left; the biggest price cuts and rises (token prices only, corrections
left out); the retirement dates coming soonest; the newest models that already have an Arena
rank; and what top quality costs against a year ago. Written to be pasted as it is.

    PYTHONPATH=src python -m llmledger.digest site/data.json    # prints the post
"""
import json
import sys
from datetime import date, timedelta

DAYS = 7
TOP = 5
PAGE = "https://pouriaetab.github.io/llmledger/"
TOKENS = {"input_cost_per_token": "input", "output_cost_per_token": "output"}


def window(machine, days=DAYS):
    end = date.fromisoformat(machine["built"][:10])
    return (end - timedelta(days=days)).isoformat(), end


def per_million(value):
    v = float(value) * 1e6
    return f"${v:,.2f}" if v >= 0.1 else f"${v:,.4f}"


def moves(machine, since):
    """Token price changes in the window, corrections left out, one row per model:
    [(ratio of the larger move, key, [(field, old, new, ratio), ...])]."""
    per = {}
    for key, events in machine["events"].items():
        for day, kind, field, old, new, flag, _ in events:
            if day < since or kind != "price" or field not in TOKENS or flag or not old or not new:
                continue
            per.setdefault(key, []).append((TOKENS[field], old, new, float(new) / float(old)))
    out = []
    for key, rows in per.items():
        rows.sort()
        far = max(rows, key=lambda r: abs(r[3] - 1))
        out.append((far[3], key, rows))
    return out


def move_line(key, rows, cut):
    bits = ", ".join(f"{field} {per_million(old)} to {per_million(new)}" for field, old, new, _ in rows)
    change = [round(100 * (1 - r)) for *_, r in rows] if cut else [r for *_, r in rows]
    if cut:
        pct = f"{min(change)}% off" if min(change) == max(change) else f"{min(change)} to {max(change)}% off"
    else:
        pct = f"{min(change):.1f}x" if round(min(change), 1) == round(max(change), 1) else f"{min(change):.1f} to {max(change):.1f}x"
    return f"- {key}: {bits} per 1M ({pct})"


def counts(machine, since):
    seen = {}
    for key, events in machine["events"].items():
        for day, kind, *_ in events:
            if day >= since and kind in ("added", "price", "deprecation", "removed"):
                seen.setdefault(kind, set()).add(key)
    return {kind: len(keys) for kind, keys in seen.items()}


def retiring(machine, since):
    rows = []
    for key, events in machine["events"].items():
        for day, kind, field, old, new, *_ in events:
            if day >= since and kind == "deprecation" and new:
                rows.append((str(new), key))
    return sorted(rows)


def arrivals(machine, since):
    """Models added in the window that Arena already ranks, one per grouped name: [(rank, task, group)]."""
    ratings = machine.get("ratings") or {}
    ranked = {}
    for task, rows in (ratings.get("tasks") or {}).items():
        for group, _name, _rating, _low, _high, _votes, rank in rows:
            if task == "overall" or group not in ranked:
                ranked[group] = (rank, task)
    out = {}
    for m in machine["models"]:
        group = m["maker"] + " / " + m["name"]
        if (m.get("added") or "") >= since and group in ranked and group not in out:
            rank, task = ranked[group]
            out[group] = (rank, task, group)
    return sorted(out.values())[:TOP]


def index_line(machine):
    idx = machine.get("index")
    if not idx:
        return ""
    return (f"Top quality costs {idx['times']}x less than a year ago: a model as good as last year's #1 "
            f"({idx['then_model']}, then ${idx['then_price']:,.2f} per 1M tokens) is {idx['now_model']} at "
            f"${idx['now_price']:,.2f}.")


def build(machine):
    since, end = window(machine)
    c = counts(machine, since)
    lines = [f"# This week in LLM prices ({since} to {end.isoformat()})", ""]
    lines.append(f"{c.get('added', 0)} models added, {c.get('price', 0)} repriced, {c.get('deprecation', 0)} got a "
                 f"retirement date, {c.get('removed', 0)} removed, in LiteLLM's catalogue of {len(machine['models']):,} "
                 "listed models.")
    lines.append("")
    m = moves(machine, since)
    cuts = sorted((x for x in m if x[0] < 1), key=lambda x: x[0])[:TOP]
    rises = sorted((x for x in m if x[0] > 1), key=lambda x: -x[0])[:TOP]
    if cuts:
        lines.append("**Biggest price cuts**")
        lines += [move_line(key, rows, True) for _, key, rows in cuts]
        lines.append("")
    if rises:
        lines.append("**Biggest price rises**")
        lines += [move_line(key, rows, False) for _, key, rows in rises]
        lines.append("")
    soon = [r for r in retiring(machine, since) if r[0] >= since][:TOP]
    if soon:
        lines.append("**Retirement dates set this week, soonest first**")
        lines += [f"- {key}: {when}" for when, key in soon]
        lines.append("")
    new = arrivals(machine, since)
    if new:
        lines.append("**New this week, already ranked on Arena**")
        lines += [f"- {key}: #{rank} for {task}" for rank, task, key in new]
        lines.append("")
    idx = index_line(machine)
    if idx:
        lines += [idx, ""]
    lines.append("Price changes that look like corrections of the catalogue (a model's first week, from zero, or "
                 "10x either way) are left out of the cuts and rises. Not financial or procurement advice.")
    lines.append(f"Every model, every change, the method: {PAGE}")
    return "\n".join(lines) + "\n"


def write(path, machine):
    with open(path, "w") as f:
        f.write(build(machine))


if __name__ == "__main__":
    with open(sys.argv[1] if len(sys.argv) > 1 else "site/data.json") as f:
        print(build(json.load(f)), end="")
