"""The five answers, as plain functions of the day's data (standard library only).

The plug-in (server.py) offers them as MCP tools; the Agent Skill (skills/llmledger) runs them from a
small command line script, with a copy of this file. Same data, same answers.
"""
from datetime import datetime, timezone

from llmledger_mcp import logic

PLANS = {"claude": ("anthropic", "anthropic", "Claude"), "chatgpt": ("openai", "openai", "ChatGPT")}
PAYS = ("api", "claude", "chatgpt")
NEEDS = ("vision", "pdf", "audio", "video", "tools", "reasoning", "web", "schema", "cache", "computer")
PLAN_NOTE = ("Plan use is an estimate: plans do not publish per-model limits, so it assumes a plan runs down "
             "in step with each model's API price on the maker's own host.")
STALE_DAYS = 3
# What each tag on a change means, when the data is older than the one that explains them (data.json units.flags)
FLAGS = {
    "bulk": "bulk clean up: one of 50 or more models removed on the same day",
    "unit": "unit fix: a price made 100 times larger or smaller",
    "reverted": "a price change undone within 30 days, or the change that undid it",
    "likely": ("likely correction: a price change in the model's first 7 days, from 0, or of 10 times or more "
               "either way; 9 in 10 such first price changes were corrections in a labelled sample"),
}
EFFORT_NOTE = ("The effort level is a rule of thumb from the task and the prompt. Higher effort writes more hidden "
               "answer tokens, and no open source measures how many yet.")


class NotFound(ValueError):
    """A name or a request the data cannot answer; the message says what to try."""


