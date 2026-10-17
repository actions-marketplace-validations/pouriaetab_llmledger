"""A machine-readable copy of each day's data, published as site/data.json.

The page reads data.js; programs (the llmledger-mcp plug-in, scripts, notebooks) read this
file instead: every listed model with its prices, effort levels and outlook, every change
to those models, and the Arena ratings by task. Same sources and licences as the page.
"""
import json
import math

SCHEMA = 1
FIELDS = ("key", "maker", "name", "host", "mode", "status", "added", "removed", "retire",
          "input", "output", "repriced", "last", "exit", "age", "skills", "size", "media",
          "cache", "effort", "effort_default")
OUTCOMES = ("price", "retirement", "removed", "none")
CREDITS = {
    "prices": "LiteLLM's model_prices_and_context_window.json (MIT), https://github.com/BerriAI/litellm",
    "ratings": "Arena leaderboard (CC BY 4.0), https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset",
    "note": "Estimates from a public catalogue and public votes. Not financial or procurement advice.",
}


def outlook(model, curves, horizons=("90", "365")):
    """The chance of each first change within the horizon, for a listed model that has not
    changed since it was added, among models of the same age (as the page shows it)."""
    if model["status"] != "listed" or not model["added"] or model["exit"] or model["age"] is None:
        return None
    group = model["host"] if model["host"] in curves else "all"
    start = math.floor(model["age"] / 7) * 7
    found = {}
    for horizon in horizons:
        row = next((r for r in curves[group].get(horizon, []) if r[0] == start), None)
        if row is None:
            continue
        found[horizon] = {"followed": row[1], **{
            outcome: row[2 + 3 * i:5 + 3 * i] for i, outcome in enumerate(OUTCOMES)}}
    return {"group": group, "age_days": round(model["age"]), **found} if found else None


def machine(data, info):
    """The dictionary written to data.json."""
    models, events = [], {}
    for record in data["models"]:
        m = dict(zip(FIELDS, record))
        if m["status"] != "listed":
            continue
        models.append({
            "key": m["key"], "maker": m["maker"], "name": m["name"], "host": m["host"], "mode": m["mode"],
            "input": m["input"], "output": m["output"], "cache_read": m["cache"], "context": m["size"],
            "skills": m["skills"], "effort": m["effort"], "effort_default": m["effort_default"],
            "added": m["added"], "retire": m["retire"], "price_changes": m["repriced"], "last_change": m["last"],
            "outlook": outlook(m, data["curves"]),
        })
        events[m["key"]] = data["events"].get(m["key"], [])
    arena = data.get("arena")
    return {
        "schema": SCHEMA,
        "built": info["built"].isoformat(),
        "litellm": {"commit": info["sha"], "changed": info["when"].isoformat()},
        "credits": CREDITS,
        "units": {"prices": "dollars per 1M tokens", "events": ["day", "kind", "field", "old", "new", "flag"],
                  "ratings": ["model", "arena name", "rating", "low", "high", "votes", "arena rank"],
                  "outlook": "estimate, low and high of a 95% interval, by outcome"},
        "models": models,
        "events": events,
        "ratings": None if not arena else {
            "date": arena["date"], "source": arena["source"], "labels": arena["labels"], "tasks": arena["tasks"]},
    }


def write(path, data, info):
    with open(path, "w") as f:
        json.dump(machine(data, info), f, separators=(",", ":"))
