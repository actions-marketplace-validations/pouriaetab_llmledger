"""llmledger as a plug-in (an MCP server) for Claude and other AI apps.

Five tools answer "which model, and what will it cost?" from the same data as the llmledger
page: LiteLLM's price catalogue (MIT), Arena's ratings (CC BY 4.0), and every price change
since 2023 with how likely a price is to change next. Runs on the user's own computer over
stdio; reads the day's data.json, cached for a day.
"""
import time
from typing import Annotated, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from llmledger_mcp import __version__, data, logic

Task = Literal[tuple(logic.TASKS)]
Pay = Literal["api", "claude", "chatgpt"]
Need = Literal["vision", "pdf", "audio", "video", "tools", "reasoning", "web", "schema", "cache", "computer"]
PLANS = {"claude": ("anthropic", "anthropic", "Claude"), "chatgpt": ("openai", "openai", "ChatGPT")}
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
PLAN_NOTE = ("Plan use is an estimate: plans do not publish per-model limits, so it assumes a plan runs down "
             "in step with each model's API price on the maker's own host.")
EFFORT_NOTE = ("The effort level is a rule of thumb from the task and the prompt. Higher effort writes more hidden "
               "answer tokens, and no open source measures how many yet.")

mcp = FastMCP(
    "llmledger",
    instructions=(
        "Which AI model to use, and what it costs. Prices come from LiteLLM's public catalogue, quality from "
        "Arena's votes, and each price's full history from llmledger. Use suggest_for_project for 'which model "
        "for this', compare_models to put 2 to 6 models side by side, estimate_cost for a budget, find_models to "
        "browse, and price_history for one model. Costs and ratings are estimates; pass on the credits line."),
    version=__version__,
)

_SHELF = None


def shelf():
    """The data, loaded once and refreshed after a day."""
    global _SHELF
    if _SHELF is None or time.time() - _SHELF.loaded > data.MAX_AGE:
        _SHELF = data.Shelf(*data.load())
    return _SHELF


def footer(s):
    d = s.data
    return {"data": {"built": d.get("built"), "litellm_changed": (d.get("litellm") or {}).get("changed"),
                     "ratings_published": s.rating_date, "copy": s.where},
            "credits": d.get("credits")}


def listing(s, group, plan=None, input_tokens=0, output_tokens=0, needs=(), min_context=None):
    """The listing a grouped model is priced at: its cheapest text listing, or on a plan the plan's own host."""
    best = None
    for m in s.groups.get(group, []):
        if not logic.is_text_model(m) or (plan and m["host"] != PLANS[plan][1]):
            continue
        if any(n not in (m.get("skills") or []) for n in needs):
            continue
        if min_context and not (m.get("context") or 0) >= min_context:
            continue
        cost = logic.cost_of(m, input_tokens, output_tokens)
        if cost is not None and (best is None or cost < best[1]):
            best = (m, cost)
    return best


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
        raise ToolError("Not found: " + "; ".join(missing) + ". Use find_models to see the names.")
    return groups


def task_label(task):
    return logic.LABELS.get(task, task)


@mcp.tool(annotations=READ_ONLY)
def find_models(
    task: Annotated[Task, Field(description="The kind of work, as Arena rates it")] = "overall",
    max_output_price: Annotated[float | None, Field(description="Highest answer price, dollars per 1M tokens", ge=0)] = None,
    min_context: Annotated[int | None, Field(description="Smallest prompt size the model must take, in tokens", ge=0)] = None,
    needs: Annotated[list[Need], Field(description="What the model must be able to do")] = [],
    maker: Annotated[str | None, Field(description="Only this maker, for example anthropic or openai")] = None,
    limit: Annotated[int, Field(ge=1, le=20)] = 5,
) -> dict:
    """The highest rated models for a kind of work that meet the limits, each at its cheapest listing,
    with prices per 1M tokens, Arena rating and prompt size. Unrated models follow, cheapest first."""
    s = shelf()
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


