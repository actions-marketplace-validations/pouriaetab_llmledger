"""The plug-in's answers, as plain functions of the day's data (standard library only).

The plug-in (server.py) offers them as MCP tools; the Agent Skill (skills/llmledger) runs them from a
small command line script, with a copy of this file. Same data, same answers.
"""
import re
from datetime import datetime, timezone

from llmledger_mcp import forecast, logic, speed, usage

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


def listing(s, group, plan=None, input_tokens=0, output_tokens=0, needs=(), min_context=None, cached_tokens=0,
            written_tokens=0, hosts=None):
    """The listing a grouped model is priced at: its cheapest priced text listing for these tokens (on these
    hosts, when given), or on a plan the plan's own host. When the tokens do not decide (none given, or a tie),
    the lower list price wins, then the maker's own host, then the name, so the answer never depends on the
    order of the listings."""
    best = None
    for m in s.groups.get(group, []):
        if not logic.is_text_model(m) or (plan and m["host"] != PLANS[plan][1]):
            continue
        if hosts and not m["host"].startswith(tuple(hosts)):
            continue
        if any(n not in (m.get("skills") or []) for n in needs):
            continue
        if min_context and not (m.get("context") or 0) >= min_context:
            continue
        # a free listing (both token prices 0) is left out, as on the page: it is usually a trial tier, not a price
        if not ((m.get("input") or 0) > 0 or (m.get("output") or 0) > 0):
            continue
        cost = logic.cost_of(m, input_tokens, output_tokens, cached_tokens, written_tokens)
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


def find_models(s, task="overall", max_output_price=None, min_context=None, needs=(), maker=None, limit=5, name=None):
    """The highest rated models for a kind of work that meet the limits, each at its cheapest listing,
    with prices per 1M tokens, Arena rating and prompt size. Unrated models follow, cheapest first.
    With a name: that one model, and every listing of it (host, mode, prices, prompt size)."""
    _check(task=task, needs=needs)
    if name:
        group = resolve_all(s, [name])[0]
        r = s.rating_of(task, group)
        hit = listing(s, group)
        rows = sorted(s.groups[group], key=lambda m: ((m.get("input") or 0) + (m.get("output") or 0), m["key"]))
        return {"task": task_label(task), "model": group, "cheapest_listing": hit[0]["key"] if hit else None,
                "rating": {"score": r[2], "low": r[3], "high": r[4]} if r else None,
                "listings": [{"listing": m["key"], "host": m["host"], "mode": m.get("mode"), "status": m.get("status"),
                              "price_per_1m": prices(m), "prompt_size": m.get("context"),
                              "effort_levels": m.get("effort")} for m in rows],
                **footer(s)}
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


def log_run(s, model=None, input_tokens=None, output_tokens=None, seconds=None, way=None, thinking=False, task=None,
            promptfoo_results=None):
    """Keep one timed run (or every result of a promptfoo results file) in a file on this computer, so time
    estimates learn from it. Nothing is sent anywhere. For a promptfoo file the way of each run comes from its
    provider unless given; a single run without a way counts as an API call."""
    try:
        if promptfoo_results:
            added, skipped = speed.from_promptfoo(promptfoo_results, way, thinking, resolve=_resolver(s))
            models = sorted({r["model"] for r in added})
            return {"logged": len(added), "models": models, "skipped": skipped, "file": str(speed.runs_file())}
        if model is None or input_tokens is None or output_tokens is None or seconds is None:
            raise NotFound("Give model, input_tokens, output_tokens and seconds, or a promptfoo results file.")
        run = speed.log(model, input_tokens, output_tokens, seconds, way or "api", thinking, task,
                        resolve=_resolver(s))
        return {"logged": 1, "run": run, "file": str(speed.runs_file())}
    except speed.SpeedError as error:
        raise NotFound(str(error)) from None



FORECAST_NOTES = [
    "A sample shows the job only as well as its tests stand for the rest: draw them at random "
    "(promptfoo eval --filter-sample 20 --filter-sample-seed 7 -o sample.json).",
    "Times are a usual time and a slow day, from the sample's own timed calls and your logged runs of the same "
    "model called the same way (estimate_time). Many calls at once can meet rate limits a small sample does not.",
    "Right is the share of checked results that passed, with a Wilson 95% range; calls that failed to run are "
    "counted apart, as errors.",
    "The break-even is what a wrong answer must cost you to catch and fix before the dearer model that is right "
    "more often pays for itself: the cost difference an item over the difference in how often each was right.",
    "The 90-day chance of a price change is for the cheapest listing, among listings of the same age that have not "
    "changed since they were added (price_history). What usually happens in the catalogue, not a forecast for one "
    "model.",
]


