"""The plug-in's answers, as plain functions of the day's data (standard library only).

The plug-in (server.py) offers them as MCP tools; the Agent Skill (skills/llmledger) runs them from a
small command line script, with a copy of this file. Same data, same answers.
"""
import re
from datetime import datetime, timezone

from llmledger_mcp import logic, speed

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
COMMIT = "https://github.com/BerriAI/litellm/commit/"
# A listing's token prices by their names in the answers and in LiteLLM's price file
PRICE_FIELDS = {"input": "input_cost_per_token", "output": "output_cost_per_token",
                "cache_read": "cache_read_input_token_cost", "cache_write": "cache_creation_input_token_cost"}
OFFLINE = ("could not refresh", "bundled")
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
    as_of = (d.get("built") or "")[:10] or None
    out = {"data": {"built": d.get("built"), "prices_as_of": as_of,
                    "litellm_changed": (d.get("litellm") or {}).get("changed"),
                    "ratings_published": s.rating_date, "copy": s.where},
           "credits": d.get("credits")}
    if any(word in (s.where or "") for word in OFFLINE):
        out["data"]["offline"] = f"Today's data could not be downloaded: answering from {s.where}, prices as of {as_of}."
    days = age_days(d.get("built"))
    if days is not None and days >= STALE_DAYS:
        out["data"]["warning"] = (f"This data is {days} days old: the daily rebuild has not run since, so prices, "
                                  "ratings and changes may be out of date.")
    return out


def source(s, event):
    """The LiteLLM commit that made a change, as a link, when the data carries it."""
    commits = s.data.get("sources") or []
    if len(event) > 6 and isinstance(event[6], int) and 0 <= event[6] < len(commits):
        return COMMIT + commits[event[6]]
    return None


def price_on(s, m, day):
    """A listing's prices per 1M tokens at the end of a day, and the change that set each one: today's prices
    rolled back through every later change, as the catalogue had them that day (corrections included)."""
    added = m.get("added") or ""
    if added and day < added:
        return {"day": day, "listed": False, "note": f"Not listed yet: added {added}."}
    now = {name: m.get(name) for name in PRICE_FIELDS}
    set_by = {}
    events = s.data["events"].get(m["key"], [])
    for event in reversed(events):
        when, kind, field = event[0], event[1], event[2]
        name = next((n for n, f in PRICE_FIELDS.items() if f == field), None)
        if kind != "price" or name is None:
            continue
        if when > day:
            old = event[3]
            now[name] = money(old * 1e6) if isinstance(old, (int, float)) and not isinstance(old, bool) else None
        elif name not in set_by:
            set_by[name] = {"day": when, "flag": event[5] or None, "source": source(s, event)}
    first = next((e for e in events if e[1] in ("added", "start")), None)
    for name in PRICE_FIELDS:
        if name not in set_by and now[name] is not None and first:
            set_by[name] = {"day": first[0] if first[1] == "added" else "before Sept 2023", "flag": None,
                            "source": source(s, first)}
    return {"day": day, "listed": True, "price_per_1m": {**now, "unit": "dollars per 1M tokens"}, "set_by": set_by}


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
    return {"input": m["input"], "output": m["output"], "cache_read": m.get("cache_read"),
            "cache_write": m.get("cache_write"), "unit": "dollars per 1M tokens"}


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


def estimate_cost(s, models, input_tokens, output_tokens, cached_tokens=0, calls_per_day=1, cache_write_tokens=0):
    """What a workload costs on each model at its cheapest listing: per call, per day and per 30 days. With
    cached or cache write tokens, also the cost without the cache and the saving."""
    if not 1 <= len(models) <= 10:
        raise NotFound("Give 1 to 10 models to price.")
    cache = cached_tokens > 0 or cache_write_tokens > 0
    rows = []
    for group in resolve_all(s, models):
        hit = listing(s, group, input_tokens=input_tokens, output_tokens=output_tokens)
        if not hit:
            rows.append({"model": group, "note": "no text price listed"})
            continue
        m = hit[0]
        call = logic.cost_of(m, input_tokens, output_tokens, cached_tokens, cache_write_tokens)
        row = {"model": group, "listing": m["key"], "host": m["host"], "price_per_1m": prices(m),
               "per_call": money(call), "per_day": money(call * calls_per_day),
               "per_30_days": money(call * calls_per_day * 30),
               "cache_priced": cached_tokens > 0 and m.get("cache_read") is not None}
        if cache:
            plain = logic.cost_of(m, input_tokens, output_tokens)
            row["without_cache"] = {"per_call": money(plain), "per_30_days": money(plain * calls_per_day * 30)}
            row["saving_per_30_days"] = money((plain - call) * calls_per_day * 30)
            missing = [n for n, used in (("cache read", cached_tokens), ("cache write", cache_write_tokens))
                       if used and m.get(n.replace(" ", "_")) is None]
            if missing:
                row["note"] = "No " + " or ".join(missing) + " price listed: those tokens are counted at the input price."
        rows.append(row)
    rows.sort(key=lambda r: r.get("per_call") if r.get("per_call") is not None else float("inf"))
    return {"models": rows, **footer(s)}


