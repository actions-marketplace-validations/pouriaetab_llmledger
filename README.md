# llmledger

[![tests](https://github.com/pouriaetab/llmledger/actions/workflows/tests.yml/badge.svg)](https://github.com/pouriaetab/llmledger/actions/workflows/tests.yml)
[![refresh](https://github.com/pouriaetab/llmledger/actions/workflows/refresh.yml/badge.svg)](https://github.com/pouriaetab/llmledger/actions/workflows/refresh.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.12 | 3.14](https://img.shields.io/badge/python-3.12%20%7C%203.14-blue.svg)
[![Data: LiteLLM](https://img.shields.io/badge/data-LiteLLM-informational.svg)](https://github.com/BerriAI/litellm)

What happens to an LLM after it is added to a price catalogue? llmledger rebuilds
the full change history of LiteLLM's model price file and estimates how likely a
newly added model is to have its price changed, get a retirement date, or be
removed, within 30 days to 2 years.

**Live results, rebuilt every day:** https://pouriaetab.github.io/llmledger/

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

## First results

A snapshot; the live page above has the current numbers.

5,100 models added after the catalogue's first recorded version
(6 September 2023), followed until 29 September 2026. Each cell is the estimated
share of models whose first exit was this one, with its 95% confidence interval.

| Within | Price change | Retirement announced | Removed | None of these |
|:--|--:|--:|--:|--:|
| 1 year | 15.3% (14.1 to 16.6) | 15.9% (14.5 to 17.3) | 9.4% (8.5 to 10.4) | 59.4% (57.5 to 61.1) |
| 2 years | 19.1% (17.6 to 20.7) | 29.3% (27.2 to 31.4) | 16.7% (15.0 to 18.4) | 34.9% (32.6 to 37.3) |

Each row adds up to 100% because the three exits compete: once a model is
removed, its price can no longer change. Analysing each exit on its own would
overstate all three.

Counting only input and output token prices, the one year price change estimate
is 13.4%. Ignoring price changes in a model's first week, it is 12.5%. Some early
changes correct a wrong first entry rather than reprice the model.

Corrections and clean ups matter more for removals. On the data of 13 October
2026, a few days after a clean up removed about 500 OpenRouter rows, the one
year removal estimate is 16.3% (15.3 to 17.4) counting every change and 5.7%
(5.0 to 6.5) leaving out bulk clean ups, unit fixes and reverted changes.

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

Tests (58 tests: known answer, simulation, naming, corrections, SQL, page and
version checks),
with the exact versions pinned in `requirements.txt`:

```bash
python -m pip install -r requirements.txt
python -m pytest
```

## Data source

The data is the git history of
[`model_prices_and_context_window.json`](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json)
in [BerriAI/litellm](https://github.com/BerriAI/litellm), used under its MIT
licence. The history is cloned to your own machine and is not redistributed
here. llmledger is independent and not affiliated with or endorsed by BerriAI.

## Layout

```
src/llmledger/       history.py, events.py, flags.py (corrections),
                     survival.py, survival.sql and sql.py (SQL check),
                     simulate.py,
                     outlook.py (one model's outlook), names.py (grouping),
                     catalog.py (page data), page.py, page.html, app.js,
                     table_protocol.js (results page), pipeline.py
tests/               known answer, simulation, naming, page and version tests
docs/SPEC.md         definitions, requirements, limitations, traceability
.github/workflows/   tests on every pull request; refresh rebuilds and
                     publishes the results page every day
```

Built with an AI pair programmer (Claude); the specification, the statistical
design and the conclusions were reviewed by the author.

MIT licence.