def _job_time(row, runs, from_logged, calls, at_once, tok):
    if not runs or tok is None:
        return None, ("No timed calls of this model in the sample (all cached or failed) and no logged runs: run "
                      "the sample again with --no-cache.")
    usual, slow = speed.estimate(runs, tok["output"])
    rounds = -(-calls // at_once)
    sampled = len(runs) - from_logged
    time = {"usual": speed.short(usual * rounds), "slow_day": speed.short(slow * rounds),
            "usual_seconds": round(usual * rounds, 1), "slow_day_seconds": round(slow * rounds, 1),
            "per_call_seconds": {"usual": round(usual, 2), "slow_day": round(slow, 2)},
            "based_on": f"{sampled} timed call{'s' if sampled != 1 else ''} in this sample"
                        + (f" and {from_logged} of your logged runs" if from_logged else "")}
    if len(runs) < speed.FEW:
        time["rough"] = f"Fewer than {speed.FEW} timed calls: the slow day is set to at least twice the usual time."
    if row["way"] == "ollama":
        time["note"] = ("A local model may answer one call at a time, so these times hold for the same number of calls "
                        "at once as the sample ran.")
    return time, None


def _job_cost(s, row, tok, calls, per_test):
    """(cost of the whole job at the cheapest listing and at the sample's host, the cheapest listing, a note)."""
    if s is None:
        return None, None, "Prices could not be loaded (no data yet, and no internet)."
    if row["model"] not in s.groups:
        if row["way"] == "ollama":
            return None, None, "A local model: no token price (it costs your computer's time and power)."
        return None, None, (f"{row['model']!r} is not in the price catalogue: give the provider a label with the "
                            "catalogue's name, for example label: claude-opus-5.5.")
    if tok is None:
        return None, None, "No token counts in the sample (all cached or failed): run it again with --no-cache."
    args = dict(input_tokens=tok["input"], output_tokens=tok["output"], cached_tokens=tok["cache_read"],
                written_tokens=tok["cache_write"])
    hit = listing(s, row["model"], **args)
    if not hit:
        return None, None, "No text price listed for this model."
    m, call = hit
    cost = {"cheapest": {"listing": m["key"], "host": m["host"], "price_per_1m": prices(m),
                         "per_item": money(call * per_test), "whole_job": money(call * calls)}}
    hosts = forecast.hosts_of(row["provider"])
    mine = None
    if hosts:
        there = listing(s, row["model"], hosts=hosts, **args)
        if there:
            mine = sum(logic.cost_of(there[0], c["input"], c["output"], c["cache_read"], c["cache_write"])
                       for c in row["calls"])
            cost["as_sampled"] = {"listing": there[0]["key"], "host": there[0]["host"],
                                  "price_per_1m": prices(there[0]), "per_item": money(there[1] * per_test),
                                  "whole_job": money(there[1] * calls), "sample_cost": money(mine)}
        else:
            cost["as_sampled"] = {"note": "No listing of this model on " + "/".join(hosts) + " in the catalogue."}
    if row["way"] == "claude-code":
        cost.setdefault("as_sampled", {})["note"] = ("Run through Claude Code: on a Claude plan the job uses the plan, "
                                                     "not dollars; these are API prices for the same tokens.")
    said = row["promptfoo_cost"]
    if said is not None and row["costed"]:
        job = said / row["costed"] * calls
        cost["by_promptfoo"] = {"sample": money(said), "whole_job": money(job)}
        if mine and said > 0 and abs(said - mine) > 0.1 * max(said, mine):
            cost["by_promptfoo"]["note"] = (
                f"promptfoo put the sample at {forecast.dollars(said)} and these prices at {forecast.dollars(mine)}: "
                "the provider may bill tokens the results do not list (cache writes, or calls Claude Code makes on "
                "its own), or promptfoo's own price table differs. At promptfoo's rate the job is "
                f"{forecast.dollars(job)}.")
    return cost, m, None


def _outlook(m):
    seen = (m.get("outlook") or {}).get("90")
    if not seen:
        return {"listing": m["key"], "note": "No 90-day outlook for this listing: it has changed since it was added, "
                                             "or too few listings of its age are followed."}
    share, low, high = seen["price"]
    return {"listing": m["key"], "share": share, "low": low, "high": high}


def forecast_job(s, promptfoo_results, items, concurrency=None, way=None, thinking=False, wrong_answer_cost=None):
    """The whole job, quoted from a promptfoo run of a sample of it. For each model in the sample: the time as a
    usual time and a slow day, the cost at its cheapest listing next to the listing the sample used, the chance
    of a price change within 90 days, how often it was right (Wilson 95% range) and the break-even against the
    pick. Reads the file only; nothing is called or sent. s may be None when the day's data cannot be loaded."""
    if not isinstance(items, int) or items < 1:
        raise NotFound("Give items as 1 or more: the number of tests in the whole job.")
    if concurrency is not None and concurrency < 1:
        raise NotFound("concurrency must be 1 or more.")
    if wrong_answer_cost is not None and wrong_answer_cost < 0:
        raise NotFound("wrong_answer_cost cannot be negative.")
    if way is not None and way not in speed.WAYS:
        raise NotFound(f"Unknown way {way!r}; use one of: " + ", ".join(speed.WAYS))
    try:
        sample = forecast.read(promptfoo_results, way, thinking, resolve=_resolver(s))
    except forecast.ForecastError as error:
        raise NotFound(str(error)) from None
    at_once = concurrency or sample["at_once"]
    logged = speed.load()
    rows = []
    for row in sample["rows"]:
        per_test = row["results"] / max(len(row["tests"]), 1)
        calls = max(1, round(items * per_test))
        tok = forecast.tokens(row)
        runs, from_logged = forecast.runs_for(row, logged)
        time, time_note = _job_time(row, runs, from_logged, calls, at_once, tok)
        cost, m, cost_note = _job_cost(s, row, tok, calls, per_test)
        name = row["model"].split(" / ", 1)[-1]
        if row["prompt"] is not None:
            name += f" ({row['prompt'][:40]})"
        out = {"model": row["model"], "provider": row["provider"], "prompt": row["prompt"], "way": row["way"],
               "thinking": row["thinking"], "calls": calls, "right": forecast.right(row),
               "errors": {"failed": row["errors"], "of": row["results"]} if row["errors"] else None,
               "tokens_per_call": tok, "time": time, "cost": cost,
               "price_change_90_days": _outlook(m) if m else None,
               "notes": [n for n in (time_note, cost_note) if n] or None}
        if row["cached"]:
            out["cached_results"] = row["cached"]
        rows.append({**out, "name": name, "per_item": (cost or {}).get("cheapest", {}).get("per_item")})
    pick = forecast.best(rows, wrong_answer_cost)
    for r in rows:
        r["versus_pick"] = forecast.versus(r, pick)
    rows.sort(key=lambda r: (r["per_item"] is None, r["per_item"] or 0, r["name"]))
    timed = [r for r in rows if r["time"]]
    together = None
    if timed and len(timed) == len(rows):
        usual = sum(r["calls"] * r["time"]["per_call_seconds"]["usual"] for r in rows) / at_once
        slow = sum(r["calls"] * r["time"]["per_call_seconds"]["slow_day"] for r in rows) / at_once
        together = {"usual": speed.short(usual), "slow_day": speed.short(slow)}
    notes = list(FORECAST_NOTES)
    if wrong_answer_cost is not None:
        notes.insert(0, f"The pick counts each wrong answer at {forecast.dollars(wrong_answer_cost)}.")
    if all(r["right"] is None for r in rows):
        notes.insert(0, "The sample has no checks (asserts), so how often each model was right is unknown: add them "
                        "to know which to pick.")
    headline = _forecast_headline(rows, pick, items, at_once, wrong_answer_cost, priced=s is not None)
    return {"pick": pick["model"] if pick else None, "headline": headline,
            "sample": {"file": str(promptfoo_results), "eval": sample["eval"], "tests": sample["items"],
                       "results": sample["results"], "at_once": sample["at_once"],
                       "took": speed.short(sample["seconds"]) if sample["seconds"] else None},
            "job": {"tests": items, "at_once": at_once, "every_model_in_the_sample": together},
            "models": [{k: v for k, v in r.items() if k not in ("name", "per_item")} for r in rows],
            "notes": notes, **(footer(s) if s else {})}


def _share(r):
    x = r["right"]
    return f"{x['right']} of {x['of']}, {round(100 * x['low'])}% to {round(100 * x['high'])}%"


def _forecast_headline(rows, pick, items, at_once, wrong_answer_cost, priced=True):
    if pick is None:
        if not priced:
            return ("Prices could not be loaded (no data yet, and no internet), so the job cannot be priced; the times "
                    "are below.")
        return "None of these models has a price in the catalogue, so the job cannot be priced; the times are below."
    graded = [r for r in rows if r["right"] is not None and r["per_item"] is not None]
    cheapest = min((r for r in rows if r["per_item"] is not None), key=lambda r: r["per_item"])
    if pick["right"] is None:
        why = "the cheapest here; the sample has no checks to say how often each was right"
    elif wrong_answer_cost is not None:
        why = (f"the lowest cost an item when a wrong answer costs {forecast.dollars(wrong_answer_cost)} "
               f"({_share(pick)})")
    else:
        top = max(graded, key=lambda r: (r["right"]["share"], r["right"]["of"]))
        if top is pick or top["right"]["share"] == pick["right"]["share"]:
            why = f"right most often in the sample ({_share(pick)})" + (", and the cheapest" if pick is cheapest
                                                                         else "")
        else:
            why = (f"right {_share(pick)}; the sample cannot tell it apart from {top['name']} ({_share(top)}), and "
                   "it costs less")
    job = pick["cost"]["cheapest"]
    line = (f"{pick['name']} is the pick: {why}. The whole job ({items:,} tests, {at_once} at once) costs about "
            f"{forecast.dollars(job['whole_job'])} on {job['host']}")
    if pick["time"]:
        line += f" and takes {pick['time']['usual']} usually, {pick['time']['slow_day']} on a slow day"
    return line + "."


HOURS_A_MONTH = 365 * 24 / 12
LOCAL_NOTES = [
    "The computer's price is yours: no openly licensed table of computer prices with dates exists, so none is used.",
    "The local model's speed comes only from your own timed runs of it (log_run, or a promptfoo run of an ollama: "
    "provider); no public speed table is used, because the open ones do not measure your computer.",
    "A local model answers one call at a time here, so its hours of work a month are calls times the time of a call.",
    "Not counted: what the computer is worth later, its other uses, your time, and cloud price changes (each "
    "cloud listing's 90-day chance of one is shown).",
    "A local model is often smaller than a cloud one: compare both on a sample with forecast_job before you buy.",
]


def _power_price(s, electricity_price, state):
    """(dollars per kWh, where it is from) or (None, why not)."""
    if electricity_price is not None:
        return electricity_price, "the price you gave"
    power = (s.data.get("electricity") if s else None) or {}
    if not power:
        return None, "this data has no electricity prices"
    if state:
        found = next((k for k in power["states"] if k.lower() == state.strip().lower()), None)
        if found is None:
            raise NotFound(f"Unknown state {state!r}; use a US state name such as Texas, or give electricity_price.")
        return power["states"][found], f"{found} homes, {power['label']}. {power['credit']}"
    return power["us"], f"the US average for homes, {power['label']}. {power['credit']}"


def local_or_cloud(s, local_model, cloud_models, input_tokens, output_tokens, calls_per_month, hardware_price,
                   watts=None, electricity_price=None, state=None, months=36, cached_tokens=0, local_way="ollama",
                   thinking=False):
    """Pay a cloud model per call, or buy a computer and run an open model at home: the monthly cost each way, the
    month buying pays off, and whether the computer keeps up. Speed from your own timed runs; electricity from EIA
    (public domain) or your own price; the computer's price is yours."""
    if not 1 <= len(cloud_models) <= 5:
        raise NotFound("Give 1 to 5 cloud models to compare with.")
    if calls_per_month <= 0 or hardware_price < 0 or months < 1:
        raise NotFound("calls_per_month must be more than 0, hardware_price 0 or more, and months 1 or more.")
    if watts is not None and watts <= 0:
        raise NotFound("watts must be more than 0: the power the computer draws while it answers.")
    if local_way not in speed.WAYS:
        raise NotFound(f"Unknown way {local_way!r}; use one of: " + ", ".join(speed.WAYS))
    kwh_price, power_from = _power_price(s, electricity_price, state)
    timed = speed.estimate_time(local_model, input_tokens, output_tokens, 1, local_way, thinking, 1,
                                resolve=_resolver(s))
    local = {"model": timed["model"], "way": local_way, "runs_used": timed["runs_used"], "hardware_price":
             money(hardware_price), "watts": watts, "electricity_per_kwh": kwh_price, "electricity_from": power_from}
    per_month = None
    if timed.get("per_call_seconds"):
        usual, slow = timed["per_call_seconds"]["usual"], timed["per_call_seconds"]["slow_day"]
        hours = {"usual": calls_per_month * usual / 3600, "slow_day": calls_per_month * slow / 3600}
        local["per_call_seconds"] = timed["per_call_seconds"]
        local["hours_of_work_a_month"] = {k: round(v, 1) for k, v in hours.items()}
        local["keeps_up"] = hours["slow_day"] <= HOURS_A_MONTH
        if not local["keeps_up"]:
            local["note"] = (f"At {calls_per_month:,} calls a month this computer needs {hours['slow_day']:,.0f} hours "
                             f"of work on a slow day, more than the {HOURS_A_MONTH:.0f} hours in a month.")
        if watts is not None and kwh_price is not None:
            per_month = {k: v * watts / 1000 * kwh_price for k, v in hours.items()}
            local["electricity_a_month"] = {k: money(v) for k, v in per_month.items()}
        if timed.get("rough"):
            local["rough"] = timed["rough"]
    else:
        local["note"] = (f"No timed runs of {timed['model']} called through {speed.WAY_TEXT[local_way]} yet: time a "
                         "few calls and log them (log_run) to count electricity and check the computer keeps up.")
    missing = []
    if not timed.get("per_call_seconds"):
        missing.append(f"timed runs of {timed['model']} (log_run)")
    if watts is None:
        missing.append("watts (the power the computer draws while it answers: its spec sheet or a plug-in power meter)")
    if kwh_price is None:
        missing.append("electricity_price (this data has no electricity prices)")
    if missing:
        local["missing"] = missing
    rows = []
    for group in resolve_all(s, cloud_models):
        hit = listing(s, group, input_tokens=input_tokens, output_tokens=output_tokens, cached_tokens=cached_tokens)
        if not hit:
            rows.append({"model": group, "note": "no text price listed"})
            continue
        m, call = hit
        monthly = call * calls_per_month
        row = {"model": group, "listing": m["key"], "host": m["host"], "price_per_1m": prices(m),
               "per_call": money(call), "per_month": money(monthly), "over_months": money(monthly * months),
               "price_change_90_days": _outlook(m)}
        pays_off = {}
        for case in ("usual", "slow_day"):
            power = per_month[case] if per_month else 0.0
            saving = monthly - power
            pays_off[case] = round(hardware_price / saving, 1) if saving > 0 else None
        row["buying_pays_off_after_months"] = pays_off if per_month else {"before_electricity": pays_off["usual"]}
        local_total = hardware_price + (per_month["usual"] if per_month else 0.0) * months
        row["saving_over_months"] = money(monthly * months - local_total)
        rows.append(row)
    rows.sort(key=lambda r: r.get("per_month") if r.get("per_month") is not None else float("inf"))
    return {"headline": _local_headline(local, rows, months, per_month), "months": months,
            "calls_per_month": calls_per_month, "local": local, "cloud": rows, "notes": LOCAL_NOTES,
            **footer(s)}


def _months(x):
    return "never" if x is None else f"{x:g} months"


def _local_headline(local, rows, months, per_month):
    priced = [r for r in rows if r.get("per_month") is not None]
    if not priced:
        return "None of these cloud models has a text price listed."
    cheap = priced[0]
    name, cost = cheap["model"].split(" / ", 1)[-1], forecast.dollars(cheap["per_month"])
    when = cheap["buying_pays_off_after_months"]
    if per_month is None:
        if when["before_electricity"] is None:
            return f"{name} costs nothing a month here, so buying never pays off."
        return (f"Against {name} at {cost} a month, the computer pays for itself after "
                f"{_months(when['before_electricity'])} at the earliest; electricity is not counted yet, for that give "
                + " and ".join(local["missing"]) + ".")
    if when["usual"] is None:
        return f"Running it at home costs more each month than {name} ({cost} a month), so buying never pays off."
    line = (f"Against {name} at {cost} a month, the computer pays for itself after about {_months(when['usual'])} "
            f"({_months(when['slow_day'])} on slow days), with {forecast.dollars(per_month['usual'])} of electricity a "
            "month")
    if when["usual"] > months:
        line += f": later than the {months} months asked about"
    if not local.get("keeps_up", True):
        line += "; but it cannot keep up with this many calls"
    return line + "."


# ---------- your usage on other models (REQ-S55) ----------
USAGE_NOTES = (
    "Every model is priced at your token counts. Another model would tokenise the same work a little differently "
    "(usually within 10 to 20%) and might answer in more or fewer tokens, so read the costs as the same work at the "
    "same size.",
    "A model with no cache read or cache write price in the catalogue has those tokens counted at its input price; "
    "its row says so.",
)


def _own_listing(s, group, tokens):
    """The listing the user most likely paid: the maker's own host when it has a text price, else the cheapest."""
    hit = listing(s, group, hosts=(group.split(" / ", 1)[0],), **tokens)
    return hit or listing(s, group, **tokens)


def _priced_on(s, m, day, cache_days):
    """A copy of listing m with the prices it had at the end of `day` (its first prices for days before it was
    listed), per 1M tokens, in the shape cost_of reads."""
    key = (m["key"], day)
    if key not in cache_days:
        p = price_on(s, m, day)
        before = not p["listed"]
        if before:
            p = price_on(s, m, m.get("added") or (s.data.get("built") or "")[:10])
        prices_ = p.get("price_per_1m") or {}
        cache_days[key] = ({"input": prices_.get("input"), "output": prices_.get("output"),
                            "cache_read": prices_.get("cache_read"), "cache_write": prices_.get("cache_write")}, before)
    return cache_days[key]


def _unit_cost(model, u):
    prompt = u["input"] + u["cache_read"] + u["cache_write"]
    return logic.cost_of(model, prompt, u["output"], u["cache_read"], u["cache_write"])


def price_my_usage(s, export=None, mix=None, task=None, compare=None, limit=25):
    """Your own coding agent usage, read from a ccusage or codeburn export (or a plain token mix), priced on every
    comparable model at the price of each day, with Arena ratings for the kind of work and a bootstrap range for
    the cost per session. Lists the models that keep the rating (their rating's high end reaches the low end of
    your most used model's) and cost less than you paid in all, and says whether two models differ for real or the
    data cannot tell. Token counts only; nothing is sent anywhere."""
    if (export is None) == (mix is None):
        raise NotFound("Give either export (a path to a ccusage or codeburn JSON export) or mix (a list of token mixes).")
    if task is not None:
        _check(task=task)
    if compare is not None and len(compare) != 2:
        raise NotFound("compare takes exactly two model names.")
    if not 1 <= limit <= 200:
        raise NotFound("limit must be between 1 and 200.")
    try:
        read = usage.read(export if export is not None else mix)
    except usage.BadExport as error:
        raise NotFound(str(error)) from None
    units = [u for u in read["units"] if u["input"] + u["output"] + u["cache_read"] + u["cache_write"] > 0]
    if not units:
        raise NotFound(f"Nothing to price in {read['source']}: no model rows with tokens." + " ".join(read["notes"]))
    notes = list(read["notes"])

    # the models used, by grouped name
    groups_of, unknown = {}, {}
    for name in sorted({u["model"] for u in units}):
        group, _ = s.resolve(name)
        if group is None:
            unknown[name] = sum(u["input"] + u["output"] + u["cache_read"] + u["cache_write"] for u in units if u["model"] == name)
        else:
            groups_of[name] = group
    units = [u for u in units if u["model"] in groups_of]
    if not units:
        raise NotFound("None of the models in the export is in the catalogue: " + ", ".join(unknown) +
                       ". Pass the names as LiteLLM lists them, or use find_models to see them.")
    if unknown:
        notes.append("Not in the catalogue, so left out: " + ", ".join(f"{n} ({t:,} tokens)" for n, t in unknown.items()) + ".")
    today = (s.data.get("built") or "")[:10]
    undated = sum(1 for u in units if not u["day"])
    if undated:
        for u in units:
            u["day"] = u["day"] or today
        notes.append(f"{undated} of {len(units)} rows carry no date; they are priced at today's prices ({today}).")
    if task is None:
        tasks = [u["task"] for u in units if u["task"]]
        task = max(set(tasks), key=tasks.count) if tasks else "coding"
    sessions = sorted({u["session"] for u in units})
    days = sorted({u["day"] for u in units if u["day"]})
    totals = {"input": sum(u["input"] for u in units), "output": sum(u["output"] for u in units),
              "cache_read": sum(u["cache_read"] for u in units), "cache_write": sum(u["cache_write"] for u in units)}
    tokens = {"input_tokens": totals["input"] + totals["cache_read"] + totals["cache_write"],
              "output_tokens": totals["output"], "cached_tokens": totals["cache_read"],
              "written_tokens": totals["cache_write"]}
    cache_days = {}

    # what the user paid: each used model on the maker's own host, at each day's prices
    used = []
    for group in sorted({groups_of[u["model"]] for u in units}):
        mine = [u for u in units if groups_of[u["model"]] == group]
        hit = _own_listing(s, group, tokens)
        if not hit:
            notes.append(f"{group} has no text price listed, so what you paid for it cannot be priced.")
            continue
        m = hit[0]
        by_session = {}
        for u in mine:
            model, _ = _priced_on(s, m, u["day"], cache_days)
            by_session[u["session"]] = by_session.get(u["session"], 0.0) + (_unit_cost(model, u) or 0.0)
        r = s.rating_of(task, group)
        used.append({"model": group, "listing": m["key"], "host": m["host"], "sessions": len(by_session),
                     "tokens": {k: sum(u[k] for u in mine) for k in ("input", "output", "cache_read", "cache_write")},
                     "cost": money(sum(by_session.values())),
                     "per_session": _range(list(by_session.values())),
                     "rating": {"score": r[2], "low": r[3], "high": r[4]} if r else None,
                     "one_shot": next((x for x in (usage.one_shot(read["efficiency"], n) for n, g in groups_of.items() if g == group) if x), None),
                     "_sessions": by_session})
    if not used:
        raise NotFound("None of the models used has a text price in the catalogue.")
    used.sort(key=lambda r: -(r["tokens"]["input"] + r["tokens"]["output"] + r["tokens"]["cache_read"] + r["tokens"]["cache_write"]))
    main = used[0]
    paid = sum(r["cost"] for r in used)

    # the same work on every rated model, each at its cheapest listing, at each day's prices
    rated = {r[0]: r for r in s.ratings.get(task, [])}
    candidates = sorted(set(rated) | {r["model"] for r in used} | set(resolve_all(s, compare) if compare else ()))
    rows = []
    for group in candidates:
        hit = listing(s, group, **tokens)
        if not hit:
            continue
        m = hit[0]
        by_session, before = {}, 0
        for u in units:
            model, early = _priced_on(s, m, u["day"], cache_days)
            before += early
            by_session[u["session"]] = by_session.get(u["session"], 0.0) + (_unit_cost(model, u) or 0.0)
        total = sum(by_session.values())
        r = rated.get(group)
        row = {"model": group, "listing": m["key"], "host": m["host"],
               "rating": {"score": r[2], "low": r[3], "high": r[4]} if r else None,
               "cost": money(total), "per_session": _range(list(by_session.values())),
               "versus_yours": {"saving": money(paid - total), "share": round((paid - total) / paid, 4) if paid else None},
               "keeps_rating": bool(r and main["rating"] and r[4] >= main["rating"]["low"]),
               "cache_priced": m.get("cache_read") is not None or not totals["cache_read"],
               "_sessions": by_session}
        if before:
            row["note"] = (f"Listed since {m.get('added')}: {before} of your {len(units)} rows are from before that "
                           "and are priced at its first prices.")
        if totals["cache_read"] and m.get("cache_read") is None:
            row["note"] = (row.get("note", "") + " No cache price listed: cache tokens counted at the input price.").strip()
        rows.append(row)
    rows.sort(key=lambda r: r["cost"])
    cheaper = [r for r in rows if r["keeps_rating"] and r["cost"] < paid and r["model"] not in {x["model"] for x in used}]

    # two models, for real or luck
    tests = []
    if compare:
        a, b = resolve_all(s, compare)
        ra, rb = ({r["model"]: r for r in rows}.get(a), {r["model"]: r for r in rows}.get(b))
        if not (ra and rb):
            raise NotFound("Both models to compare need a text price; " + ", ".join(n for n, r in ((a, ra), (b, rb)) if not r) + " has none.")
        diffs = [ra["_sessions"][k] - rb["_sessions"][k] for k in sessions if k in ra["_sessions"] and k in rb["_sessions"]]
        got = usage.bootstrap_mean(diffs)
        tests.append({"kind": "same work", "models": [a, b], "sessions": len(diffs),
                      "difference_per_session": _triple(got),
                      "verdict": usage.verdict(got[1], got[2], "cost per session") if got else
                      f"not enough sessions: {len(diffs)} of the {usage.MIN_SESSIONS} needed",
                      "note": f"The same {len(diffs)} sessions priced on both, so this is the price gap at your token counts."})
    elif len(used) >= 2:
        a, b = used[0], used[1]
        got = usage.bootstrap_difference(list(a["_sessions"].values()), list(b["_sessions"].values()))
        test = {"kind": "as used", "models": [a["model"], b["model"]], "sessions": [a["sessions"], b["sessions"]],
                "difference_per_session": _triple(got),
                "verdict": usage.verdict(got[1], got[2], "cost per session") if got else
                f"not enough sessions: {a['sessions']} and {b['sessions']}, {usage.MIN_SESSIONS} each needed",
                "note": ("Different sessions went to each model, so a gap here is partly the work you gave each, "
                         "not only the price.")}
        if a["one_shot"] and b["one_shot"]:
            oa, ob = (a["one_shot"]["low"], a["one_shot"]["high"]), (b["one_shot"]["low"], b["one_shot"]["high"])
            test["one_shot"] = {"rates": [a["one_shot"], b["one_shot"]],
                                "verdict": ("not enough data to tell the two apart on one-shot rate: the 95% ranges overlap"
                                            if forecast.overlap(oa, ob) else
                                            "a real difference in one-shot rate: the 95% ranges do not overlap")}
        tests.append(test)

    for r in used + rows:
        r.pop("_sessions", None)
    shown = rows[:limit]
    for r in used:
        if r["model"] not in {x["model"] for x in shown}:
            shown.append(next(x for x in rows if x["model"] == r["model"]))
    return {"source": read["source"], "task": task_label(task), "days": [days[0], days[-1]] if days else None,
            "sessions": len(sessions), "tokens": totals, "you_paid": {"cost": money(paid), "models": used},
            "headline": _usage_headline(used, paid, cheaper, len(sessions), days),
            "cheaper_and_as_good": [{k: v for k, v in r.items() if k != "cache_priced"} for r in cheaper[:10]],
            "every_model": shown, "tests": tests, "notes": notes + list(USAGE_NOTES), **footer(s)}


def _range(values):
    got = usage.bootstrap_mean(values)
    if got is None:
        return {"mean": money(sum(values) / len(values)) if values else None, "low": None, "high": None,
                "note": f"{len(values)} sessions; a range needs {usage.MIN_SESSIONS}"}
    return {"mean": money(got[0]), "low": money(got[1]), "high": money(got[2])}


def _triple(got):
    return None if got is None else {"mean": money(got[0]), "low": money(got[1]), "high": money(got[2])}


def _usage_headline(used, paid, cheaper, sessions, days):
    span = f"{sessions} session{'s' if sessions != 1 else ''}" + (f" ({days[0]} to {days[-1]})" if days and days[0] != days[-1] else f" ({days[0]})" if days else "")
    named = sorted(used, key=lambda r: -r["cost"])[:3]
    on = used[0]["model"] if len(used) == 1 else " and ".join(
        f"{r['model']} ({forecast.dollars(r['cost'])}, {r['sessions']} session{'s' if r['sessions'] != 1 else ''})" for r in named)
    if len(used) > 3:
        on += f" and {len(used) - 3} more model{'s' if len(used) > 4 else ''}"
    paid = f"Your {span} on {on} cost {forecast.dollars(paid)} at each day's prices."
    if not cheaper:
        return paid + " No rated model would have done the same work for less while keeping the rating."
    best = cheaper[0]
    return (paid + f" {len(cheaper)} rated model{'s' if len(cheaper) != 1 else ''} would have done it for less while keeping "
            f"the rating; the cheapest is {best['model']} at {forecast.dollars(best['cost'])}, "
            f"{round(100 * best['versus_yours']['share'])}% less.")
