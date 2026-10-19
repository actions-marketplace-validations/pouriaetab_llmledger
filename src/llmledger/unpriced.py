"""Seen, not yet priced: models people rate on Arena that LiteLLM's catalogue does not price yet, and how
long the catalogue usually takes to price a model after Arena first shows it.

Sources: Arena's latest leaderboard and its full history (CC BY 4.0, read by arena.py and trends.py), and
the catalogue's own history (MIT). A model's "first seen" is the first overall leaderboard it is on. Arena's
history starts on 28 August 2024, so models already there that day are left out of the timing: their real
first day is unknown. Names are matched by the same rules as the ratings. A name the rules cannot match is
listed with the catalogue's closest names, because it may be priced under another name; such models are
left out of the timing too, since it is not known whether they are priced.
"""
import json
from datetime import date

from llmledger import arena, survival, trends

RECENT = 180            # days: the list shows models Arena first showed within this many days
CLOSE = 3               # closest catalogue names shown for a name the rules cannot match
MIN_CLOSE = 5           # a close name has at least this many characters
DAYS = (0, 7, 30, 90)   # the chance a model is priced within this many days of Arena first showing it
MIN_AT_RISK = 20
MIN_MAKER = 5           # a maker needs this many models for its own line


def _day(text):
    return date.fromisoformat(str(text)[:10])


def first_seen(history):
    """The first overall leaderboard each Arena model is on, by trends.same(name)."""
    seen = {}
    for row in history:
        key = trends.same(row["name"])
        if key not in seen or row["date"] < seen[key]:
            seen[key] = row["date"]
    return seen


def first_priced(records, since):
    """The day each grouped model ("maker / name") was first listed with a price field; listings in the
    catalogue's first version count from its first day."""
    out = {}
    for record in records:
        group = record[1] + " / " + record[2]
        day = record[6] or since
        if group not in out or day < out[group]:
            out[group] = day
    return out


def close_names(name, names):
    """Catalogue names that may be the same model: one starts with a form of the Arena name, or the
    Arena name contains it."""
    forms = [form for form in arena.candidates(name) if len(form) >= MIN_CLOSE]
    found = []
    for form in forms:
        for other in names:
            if other in found or len(other) < MIN_CLOSE:
                continue
            if other.startswith(form + "-") or other.startswith(form + ".") or (other in form and other != form):
                found.append(other)
    return sorted(found, key=lambda n: (-len(n), n))[:CLOSE]


def build(tables, history, records, since, today=None):
    """The page's and data.json's "unpriced" part, or None without Arena's tables and history."""
    if not tables or not history:
        return None
    today = today or date.today()
    latest = [row for row in tables.get(arena.TEXT, []) if row["category"] == "overall"]
    if not latest:
        return None
    start = min(row["date"] for row in history)
    seen = first_seen(history)
    groups = {}
    for record in records:
        groups.setdefault(record[2], set()).add(record[1])
    priced = first_priced(records, since)
    names = sorted(groups)
    models = {}
    for row in latest:
        name = row["model_name"]
        base = arena.candidates(name)[-1]          # one line for a model Arena lists at several effort levels
        group = arena.match(name, row.get("organization", ""), groups)
        first = seen.get(trends.same(name))
        kept = models.get(base)
        if kept is None or (first and (kept["seen"] is None or first < kept["seen"])):
            models[base] = {"name": name, "maker": row.get("organization") or "", "group": group, "seen": first,
                            "votes": int(row["vote_count"]), "rating": round(row["rating"], 1)}
        if kept is not None:
            models[base]["votes"] = max(models[base]["votes"], kept["votes"], int(row["vote_count"]))
            models[base]["group"] = models[base]["group"] or kept["group"] or group
    unpriced, timing = [], []
    for model in models.values():
        close = [] if model["group"] else close_names(model["name"], names)
        if not model["group"]:
            model["close"] = close
            unpriced.append(model)
        if not model["seen"] or model["seen"] <= start:
            continue                                # first day unknown: on Arena before its history starts
        if model["group"]:
            days = max(0, (_day(priced[model["group"]]) - _day(model["seen"])).days)
            timing.append((float(days), "price", model["maker"]))
        elif not close:
            timing.append((float((today - _day(model["seen"])).days), "censored", model["maker"]))
    recent = [m for m in unpriced if m["seen"] and (today - _day(m["seen"])).days <= RECENT]
    recent.sort(key=lambda m: (m["seen"], m["votes"]), reverse=True)
    subjects = [(t, kind) for t, kind, _ in timing]
    report = survival.cumulative_incidence(subjects, DAYS, min_at_risk=MIN_AT_RISK)
    intervals = survival.bootstrap(subjects, DAYS, min_at_risk=MIN_AT_RISK, resamples=1000)
    within = {str(d): [round(row["price"], 3), round(intervals[(d, "price")][0], 3),
                       round(intervals[(d, "price")][1], 3)] for d, (_, row) in report.items()}
    makers = {}
    for t, kind, maker in timing:
        makers.setdefault(maker or "unknown", []).append((t, kind))
    by_maker = []
    for maker, rows in sorted(makers.items()):
        if len(rows) < MIN_MAKER:
            continue
        late = sorted(t for t, kind in rows if kind == "price" and t > 0)
        before = sum(1 for t, kind in rows if kind == "price" and t == 0)
        by_maker.append([maker, len(rows), round(before / len(rows), 3),
                         late[len(late) // 2] if late else None,
                         sum(1 for _, kind in rows if kind == "censored")])
    return {
        "date": max(row["leaderboard_publish_date"] for row in latest),
        "history_from": start,
        "recent_days": RECENT,
        "models": [[m["name"], m["maker"], m["seen"], (today - _day(m["seen"])).days, m["votes"], m["rating"],
                    m["close"]] for m in recent],
        "not_priced": len(unpriced),
        "timing": {"models": len(timing), "priced": sum(1 for _, kind, _ in timing if kind == "price"),
                   "within": within,
                   "left_out_close_names": sum(1 for m in unpriced if m["close"])},
        "by_maker": sorted(by_maker, key=lambda r: -r[1]),
    }


def previous(url):
    """The part on the page that is live now, if Arena cannot be read today."""
    try:
        text = arena._get_text(url)
        return json.loads(text[text.index("{"):text.rstrip().rstrip(";").rindex("}") + 1]).get("unpriced")
    except Exception as error:
        print("No earlier 'not yet priced' list either:", error)
        return None