def age_days(built, now=None):
    """How many whole days old the data is, or None when its build time is unknown."""
    try:
        return int(((now or datetime.now(timezone.utc)) - datetime.fromisoformat(built)).total_seconds() // 86400)
    except (TypeError, ValueError):                      # missing, not a date, or without a time zone
        return None


def footer(s):
    d = s.data
    out = {"data": {"built": d.get("built"), "litellm_changed": (d.get("litellm") or {}).get("changed"),
                    "ratings_published": s.rating_date, "copy": s.where},
           "credits": d.get("credits")}
    days = age_days(d.get("built"))
    if days is not None and days >= STALE_DAYS:
        out["data"]["warning"] = (f"This data is {days} days old: the daily rebuild has not run since, so prices, "
                                  "ratings and changes may be out of date.")
    return out


def correction_note(s):
    """How many first price changes were corrections, from the labelled sample the data carries."""
    c = s.data.get("corrections") or {}
    if not (c.get("first_week") and c.get("later")):
        return None
    return (f"A price change counts corrections too: in a labelled sample, {round(100 * c['first_week']['share'])}% "
            f"of first price changes in a model's first week and {round(100 * c['later']['share'])}% of later ones "
            "fixed a wrong catalogue entry rather than changed the price, so a real price change is less likely "
            "than the outlook says. Changes flagged likely are probably such corrections.")


def listing(s, group, plan=None, input_tokens=0, output_tokens=0, needs=(), min_context=None):
    """The listing a grouped model is priced at: its cheapest priced text listing for these tokens, or on a plan
    the plan's own host. When the tokens do not decide (none given, or a tie), the lower list price wins, then
    the maker's own host, then the name, so the answer never depends on the order of the listings."""
    best = None
    for m in s.groups.get(group, []):
        if not logic.is_text_model(m) or (plan and m["host"] != PLANS[plan][1]):
            continue
        if any(n not in (m.get("skills") or []) for n in needs):
            continue
        if min_context and not (m.get("context") or 0) >= min_context:
            continue
        # a free listing (both token prices 0) is left out, as on the page: it is usually a trial tier, not a price
        if not ((m.get("input") or 0) > 0 or (m.get("output") or 0) > 0):
            continue
        cost = logic.cost_of(m, input_tokens, output_tokens)
        if cost is None:
            continue
        rank = (cost, (m.get("input") or 0) + (m.get("output") or 0), m["host"] != m.get("maker"), m["key"])
        if best is None or rank < best[2]:
            best = (m, cost, rank)
    return best[:2] if best else None


def prices(m):
    return {"input": m["input"], "output": m["output"], "cache_read": m.get("cache_read"), "unit": "dollars per 1M tokens"}


def money(x):
    return None if x is None else float(f"{x:.6g}")


def resolve_all(s, names):
    groups, missing = [], []
    for name in names:
        group, close = s.resolve(name)
        if group is None:
            missing.append(f"{name!r}" + (" (did you mean " + ", ".join(close[:5]) + "?)" if close else ""))
        elif group not in groups:
            groups.append(group)
    if missing:
        raise NotFound("Not found: " + "; ".join(missing) + ". Use find_models (find in the skill's script) "
                       "to see the names.")
    return groups


def task_label(task):
    return logic.LABELS.get(task, task)


def _check(task=None, pay=None, needs=()):
    if task is not None and task not in logic.TASKS:
        raise NotFound(f"Unknown task {task!r}; use one of: " + ", ".join(logic.TASKS))
    if pay is not None and pay not in PAYS:
        raise NotFound(f"Unknown pay {pay!r}; use one of: " + ", ".join(PAYS))
    wrong = [n for n in needs if n not in NEEDS]
    if wrong:
        raise NotFound("Unknown needs " + ", ".join(map(repr, wrong)) + "; use any of: " + ", ".join(NEEDS))


def find_models(s, task="overall", max_output_price=None, min_context=None, needs=(), maker=None, limit=5):
    """The highest rated models for a kind of work that meet the limits, each at its cheapest listing,
    with prices per 1M tokens, Arena rating and prompt size. Unrated models follow, cheapest first."""
    _check(task=task, needs=needs)
    found = {}
    for group in s.groups:
        if maker and not group.lower().startswith(maker.lower().strip() + " / "):
            continue
        hit = listing(s, group, needs=needs, min_context=min_context)
        if hit and (max_output_price is None or hit[0]["output"] <= max_output_price):
            found[group] = hit[0]
    rated = [r for r in s.ratings.get(task, []) if r[0] in found]
    rows = [{"model": r[0], "listing": found[r[0]]["key"], "host": found[r[0]]["host"],
             "rating": {"score": r[2], "low": r[3], "high": r[4], "rank": i + 1, "of": len(rated)},
             "price_per_1m": prices(found[r[0]]), "prompt_size": found[r[0]].get("context"),
             "effort_levels": found[r[0]].get("effort")} for i, r in enumerate(rated[:limit])]
    if len(rows) < limit:
        rest = sorted((g for g in found if g not in {r[0] for r in rated}), key=lambda g: found[g]["output"])
        rows += [{"model": g, "listing": found[g]["key"], "host": found[g]["host"], "rating": None,
                  "price_per_1m": prices(found[g]), "prompt_size": found[g].get("context"),
                  "effort_levels": found[g].get("effort")} for g in rest[:limit - len(rows)]]
    return {"task": task_label(task), "matching_models": len(found), "rated_for_task": len(rated), "models": rows,
            **footer(s)}


def compare_models(s, models, task="overall", input_tokens=1000, output_tokens=800, answer_tokens=None, pay="api"):
    """Two to six models side by side for a kind of work: rating, prices, cost per task (or plan use), and
    which to pick, with the break-even share of answer tokens for each against the pick."""
    _check(task=task, pay=pay)
    if not 2 <= len(models) <= 6:
        raise NotFound("Give 2 to 6 models to compare.")
    groups = resolve_all(s, models)
    own = {}
    for name, n in (answer_tokens or {}).items():
        group, _ = s.resolve(name)
        if group:
            own[group] = n
    plan = pay if pay in PLANS else None
    rows = []
    for group in groups:
        out = own.get(group, output_tokens)
        hit = listing(s, group, plan, input_tokens, out)
        m = hit[0] if hit else None
        cost = logic.cost_of(m, input_tokens, out) if m else None
        r = s.rating_of(task, group)
        rows.append({"name": group.split(" / ", 1)[1], "model": group, "listing": m["key"] if m else None,
                     "host": m["host"] if m else None, "rating": r[2] if r else None, "low": r[3] if r else None,
                     "high": r[4] if r else None, "cost": cost, "out": m["output"] if m else None,
                     "answer_tokens": out, "m": m})
    pick = logic.best_pick(rows)
    use = logic.plan_multiples([r["cost"] for r in rows])
    table = []
    for r, u in zip(rows, use):
        m = r["m"]
        row = {"model": r["model"], "listing": r["listing"], "host": r["host"],
               "rating": None if r["rating"] is None else {"score": r["rating"], "low": r["low"], "high": r["high"]},
               "price_per_1m": prices(m) if m else None, "answer_tokens": r["answer_tokens"],
               "cost_per_task": money(r["cost"]), "effort_levels": m.get("effort") if m else None,
               "versus_pick": logic.versus(r, pick, bool(plan)) or None}
        if plan:
            row["plan_use"] = None if u is None else round(u, 2)
            if not m:
                row["note"] = "Not listed on " + PLANS[plan][1]
        table.append(row)
    return {"task": task_label(task), "pick": pick["model"] if pick else None,
            "headline": logic.headline(rows, bool(plan)), "models": table,
            "notes": [PLAN_NOTE] if plan else [], **footer(s)}


def estimate_cost(s, models, input_tokens, output_tokens, cached_tokens=0, calls_per_day=1):
    """What a workload costs on each model at its cheapest listing: per call, per day and per 30 days."""
    if not 1 <= len(models) <= 10:
        raise NotFound("Give 1 to 10 models to price.")
    rows = []
    for group in resolve_all(s, models):
        hit = listing(s, group, input_tokens=input_tokens, output_tokens=output_tokens)
        if not hit:
            rows.append({"model": group, "note": "no text price listed"})
            continue
        m = hit[0]
        call = logic.cost_of(m, input_tokens, output_tokens, cached_tokens)
        rows.append({"model": group, "listing": m["key"], "host": m["host"], "price_per_1m": prices(m),
                     "per_call": money(call), "per_day": money(call * calls_per_day),
                     "per_30_days": money(call * calls_per_day * 30),
                     "cache_priced": cached_tokens > 0 and m.get("cache_read") is not None})
    rows.sort(key=lambda r: r.get("per_call") if r.get("per_call") is not None else float("inf"))
    return {"models": rows, **footer(s)}


def _value(field, v):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and ("per_token" in field or "token_cost" in field):
        return money(v * 1e6)
    return v


def price_history(s, model):
    """Every change to a model's listings since 2023 (prices, retirement dates), and for listings that have not
    changed yet, the chance of a price change, a retirement date or removal in the next 90 days and year."""
    if model in s.by_key:
        keys = [model]
        group = s.by_key[model]["maker"] + " / " + s.by_key[model]["name"]
    else:
        group = resolve_all(s, [model])[0]
        keys = [m["key"] for m in sorted(s.groups[group], key=lambda m: m.get("last_change") or "", reverse=True)][:10]
    out = []
    for key in keys:
        m = s.by_key[key]
        events = [{"day": e[0], "change": e[1], "field": e[2] or None, "before": _value(e[2], e[3]),
                   "after": _value(e[2], e[4]), "flag": e[5] or None} for e in s.data["events"].get(key, [])]
        out.append({"listing": key, "host": m["host"], "added": m.get("added") or "before Sept 2023",
                    "retirement_date": m.get("retire") or None, "price_per_1m": prices(m),
                    "price_changes": m.get("price_changes"), "changes": events, "outlook": m.get("outlook")})
    used = sorted({e["flag"] for x in out for e in x["changes"] if e["flag"]})
    meaning = {**FLAGS, **((s.data.get("units") or {}).get("flags") or {})}
    notes = ["Prices per 1M tokens. price_changes counts changes from one price to another, without the flagged ones.",
             "The outlook covers listings that have not changed since they were added: Aalen-Johansen estimates "
             "with 95% intervals, among listings of the same age. What usually happens in the catalogue, not a "
             "forecast for one model."]
    if correction_note(s):
        notes.append(correction_note(s))
    return {"model": group, "listings": out, "listings_in_total": len(s.groups[group]),
            "flags": {f: meaning.get(f, f) for f in used}, "notes": notes, **footer(s)}


def suggest_for_project(s, prompt, pay="api", answer="medium"):
    """Reads a prompt, guesses its kind of work, and suggests a model and effort level: the best value (the
    cheapest whose rating the votes cannot tell apart from the top), the top rated and the cheapest rated."""
    _check(pay=pay)
    if answer not in logic.ANSWERS:
        raise NotFound(f"Unknown answer length {answer!r}; use one of: " + ", ".join(logic.ANSWERS))
    guess = logic.guess_task(prompt)
    task = guess["task"] if s.ratings.get(guess["task"]) else "overall"
    plan = pay if pay in PLANS else None
    tokens_in, tokens_out = logic.estimate_tokens(prompt), logic.ANSWERS[answer]
    rows = []
    for r in s.ratings.get(task, []):
        if plan and not r[0].startswith(PLANS[plan][0] + " / "):
            continue
        hit = listing(s, r[0], plan, tokens_in, tokens_out)
        if hit:
            rows.append({"name": r[0].split(" / ", 1)[1], "model": r[0], "m": hit[0], "cost": hit[1],
                         "rating": r[2], "low": r[3], "high": r[4], "out": hit[0]["output"]})
    if not rows:
        raise NotFound("No rated model matches; try pay='api'.")
    best = logic.best_pick(rows)
    top = max(rows, key=lambda r: r["rating"])
    low = min(rows, key=lambda r: r["cost"])
    picks = [("best value", best), ("top rated", top), ("cheapest rated", low)]
    shown, seen = [], set()
    use = logic.plan_multiples([r["cost"] for _, r in picks])
    for (role, r), u in zip(picks, use):
        if r["model"] in seen:
            continue
        seen.add(r["model"])
        m = r["m"]
        effort = logic.suggest_effort(prompt, task, m.get("effort"), tokens_in, m.get("effort_default") or "")
        item = {"role": role, "model": r["model"], "listing": m["key"], "host": m["host"],
                "rating": {"score": r["rating"], "low": r["low"], "high": r["high"],
                           "rank": rows.index(r) + 1, "of": len(rows)},
                "cost_per_task": money(r["cost"]), "price_per_1m": prices(m),
                "effort": effort["level"], "effort_why": effort["why"] or None,
                "versus_pick": logic.versus(r, best, bool(plan)) or None}
        if plan:
            item["plan_use"] = None if u is None else round(u, 2)
        shown.append(item)
    notes = [EFFORT_NOTE] + ([PLAN_NOTE] if plan else [])
    return {"task": task_label(task), "why": guess["why"], "prompt_tokens": tokens_in, "answer_tokens": tokens_out,
            "headline": logic.headline([r for _, r in picks], bool(plan)),
            "picks": shown, "rated_models_considered": len(rows), "notes": notes, **footer(s)}


def snapshot(s):
    """What the data holds today: dates, how many models and rated tasks, and the sources."""
    return {"models_listed": len(s.models), "grouped_models": len(s.groups),
            "rated_tasks": {k: len(v) for k, v in s.ratings.items()}, "tasks": logic.LABELS, **footer(s)}