@mcp.tool(annotations=READ_ONLY)
def compare_models(
    models: Annotated[list[str], Field(description="2 to 6 model names, for example claude-opus-5.5, gpt-6.1-sol", min_length=2, max_length=6)],
    task: Annotated[Task, Field(description="The kind of work, as Arena rates it")] = "overall",
    input_tokens: Annotated[int, Field(description="Prompt tokens per task", ge=0)] = 1000,
    output_tokens: Annotated[int, Field(description="Answer tokens per task, including hidden thinking", ge=0)] = 800,
    answer_tokens: Annotated[dict[str, int] | None, Field(description="Answer tokens per model when they differ, by the names given")] = None,
    pay: Annotated[Pay, Field(description="api: dollars; claude or chatgpt: how fast each uses that plan")] = "api",
) -> dict:
    """Two to six models side by side for a kind of work: rating, prices, cost per task (or plan use), and
    which to pick, with the break-even share of answer tokens for each against the pick."""
    s = shelf()
    groups = resolve_all(s, models)
    own = {}
    for name, n in (answer_tokens or {}).items():
        group, _ = s.resolve(name)
        if group:
            own[group] = n
    plan = pay if pay in PLANS else None
    rows = []
    for group in groups:
        hit = listing(s, group, plan)
        m = hit[0] if hit else None
        out = own.get(group, output_tokens)
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


@mcp.tool(annotations=READ_ONLY)
def estimate_cost(
    models: Annotated[list[str], Field(description="1 to 10 model names", min_length=1, max_length=10)],
    input_tokens: Annotated[int, Field(description="Prompt tokens per call", ge=0)],
    output_tokens: Annotated[int, Field(description="Answer tokens per call, including hidden thinking", ge=0)],
    cached_tokens: Annotated[int, Field(description="How many of the prompt tokens are read from the cache", ge=0)] = 0,
    calls_per_day: Annotated[float, Field(description="Calls per day", ge=0)] = 1,
) -> dict:
    """What a workload costs on each model at its cheapest listing: per call, per day and per 30 days."""
    s = shelf()
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


@mcp.tool(annotations=READ_ONLY)
def price_history(
    model: Annotated[str, Field(description="A model name, for example claude-opus-5.5, or one listing such as bedrock/anthropic.claude-opus-5-5")],
) -> dict:
    """Every change to a model's listings since 2023 (prices, retirement dates), and for listings that have not
    changed yet, the chance of a price change, a retirement date or removal in the next 90 days and year."""
    s = shelf()
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
    return {"model": group, "listings": out, "listings_in_total": len(s.groups[group]),
            "notes": ["Prices per 1M tokens. A flag marks a bulk clean up, a unit fix or a change that was undone.",
                      "The outlook covers listings that have not changed since they were added: Aalen-Johansen estimates "
                      "with 95% intervals, among listings of the same age. What usually happens in the catalogue, not a "
                      "forecast for one model."], **footer(s)}


@mcp.tool(annotations=READ_ONLY)
def suggest_for_project(
    prompt: Annotated[str, Field(description="The project's starting prompt, or a description of the work")],
    pay: Annotated[Pay, Field(description="api: dollars; claude or chatgpt: compare within that plan")] = "api",
    answer: Annotated[Literal["short", "medium", "long", "very_long"], Field(description="Typical answer length")] = "medium",
) -> dict:
    """Reads a prompt, guesses its kind of work, and suggests a model and effort level: the best value (the
    cheapest whose rating the votes cannot tell apart from the top), the top rated and the cheapest rated."""
    s = shelf()
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
        raise ToolError("No rated model matches; try pay='api'.")
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


@mcp.resource("llmledger://snapshot", mime_type="application/json")
def snapshot() -> dict:
    """What the plug-in knows today: data dates, how many models and rated tasks, and the sources."""
    s = shelf()
    return {"models_listed": len(s.models), "grouped_models": len(s.groups),
            "rated_tasks": {k: len(v) for k, v in s.ratings.items()}, "tasks": logic.LABELS, **footer(s)}


@mcp.prompt
def pick_a_model(work: str) -> str:
    """Pick a model for a piece of work, with its cost and effort."""
    return ("Use the llmledger tools to pick an AI model for this work:\n\n" + work + "\n\n"
            "1. Call suggest_for_project with the work as the prompt.\n"
            "2. Call compare_models with its three picks and the task it returned.\n"
            "3. Answer in five lines or fewer: the pick, its cost per task, the effort level, the runner up and why, "
            "and the credits line.")


def main():
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
