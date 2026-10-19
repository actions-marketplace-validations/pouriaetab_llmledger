---
name: llmledger
description: Pick an AI model and price AI work from public data. Today's price of every model in LiteLLM's catalogue at its cheapest host, Arena quality ratings by kind of work, and each price's history since 2023 with the chance it changes soon. Use when someone asks which LLM to use, what a prompt, job or monthly workload will cost on different models, how models compare on price and quality, or whether a model's price has changed.
license: MIT
compatibility: Python 3.10 or newer, standard library only. Downloads the day's data from pouriaetab.github.io once a day and keeps it in ~/.cache/llmledger-mcp/. No keys.
metadata:
  version: "0.1.4"
  source: https://github.com/pouriaetab/llmledger
---

# llmledger

Run `python3 scripts/llmledger.py <command>` from this skill's folder. Every command prints one JSON object.
The same answers as the llmledger plug-in (llmledger-mcp), from the same daily data.

## Commands

| Command | Use it for |
|---|---|
| `suggest "<the prompt or the work>" [--pay api\|claude\|chatgpt] [--answer short\|medium\|long\|very_long]` | Which model for this: guesses the kind of work and gives the best value, the top rated and the cheapest rated, each with its cost per task and effort level |
| `compare MODEL MODEL [...] [--task T] [--input N] [--output N] [--pay ...]` | 2 to 6 models side by side: rating, price, cost per task, which to pick and why |
| `cost MODEL [...] --input N --output N [--cached N] [--cache-write N] [--calls-per-day N]` | A budget: cost per call, per day and per 30 days; with cached tokens, also the cost without the cache and the saving |
| `find [--task T] [--needs vision,tools,...] [--max-output-price X] [--min-context N] [--maker M] [--limit N]` | The highest rated models for a kind of work within limits |
| `history MODEL [--date YYYY-MM-DD]` | Every price change of a model's listings with a link to the LiteLLM change behind it, and the chance of a price change, a retirement date or removal in the next 90 days and year; with a date, the prices that day |
| `unpriced [--maker M]` | New models on Arena that no price list has yet, and how soon prices usually appear, by maker |
| `tasks` | The kinds of work (`--task` values) and the data's dates |

Model names can be written loosely (`claude-opus-5.5`, `gpt 6.1`) or as one listing (`bedrock/anthropic.claude-opus-5-5`).
An unknown name returns `{"error": ...}` with close names to try. Tokens: about 4 characters of English text each.

## How to answer

1. For "which model", run `suggest` with the user's own prompt or a short description of the work, then
   `compare` the picks if they want more detail. Use `--pay claude` or `--pay chatgpt` when they use a plan.
2. Give prices per 1M tokens and costs in dollars, and say which host each price is for (the cheapest listing).
3. Say ratings are Arena votes for the kind of work, and that overlapping ranges mean the votes cannot tell the
   models apart.
4. In `history`, a change flagged `likely`, `unit` or `reverted` is probably a fix of the catalogue, not a real
   price change; the `flags` and `notes` fields say what each means. The outlook is what usually happens to
   similar listings, not a forecast for one model.
5. If `data.warning` or `data.offline` is present, tell the user the data is old or offline, with `data.prices_as_of`.
6. End with the credits: prices from LiteLLM (MIT), ratings from Arena (CC BY 4.0), via llmledger. Costs are
   estimates, not financial or procurement advice.