def _value(field, v):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and ("per_token" in field or "token_cost" in field):
        return money(v * 1e6)
    return v


def price_history(s, model, date=None):
    """Every change to a model's listings since 2023 (prices, retirement dates) with the LiteLLM change behind
    each, and for listings that have not changed yet, the chance of a price change, a retirement date or removal
    in the next 90 days and year. With a date (YYYY-MM-DD), each listing's prices that day and what set them."""
    if date is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)):
        raise NotFound(f"Give the date as YYYY-MM-DD, not {date!r}.")
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
                   "after": _value(e[2], e[4]), "flag": e[5] or None, "source": source(s, e)}
                  for e in s.data["events"].get(key, [])]
        item = {"listing": key, "host": m["host"], "added": m.get("added") or "before Sept 2023",
                "retirement_date": m.get("retire") or None, "price_per_1m": prices(m),
                "price_changes": m.get("price_changes"), "changes": events, "outlook": m.get("outlook")}
        if date is not None:
            item["on_date"] = price_on(s, m, date)
        out.append(item)
    used = sorted({e["flag"] for x in out for e in x["changes"] if e["flag"]})
    meaning = {**FLAGS, **((s.data.get("units") or {}).get("flags") or {})}
    notes = ["Prices per 1M tokens. price_changes counts changes from one price to another, without the flagged ones. "
             "source links the LiteLLM change behind each change.",
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


def not_yet_priced(s, maker=None):
    """Models Arena rated recently that LiteLLM's catalogue does not price yet (with names it may be priced
    under), and how soon the catalogue usually prices a model after Arena first shows it, by maker."""
    u = s.data.get("unpriced")
    if not u:
        raise NotFound("This data has no list of models not yet priced (Arena could not be read when it was built).")
    want = (maker or "").strip().lower()
    rows = [{"model": r[0], "maker": r[1] or None, "first_on_arena": r[2], "days_since": r[3], "votes": r[4],
             "rating": r[5], "maybe_listed_as": r[6] or None}
            for r in u["models"] if not want or (r[1] or "").lower() == want]
    makers = [{"maker": r[0], "models": r[1], "priced_before_arena": r[2], "median_wait_days_when_later": r[3],
               "not_priced_yet": r[4]} for r in u["by_maker"] if not want or r[0].lower() == want]
    timing = u["timing"]
    return {"leaderboard": u["date"], "recent_days": u["recent_days"], "models": rows,
            "priced_within": {d: {"share": v[0], "low": v[1], "high": v[2]} for d, v in timing["within"].items()},
            "timed_models": timing["models"], "by_maker": makers,
            "notes": ["Days run from the first Arena leaderboard that lists a model (Arena's history starts "
                      f"{u['history_from']}) to the first catalogue version with a price for it; not the time "
                      "from release. Kaplan-Meier with 95% bootstrap ranges; a model not priced yet counts until "
                      "today. maybe_listed_as names a catalogue model the naming rules could not confirm."],
            **footer(s)}


def _resolver(s):
    if s is None:
        return None
    return lambda text: s.resolve(text)[0]


def estimate_time(s, model, input_tokens, output_tokens, calls=1, way="api", thinking=False, concurrency=1):
    """How long one call and the whole job take, as a usual time and a slow day, learned from the user's own runs
    of that model called that way (see log_run). s may be None when the day's data cannot be loaded."""
    try:
        return speed.estimate_time(model, input_tokens, output_tokens, calls, way, thinking, concurrency,
                                   resolve=_resolver(s))
    except speed.SpeedError as error:
        raise NotFound(str(error)) from None


def log_run(s, model=None, input_tokens=None, output_tokens=None, seconds=None, way="api", thinking=False, task=None,
            promptfoo_results=None):
    """Keep one timed run (or every result of a promptfoo results file) in a file on this computer, so time
    estimates learn from it. Nothing is sent anywhere."""
    try:
        if promptfoo_results:
            added, skipped = speed.from_promptfoo(promptfoo_results, way, thinking, resolve=_resolver(s))
            models = sorted({r["model"] for r in added})
            return {"logged": len(added), "models": models, "skipped": skipped, "file": str(speed.runs_file())}
        if model is None or input_tokens is None or output_tokens is None or seconds is None:
            raise NotFound("Give model, input_tokens, output_tokens and seconds, or a promptfoo results file.")
        run = speed.log(model, input_tokens, output_tokens, seconds, way, thinking, task, resolve=_resolver(s))
        return {"logged": 1, "run": run, "file": str(speed.runs_file())}
    except speed.SpeedError as error:
        raise NotFound(str(error)) from None

