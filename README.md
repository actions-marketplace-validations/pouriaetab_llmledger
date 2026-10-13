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

**Status:** version 1.3. The data and the page refresh every day.

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
   same day), unit fixes (a price made 100 times larger or smaller) and changes
   undone within 30 days, and shows the results with and without them.
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
is 12.5%. Ignoring price changes in a model's first week, it is 12.0%. Some early
changes correct a wrong first entry rather than reprice the model.

Corrections and clean ups matter more for removals. The one year removal
estimate above includes a clean up that removed about 500 OpenRouter rows on
9 October 2026. Leaving out bulk clean ups, unit fixes and reverted changes, it
is 5.7% (5.0 to 6.5).

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
library only. One command downloads LiteLLM's history, rebuilds everything and
writes the results page:

```bash
PYTHONPATH=src python -m llmledger.pipeline    # writes data/ and site/index.html
PYTHONPATH=src python -m llmledger.simulate    # simulation check, about 2 minutes
```

Tests (97 tests: known answer, simulation, naming, corrections, SQL, prompt cost,
Arena matching, task guess, licences, page and version checks; the prompt cost
and task guess tests need Node.js and are skipped without it),
with the exact versions pinned in `requirements.txt`:

```bash
python -m pip install -r requirements.txt
python -m pytest
```

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
by LMArena, used under CC BY 4.0 and read once a day. The task guess is
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
                     table_protocol.js (results page), pipeline.py
tests/               known answer, simulation, naming, page and version tests
docs/SPEC.md         definitions, requirements, limitations, traceability
.github/workflows/   tests on every pull request; refresh rebuilds and
                     publishes the results page every day
```

Built with an AI pair programmer (Claude); the specification, the statistical
design and the conclusions were reviewed by the author.

MIT licence.
