"""A badge per listed model for any README, in shields.io's endpoint format (site/badge/<slug>.json).

    ![gpt-5](https://img.shields.io/endpoint?url=https://pouriaetab.github.io/llmledger/badge/gpt-5.json)

shows "gpt-5 | $1.25 / $10.00 per 1M · 4.5% chance of a price change in 90 days", refreshed with
the page every day. The slug is the LiteLLM key with / as -- and : as -.
"""
import json
from pathlib import Path

PAGE = "https://pouriaetab.github.io/llmledger/"
COLOURS = {"steady": "2a78d6", "watch": "eda100", "retiring": "eb6834"}


def slug(key):
    return key.replace("/", "--").replace(":", "-")


def money(value):
    if value is None:
        return "–"
    return f"${value:,.2f}" if value >= 0.1 else f"${value:,.4f}"


def badge(model):
    """The endpoint JSON for one listed model (prices are per 1M tokens in data.json)."""
    message = f"{money(model['input'])} / {money(model['output'])} per 1M"
    colour = COLOURS["steady"]
    outlook = (model.get("outlook") or {}).get("90")
    if model.get("retire"):
        message += f" · retirement date {model['retire']}"
        colour = COLOURS["retiring"]
    elif outlook and outlook.get("price"):
        chance = 100 * outlook["price"][0]
        message += f" · {chance:.1f}% chance of a price change in 90 days"
        if chance >= 10:
            colour = COLOURS["watch"]
    return {"schemaVersion": 1, "label": model["name"], "message": message, "color": colour,
            "cacheSeconds": 3600, "llmledger": PAGE}


def write(folder, machine):
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    names = set()
    for model in machine["models"]:
        name = slug(model["key"]) + ".json"
        if name in names:
            continue
        names.add(name)
        with open(out / name, "w") as f:
            json.dump(badge(model), f, separators=(",", ":"))
    return len(names)
