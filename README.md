# llmledger

[![tests](https://github.com/pouriaetab/llmledger/actions/workflows/tests.yml/badge.svg)](https://github.com/pouriaetab/llmledger/actions/workflows/tests.yml)
[![refresh](https://github.com/pouriaetab/llmledger/actions/workflows/refresh.yml/badge.svg)](https://github.com/pouriaetab/llmledger/actions/workflows/refresh.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.12 | 3.14](https://img.shields.io/badge/python-3.12%20%7C%203.14-blue.svg)
[![Data: LiteLLM](https://img.shields.io/badge/data-LiteLLM-informational.svg)](https://github.com/BerriAI/litellm)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23330454.svg)](https://doi.org/10.5281/zenodo.23330454)

What happens to an LLM after it is added to a price catalogue? llmledger rebuilds
the full change history of LiteLLM's model price file and estimates how likely a
newly added model is to have its price changed, get a retirement date, or be
removed, within 30 days to 2 years.

**Live results, rebuilt every day:** https://pouriaetab.github.io/llmledger/

**Status:** version 1.16. The data and the page refresh every day.

Paste a prompt on the live page to see the best value model for it, the top rated one and the
cheapest rated one, with what each costs and the chance its price changes in the next 90 days.
Everything else (compare, cost vs quality, every model, quality ratings, price history, method) is
one click away. A view fits one screen when it can; when it has more, the page scrolls the normal
way and nothing is cut. The Trends view
replays two years of Arena's leaderboards and what top quality has cost.

> **Not financial or procurement advice.** The numbers describe edits to a public
> catalogue, not what any model costs you. See [DISCLAIMER.md](DISCLAIMER.md).

## What it does

1. **Rebuilds the history.** Reads every version of
   `model_prices_and_context_window.json` that LiteLLM's `main` branch went
   through, in order, using git.
2. **Writes a change log.** Compares each version with the one before and records
   one row per change: a model added or removed, a price changed, a retirement
   date set (`data/events.csv`).
3. **Estimates competing risks.** Follows each newly added model until its first
   exit (a price change, a retirement announcement or removal) and estimates the
   chance of each with the Aalen-Johansen estimator and 95% bootstrap confidence
   intervals (`data/survival.csv`).
4. **Publishes the results.** Rebuilds the results page from LiteLLM's latest
   history every day (`site/index.html`).
5. **Looks up any model.** Search by name, maker or host, under LiteLLM's own
   names or grouped by model, to see each listing's chance of a price change in
   the next 90 days and year, its timeline and full outlook, and a side by side
   comparison of up to five models. The page also lists every change in the
   last 7 days and the most repriced models. Every table sorts, keeps its
   header in view and lets you move columns, and remembers all of it.
6. **Flags corrections.** Tags bulk clean ups (50 or more models removed on the
   same day), unit fixes (a price made 100 times larger or smaller), changes
   undone within 30 days and likely corrections (a price change in a model's
   first 7 days, from 0, or of 10 times or more), and shows the results with
   and without them.
7. **Checks itself in SQL.** Every run builds the table of models a second time
   in SQL (`survival.sql`, run with SQLite) and stops before publishing if SQL
   and Python disagree on any model.
8. **Prices a prompt.** Paste a prompt to see what it would cost on every listed
   model, cheapest first, next to each model's chance of a price change in the
   next 90 days. It covers text answers (with images, PDF pages, audio or video
   attached), and making images, video or speech. Filter by what a model must
   be able to do, and by maker, model, version and host. The prompt stays in
   your browser.
9. **Finds the best value for a task.** For 26 tasks, from coding, math and
   writing to 7 fields, 7 languages, images, documents and websites, it marks
   the cheapest model whose Arena rating cannot be told apart from the top
   model's.
10. **Guesses the task of a prompt.** From its words and attachments, in the
    browser, it guesses the task (coding, math, a field or a language) and
    picks the best value model for it. On 1,740 real Arena prompts kept apart
    from the ones used to write the rules, it picks one of the prompt's tasks
    69.7% of the time (67.5 to 71.8%), against 45.4% for always guessing
    Everything (overall).
11. **Checks licences every day.** Before building, it reads the current licence
    of every outside source. If one is no longer open for business use, it
    stops using it (or stops publishing, for the core data) and opens a GitHub
    issue.
12. **Compares models side by side.** Columns that follow the prompt (the
    three answers, or a Claude or ChatGPT plan's top rated models) plus up to
    three of your own: Arena rating and rank, effort levels with a suggested
    level, prices, answer tokens and cost per task, or how fast each uses the
    plan. It names the pick and says, for each other model, how few answer
    tokens it would need to cost the same.
13. **Works inside Claude.** The plug-in in `mcp/` (llmledger-mcp) answers the
    same questions inside Claude, Cursor or any app that speaks MCP, from the
    daily `data.json`. See [Use it inside Claude](#use-it-inside-claude).
14. **Replays the leaderboards.** The Trends view plays every past Arena
    leaderboard as a moving chart: the best closed model against the best
    open one (and how often people would pick the leader), the top 5 makers,
    and a price race: the top rated model's price, the cheapest of the top 10,
    and what a model as good as last year's #1 costs now, rebuilt from every
    price change in the catalogue. Next to it: the newest models with their
    best Arena rank, and the latest price changes and retirements.
15. **Shows cost against quality.** For your prompt, every rated model's cost
    against its Arena score, with the edge marked: the models no other model
    beats on both.
16. **One page when it fits, otherwise it scrolls.** The answers come first,
    the extras are tabs in one panel under them, shown at their full height,
    and a model's details open in a drawer. When a view has more than the
    window holds, the page scrolls the normal way: nothing is cut, squeezed
    into a box that scrolls inside, or shrunk to fit. About shows each part
    as a row that opens on a click.
17. **Measures how many price changes are corrections.** A labelled random
    sample of first price changes, with a written guide, shows how often the
    catalogue fixes its own entry instead of recording a real price change,
    and how well simple rules and a small model tell the two apart. See
    [How many first price changes are corrections?](#how-many-first-price-changes-are-corrections)
18. **Checks every build before it goes live.** A build that knows fewer
    models than the live page, lists a quarter fewer, or has older data is
    not published. When the data is 3 or more days old, the page and the
    plug-in say so, and a failed daily refresh opens an issue in this
    repository until a refresh passes again.
19. **Works as an Agent Skill too.** The folder `skills/llmledger` gives AI
    agents the plug-in's answers through a small script, standard library
    only. Until it is used, the skill takes about 150 tokens of an agent's
    context, against well over 1,000 for the plug-in's tools. See
    [Use it inside Claude](#use-it-inside-claude).
20. **Lists models seen but not yet priced.** New models on Arena that the
    catalogue has no price for, and how soon a model usually gets one after
    Arena first shows it, by maker (Price history, Not yet priced).
21. **Shows where each change came from.** Every change in a model's timeline
    links the LiteLLM change behind it, and the plug-in gives a model's prices
    on any past day with the change that set them. Estimates count cache reads
    and cache writes, and an answer from the offline copy says how old it is.
22. **Learns how long your jobs take.** The plug-in times a job (one call and
    the whole job, as a usual time and a slow day) from your own timed runs,
    kept on your computer, including promptfoo's results files; and promptfoo
    can check the plug-in's answers against the data. See
    [docs/promptfoo.md](docs/promptfoo.md).
23. **Quotes a whole job from a sample.** Run 20 of a job's tests in promptfoo,
    and the plug-in quotes the whole job on each model in it: time as a usual
    time and a slow day, cost at the cheapest listing next to the one used, the
    chance of a price change within 90 days, how often it was right with a 95%
    range, and what a wrong answer must cost for the dearer model to pay off.

## First results

A snapshot; the live page above has the current numbers.

5,256 models added after the catalogue's first recorded version
(6 September 2023), followed until 13 October 2026. Each cell is the estimated
share of models whose first exit was this one, with its 95% confidence interval.

| Within | Price change | Retirement announced | Removed | None of these |
|:--|--:|--:|--:|--:|
| 1 year | 14.7% (13.5 to 15.9) | 16.4% (15.2 to 17.7) | 16.3% (15.3 to 17.4) | 52.6% (50.9 to 54.3) |
| 2 years | 18.3% (16.9 to 19.7) | 29.5% (27.6 to 31.4) | 23.4% (21.7 to 25.0) | 28.8% (26.8 to 31.2) |

Each row adds up to 100% because the three exits compete: once a model is
removed, its price can no longer change. Analysing each exit on its own would
overstate all three.

Counting only input and output token prices, the one year price change estimate
is 12.5%. Ignoring price changes in a model's first week, it is 12.0%. Many of
the changes counted are corrections of the catalogue, not real price changes:
see the next section. On the data of 18 October 2026, leaving out likely
corrections as well as unit fixes and undone changes, it is 10.0% (9.1 to
11.1), against 14.6% (13.5 to 15.7) counting every change; that still counts
some corrections.

Corrections and clean ups matter more for removals. The one year removal
estimate above includes a clean up that removed about 500 OpenRouter rows on
9 October 2026. Leaving out bulk clean ups, unit fixes and reverted changes, it
is 5.7% (5.0 to 6.5).

### How many first price changes are corrections?

A stratified random sample of 200 models' first price changes (100 from a
model's first 7 days, 100 from later, out of 800) was labelled from the LiteLLM
commit behind each change: a correction when the catalogue's number had been
wrong, a repricing when the host changed its price, unclear when the evidence
cannot tell (33 rows). The guide, every label and its reason are in
[`docs/corrections`](docs/corrections); the numbers are in
`src/llmledger/corrections_eval.json`. Intervals are 95%, from a bootstrap of
whole LiteLLM commits, since one commit often changes many rows.

| First price changes | Share that are corrections |
|:--|--:|
| All | 59% (41 to 75) |
| In a model's first 7 days | 86% (54 to 97) |
| Later | 51% (34 to 71) |

How well simple rules find the corrections:

| Rule | Precision | Recall |
|:--|--:|--:|
| The page's tags (unit fixes, reverted changes) | 93% (51 to 100) | 36% (5 to 59) |
| Any first change in the first 7 days | 86% (54 to 97) | 30% (11 to 53) |
| Either of the two | 87% (60 to 96) | 46% (19 to 66) |
| First 7 days, or a change of 10 times or more | 92% (76 to 98) | 55% (30 to 73) |
| A small model (cross-validated logistic regression) | 76% (57 to 89) | 78% (59 to 90) |

So about six in ten first price changes correct the catalogue rather than
reprice the model, and corrections are common after the first week too. The
tags miss most of them. Counting the unclear rows as repricings instead, the
share is 46%; counting them as corrections, 70%.

Since version 1.12 the page tags the fourth rule as a **likely correction**
and gives every estimate without those changes too. It does not find them
all: of the first price changes it does not tag, about 40% (24 to 61) are
still corrections, so even that estimate overstates how often a host really
changes a price.

## How it works

The full method is in [docs/SPEC.md](docs/SPEC.md): definitions, numbered
requirements, known limitations, and a traceability table linking each
requirement to the test that verifies it. In short:

1. **Subject:** a model added after the catalogue's first version. Time zero is
   the moment it was added.
2. **Exit:** the first of a price change, a retirement date being set, or
   removal. When two happen in the same version, removal counts first, then
   retirement.
3. **Censored:** no exit by the end of the history.
4. **Estimator:** Aalen-Johansen cumulative incidence for each exit, reported
   only while at least 100 models are still being followed.
5. **Uncertainty:** 1,000 bootstrap resamples of the models with a fixed seed,
   so every run gives identical output.
6. **Checked on simulated data:** on 200 simulated datasets per setting,
   with exit rates chosen in advance, the largest bias is 0.0015 and the
   95% intervals contain the true value in 91% to 98% of datasets.

## Run it

Python 3.14.7 (pinned in `.python-version`; 3.12 or newer works), standard
library only, plus pyarrow (pinned in `requirements.txt`) to read Arena's past
leaderboards for the Trends view; without it the page is built without the
trend charts. One command downloads LiteLLM's history, rebuilds everything and
writes the results page:

```bash
PYTHONPATH=src python -m llmledger.pipeline    # writes data/ and site/index.html
PYTHONPATH=src python -m llmledger.simulate    # simulation check, about 2 minutes
```

Before it writes the page, the pipeline compares its data with the live page
and stops if the new build is a step back (fewer models, a quarter fewer
listed, or older data). Set `LLMLEDGER_SKIP_LIVE_CHECK=1` to publish anyway,
for example after LiteLLM rewrites its history.

Tests (174 tests: known answer, simulation, naming, corrections, SQL, prompt cost,
Arena matching, task guess, model comparison, plug-in parity, trends, licences,
the check against the live page, the Agent Skill, models not yet priced, the
promptfoo answer keys, page and version checks; the prompt cost, task guess,
comparison, trends drawing and parity tests need Node.js and are skipped without
it; the plug-in has 28 more in `mcp/tests`),
with the exact versions pinned in `requirements.txt`:

```bash
python -m pip install -r requirements.txt
python -m pytest
```

## Use it inside Claude

The plug-in `llmledger-mcp` (in [`mcp/`](mcp/)) gives Claude and other AI apps nine tools:
suggest a model and effort for a project, compare models, estimate a budget, find models,
a model's price history with its outlook, new models not priced yet, how long a job
takes (learned from runs you log), and a quote for a whole job from a promptfoo sample. It runs on your computer and reads the daily
`data.json`; no keys, nothing to host.

```bash
claude mcp add llmledger -- uvx llmledger-mcp
```

Other apps and details: [mcp/README.md](mcp/README.md).

Or as an Agent Skill, which gives the same answers and stays out of the
context until it is needed. In Claude Code:

```text
/plugin marketplace add pouriaetab/llmledger
/plugin install llmledger@llmledger
```

For other agents that read Agent Skills, copy the folder
[`skills/llmledger`](skills/llmledger) into the agent's skills folder (for
Claude Code without the commands above: `~/.claude/skills/`), or run
`npx skills add pouriaetab/llmledger`. It needs Python 3.10 or newer and
nothing else; the data is downloaded once a day.

## Cite

Use the "Cite this repository" button on GitHub, which reads
[CITATION.cff](CITATION.cff). Archived on Zenodo:
[10.5281/zenodo.23330454](https://doi.org/10.5281/zenodo.23330454) always
points to the newest version; version 1.0.0 is
[10.5281/zenodo.23330455](https://doi.org/10.5281/zenodo.23330455).

## Data source

The data is the git history of
[`model_prices_and_context_window.json`](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json)
in [BerriAI/litellm](https://github.com/BerriAI/litellm), used under its MIT
licence. The history is cloned to your own machine and is not redistributed
here. llmledger is independent and not affiliated with or endorsed by BerriAI.

Quality ratings on the Best value tab come from the
[Arena leaderboard dataset](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset)
by LMArena, used under CC BY 4.0 and read once a day; the Trends view reads
its full history of past leaderboards from the same dataset. The task guess is
measured on prompts from Arena's
[human preference dataset](https://huggingface.co/datasets/lmarena-ai/arena-human-preference-140k),
also CC BY 4.0. llmledger is not affiliated with or endorsed by LMArena.

## Layout

```
src/llmledger/       history.py, events.py, flags.py (corrections),
                     survival.py, survival.sql and sql.py (SQL check),
                     simulate.py,
                     outlook.py (one model's outlook), names.py (grouping),
                     catalog.py (page data), page.py, page.html, app.js,
                     cost.js (prompt cost), arena.py (quality ratings),
                     licences.py (daily licence check), route.js and
                     route_eval.py (task guess and how often it is right),
                     pick.js (compare side by side), export.py (data.json),
                     trends.py and trends.js (the Trends view, cost vs quality),
                     corrections.py (how many price changes are corrections),
                     unpriced.py (models seen on Arena, not yet priced),
                     guard.py (no step back from the live page),
                     table_protocol.js (results page), pipeline.py
tests/               known answer, simulation, naming, page and version tests
mcp/                 the plug-in (llmledger-mcp): FastMCP server, tests, server.json
skills/llmledger/    the Agent Skill: SKILL.md and a script with a copy of the
                     plug-in's code (tools.py, logic.py, data.py, speed.py, forecast.py)
.claude-plugin/      the Claude Code marketplace entry for the skill
docs/SPEC.md         definitions, requirements, limitations, traceability
docs/corrections/    labelling guide and the labelled sample (issue #7)
docs/promptfoo.md    checking the plug-in with promptfoo, timing jobs from its runs,
                     and quoting a whole job from a sample
.github/workflows/   tests on every pull request; refresh rebuilds and
                     publishes the results page every day, and opens an
                     issue when it fails
```

Built with an AI pair programmer (Claude); the specification, the statistical
design and the conclusions were reviewed by the author.

MIT licence.
