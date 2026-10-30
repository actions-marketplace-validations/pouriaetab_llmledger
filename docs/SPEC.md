# Survival analysis specification

Status: draft · Issue: #3

## 1. Purpose

Estimate, for a model newly added to LiteLLM's model
catalogue, the probability of each of three exits within a
given number of days: a price change, a retirement
announcement, or removal from the catalogue.

## 2. Input

`data/events.csv`, produced by `llmledger.events`, one row
per change, with columns `when, sha, model, kind, field,
old, new`.

## 3. Definitions

- **D1 Subject:** one model name in the catalogue.
- **D2 Time zero:** the first version of LiteLLM's main in
  which the model appears.
- **D3 Time unit:** days, fractions allowed.
- **D4 End of observation:** the time of the newest version
  in the input.
- **D5 Price change:** a field whose name contains `cost` or
  `pricing` changes from one number to a different number.
- **D6 Retirement announced:** `deprecation_date` changes
  from no value to a date.
- **D7 Removed:** the model disappears from the catalogue.
- **D8 Exit:** the first of D5, D6 or D7 after time zero.
- **D9 Censored:** no exit before the end of observation.
- **D10 Bulk clean up:** a removal on a day (UTC) when 50 or more
  models were removed from the catalogue.
- **D11 Unit fix:** a price change in which the new number is at
  least 100 times larger or smaller than the old one.
- **D12 Reverted:** two price changes to the same field of the same
  model, the second putting back the number the first replaced,
  within 30 days. Both changes are reverted.
- **D13 Effort levels:** the thinking effort levels a model takes, from
  lowest to highest: none, minimal, low, medium, high, xhigh, max. Taken
  from LiteLLM's `reasoning_effort_levels` when it lists them; otherwise
  low, medium and high for a model with `supports_reasoning`, plus each
  level LiteLLM marks with `supports_<level>_reasoning_effort`. The
  default is `default_reasoning_effort` when listed.
- **D14 Likely correction:** a price change (D5) that is not a unit fix
  or reverted (D11, D12) and that comes within 7 days after time zero, or
  is from 0, or whose new number is at least 10 times larger or smaller
  than the old one. For a model in the first version, whose time zero is
  unknown, only the last two parts apply. This is the rule measured in
  REQ-S37 (first week or tenfold).

## 4. Requirements

**REQ-S1 Inclusion.** The analysis shall include only models
that are not present in the first version of the input.
Verified by: a test in which a model present in the first
version is not among the subjects.

**REQ-S2 First appearance only.** The analysis shall follow
each model from its time zero to its first exit and ignore
any later re-additions.
Verified by: a test in which a model is removed and re-added;
it yields one subject, ending at the removal.

**REQ-S3 Ties.** When two exits occur in the same version,
the analysis shall record one exit, choosing removed over
retirement announced over price change.
Verified by: a test with a simultaneous removal and price
change; the recorded exit is removed.

**REQ-S4 Estimator.** The analysis shall estimate the
cumulative incidence of each exit with the Aalen-Johansen
estimator, and the probability of no exit with the
Kaplan-Meier estimator.
Verified by: REQ-S11.

**REQ-S5 Totals.** At every reported time point, the three
cumulative incidences plus the probability of no exit shall
sum to 1, within 0.000000001.
Verified by: an automated check on every output.

**REQ-S6 Time points.** By default, the analysis shall report
estimates at 30, 90, 180, 365 and 730 days after time zero.
Verified by: inspection of the output.

**REQ-S7 Minimum at risk.** The analysis shall not report an
estimate at a time point where fewer subjects remain at risk
than a set minimum, 100 by default.
Verified by: a test with fewer than 100 subjects, in which
no estimate is reported.

**REQ-S8 Confidence intervals.** For every estimate, the
analysis shall report a 95% confidence interval from 1,000
bootstrap resamples of the subjects, using the 2.5th and
97.5th percentiles.
Verified by: inspection that every interval has a lower
bound no greater than its upper bound.

**REQ-S9 Reproducibility.** Given the same input and the
random seed 20261001, the analysis shall produce identical
output.
Verified by: a test that runs the analysis twice and
compares the two outputs.

**REQ-S10 Sensitivity analyses.** Alongside the main result,
the analysis shall report the same estimates under two
alternative definitions: (a) a price change limited to
`input_cost_per_token` and `output_cost_per_token`;
(b) price changes in the first 7 days after time zero
ignored.
Verified by: inspection that the output has three labelled
sets of estimates.

**REQ-S11 Known answer.** On the six-subject example in
section 6, with the time point 60 days and a minimum at risk
of 1, the analysis shall report: price change 7/18, removed
1/6, retirement announced 2/9, no exit 2/9.
Verified by: an automated test.

**REQ-S12 Output.** The analysis shall write
`data/survival.csv` with the columns `definition, days,
outcome, estimate, ci_low, ci_high, at_risk`, one row per
definition, time point and outcome.
Verified by: a test that reads the file and checks its
columns.

**REQ-S13 Known truth.** On data simulated with constant exit rates,
where the true cumulative incidence is (rate of the exit / total rate)
× (1 − e^(−total rate × days)), the estimate at 365 days from 50,000
simulated models shall be within 0.01 of the truth for every outcome,
for both rate sets in `src/llmledger/simulate.py`.
Verified by: an automated test.

**REQ-S14 Interval coverage.** Over 200 simulated datasets of 2,000
models each, the 95% bootstrap intervals (200 resamples) shall contain
the true value in at least 90% and at most 99% of datasets, for every
outcome at 90, 180 and 365 days.
Verified by: analysis of `data/simulation.csv`.

**REQ-S15 Daily refresh.** The published results page shall be rebuilt
from LiteLLM's latest `main` at least once a day, and shall state the
LiteLLM commit and the time of the data it was built from.
Verified by: an automated test that the page names its data, and
demonstration (the scheduled `refresh` workflow).

**REQ-S16 Pinned environment.** Runs whose numbers are compared or
published shall use the Python version in `.python-version` and the
exact package versions in `requirements.txt`, and every pipeline run
shall print the Python version it used and whether it matches the pin.
Verified by: an automated test that both files pin exact versions, and
inspection of the run log.

**REQ-S17 Outlook for one model.** For a listed model with no exit
yet, the page shall report the chance of each exit in the next 90 and
365 days, conditional on the model's age, as (F(age + h) − F(age)) /
S(age) for each exit and S(age + h) / S(age) for none, from the
Aalen-Johansen curves of its host's models (or of all models when the
host has fewer than 200), with 95% bootstrap intervals, and only where
at least 100 models are still followed at age + h.
Verified by: an automated test on the six-subject example: from day
20, over the next 40 days, price change 1/3, retirement 1/3,
removed 0, none 1/3.

**REQ-S18 Names.** The page shall show every model under LiteLLM's own
name, and shall also offer a grouped view in which naming rules map
the same model on different hosts to one name (for example,
`snowflake/claude-3-5-sonnet` and
`eu.anthropic.claude-3-5-sonnet-20241022-v2:0` both map to
anthropic / claude-3.5-sonnet). A vendor glued to the front of a name
(`databricks-claude-opus-4`, `Meta-Llama-3-70B`, `openai-gpt-4o`, `ft:gpt-4o`)
is not the model and shall be dropped when what is left names a maker, and a
vendor segment of the key shall name the maker when the name does not
(`bedrock/us-east-1/deepseek.v3.2` is deepseek); a name that carries its
maker's own name keeps it (`deepseek-v4-flash`). Before a search, the view
shall show the newest listings rather than nothing.
Verified by: automated tests on named examples.

**REQ-S19 Last 7 days.** The page shall list every addition, removal,
price change and retirement date change in the 7 days before the
latest data.
Verified by: an automated test.

**REQ-S20 Corrections.** Every change that meets D10, D11, D12 or D14
shall be tagged as a bulk clean up, a unit fix, reverted or a likely
correction, in that order when more than one applies to a price change.
The page shall show the tag next to the change with what it means,
shall offer to hide tagged changes in the last 7 days, and shall leave
tagged changes out of each model's count of price changes. A model's
outlook shall say how many first price changes were corrections in the
labelled sample of REQ-S37.
Verified by: automated tests at and just below each threshold.

**REQ-S21 Leaving out corrections.** Alongside the main result, the
analysis shall report the same estimates with unit fixes and reverted
changes ignored (definition `real_only`), and with likely corrections
ignored as well (`likely_real`), each with a model removed in a bulk
clean up censored on that day rather than removed. The page shall show
all three at 1 year, side by side, shall give the one year chance of a
price change without likely corrections under the headline numbers, and
shall say that both still count some corrections (REQ-S37). No estimate
shall be called "real changes only".
Verified by: automated tests on a small example and on the page.

**REQ-S22 SQL cross-check.** Every run shall build the table of
subjects (one row per model: days followed and how it ended) a second
time, in SQL, under every definition in REQ-S10 and REQ-S21, and shall
stop before publishing if the SQL and Python tables differ for any
model.
Verified by: automated tests in which each model checks one rule, and
the check line in every daily run log.

**REQ-S23 Prompt cost.** The page shall estimate the cost of one prompt
on every listed chat model that has input and output token prices, as
(prompt tokens x input price + answer tokens x output price) / 1,000,000,
with prompt tokens estimated at 4 characters per token unless the user
enters a number. It shall sort models from cheapest, offer the cheapest
listing per grouped model, and show each listing's chance of a price
change within 90 days. The prompt text shall not leave the page or be
stored.
Verified by: automated known answer tests of `cost.js`, and the page in
a browser.

**REQ-S24 Media and choices.** For a text answer, the page shall add the
cost of attached images, PDF pages, audio and video, using the model's own
per-image or per-second price when LiteLLM lists one and otherwise about
1,000 tokens per image, 1,500 per PDF page, 32 per second of audio and 300
per second of video, and shall show only models that can take that input
in. It shall also price making images (per image), video (per second) and
speech (per character or per second). Answer length shall be offered as
Short (250 tokens), Medium (800), Long (2,000), Very long (6,000) or a
number. Models shall be filterable by skill, prompt size, maker, model,
version and host, each with an All option.
Verified by: automated known answer tests of `cost.js`, and the page in
a browser.

**REQ-S25 Best value.** The page shall show, for each task in Arena's
leaderboard that it offers, the Arena rating and 95% range of every model
it can match to the catalogue, the cost of the user's prompt on the
cheapest listing of that model, and mark as best value the cheapest model
whose range overlaps the top model's. If Arena cannot be reached, the page
shall be built without ratings.
Verified by: automated tests of name matching, of the best value rule,
and of a failed download.

**REQ-S26 Licences.** Every run shall read the current licence of each
outside source (LiteLLM's licence file, the Arena dataset card, EIA's
reuse page, and the packages pinned in `requirements.txt` and
`mcp/pyproject.toml` on PyPI) and accept only licences open for business use
(MIT, Apache-2.0, BSD, ISC, CC BY 4.0, CC0, public domain). If LiteLLM's is
not, the run shall stop before publishing. If Arena's is not, or cannot be
read, the page shall be built without ratings or trends. If pyarrow's is
not, the page shall be built without the trend charts. If EIA's data is no
longer in the public domain, the electricity prices shall be left out. Every problem shall be written to
`data/licence-problems.txt`, from which the daily refresh opens a GitHub
issue, and the licences found shall be shown on the page.
Verified by: automated tests with each source open, closed and
unreachable.

**REQ-S27 Task guess.** The page shall guess which Arena task a prompt
belongs to from its words and attachments, in the browser, and show the
words the guess was based on. When the Best value task is set to
Automatic, it shall use the guess. The page shall show how often the guess
is right on a sample of labelled Arena prompts kept apart from the ones
used to write the rules, with 95% intervals, next to always guessing
Everything (overall).
Verified by: automated tests of the guess on named examples and of the
scoring, and the measurement in `src/llmledger/route_eval.json`.

**REQ-S28 Simple first view.** The page shall open on one prompt box
with answer length choices, and show at most three answers for it: best
value, top rated and cheapest rated, each with its cost per answer and
its chance of a price change in the next 90 days. Every other control and
table shall be one click away: in the tabbed panel under the answers, or under
Trends, Models, Price history or About. Each script shall be loaded by an address that changes when the
file changes, so a browser never mixes an old script with a new page.
Verified by: an automated test of the page's views and script addresses,
and the page in a browser at desktop and phone widths.

**REQ-S29 Compare side by side.** Under the answers, the page shall show
models side by side as columns that follow the prompt: the three answers,
or on a Claude or ChatGPT plan that maker's three highest rated models for
the task on its own host, plus up to 3 models the reader adds. Each column
shall show the model's Arena rating for the task with its rank, its effort
levels (D13) and a suggested level for the prompt, its price per 1M tokens,
its answer tokens per task (the chosen answer length, or the number the
reader types) and its cost per task, or on a plan how fast it uses the plan
compared with the one that uses it least. One sentence shall name the pick
(the cheapest whose rating the votes cannot tell apart from the highest
rated) and each other column shall say how it compares with the pick,
including the break-even share of answer tokens. Verified by: automated
tests of the effort levels, the suggestion, plan use, the pick and the
sentences, and the page in a browser.

**REQ-S30 Plain explanations.** Each answer card shall say where its model
stands among the rated models for the task (its rank, or that it is the
cheapest of them), the line under the cards shall say how many priced and
rated models the answers were picked from, and a click on the "i" beside
any Arena score shall open a short explanation of Arena. Quality ratings
shall be shown as a chart of each score and its 95% range, with the range
the votes cannot tell apart from the top shaded, and as a table on request.
Verified by: an automated test of the page and the page in a browser.

**REQ-S31 Machine-readable data.** Every run shall also publish
`data.json`: every listed model with its prices per 1M tokens, prompt
size, skills, effort levels and outlook, every change to those models, the
Arena ratings by task, the sources and their licences. Verified by:
`test_req_s31_data_json_lists_listed_models_with_prices_and_outlook`.

**REQ-S32 Plug-in.** The folder `mcp/` shall hold an MCP server
(llmledger-mcp) with eight tools (find_models, compare_models,
estimate_cost, price_history, suggest_for_project, not_yet_priced,
estimate_time, all read-only, and log_run, which only adds to a file on the
user's computer), a snapshot resource
and a prompt, reading `data.json` once a day with a bundled copy for the
first run. Its task guess and comparison shall give the same answers as
the page's route.js and pick.js. A model shall be priced at its cheapest
listing for the tokens asked about; when the tokens do not decide, at the
lower list price, then the maker's own host, then the name, never by the
order of the listings. Verified by: the parity tests in the repository and
the plug-in's own tests through FastMCP's in-memory client.

**REQ-S33 Trends.** A Trends view shall replay Arena's past overall
leaderboards (the dataset's full history, CC BY 4.0) as a moving line
chart, in three views: Open vs closed (the best closed and the best open
rating at each leaderboard, the gap between them shaded and said in
plain words as the share of people who would pick the leader, and today's
top 3 of each as thin lines), Top 5 makers (each maker's best rating), and
Price race (the price of the top rated model that can be priced, the
cheapest of the top 10, and the cheapest model rated at least as high as
the model that was first a year earlier). A price is per 1M tokens,
counting 3 read for every 1 written, at the model's cheapest host on that
day, rebuilt by rolling today's price back through every later change
(unit fixes and likely corrections are not rolled back; free listings are
not prices). Arena
models renamed between leaderboards shall keep one line. The replay shall
play once when the view opens, not move for readers who ask for reduced
motion, and offer play, pause and a slider; hovering shall show every
line's value at the nearest leaderboard, and a table shall give the
numbers. If the history cannot be read, the page shall keep the trends
from the live page, or be built without them. Verified by: automated tests
of the series, the price roll back, the renamed models, the fallback and
the drawing helpers, and the page in a browser.

**REQ-S34 Cost vs quality.** Under Compare side by side, the page shall
draw every model Arena rated for the task within 200 points of the top,
at its cheapest listing's cost for the prompt (log scale) against its
score, and mark the edge: the models no other model beats on both price
and score, listed best first with the three answers named. It shall
follow the prompt like the answers. Verified by: an automated test of the
edge and the page in a browser.

**REQ-S35 What is new.** The Trends view shall list the newest text models
in the catalogue (grouped models whose first listing is newest and that
have a token price) with their best Arena rank across tasks, and the
latest catalogue changes, newest first: one line per listing and day, with
a clean up, or four or more listings added, removed or priced for the
first time on one day, folded into one line, and a link to every change in
the last 7 days. Verified by: automated tests of both lists.

**REQ-S36 One page when it fits, otherwise natural scrolling.** A view
shall fit one screen when its content fits at a normal size; when it does
not, the page shall scroll the normal way, with the bar at the top and the
footer at the end, and the first screen shall show that more follows. No
content shall be cut, put in a box that scrolls inside, shortened with an
ellipsis or a line limit, or shrunk to fit. Allowed exceptions: the model
drawer, wide tables that scroll sideways on narrow screens, the prompt box
past 40% of the window, and the long checklists under Options (makers,
models, versions, hosts), which scroll like a dropdown. The page shall
never scroll sideways. On Ask, the three answers shall come first and the
extras (Compare, Cost vs quality, Quality ratings, Every model, Options,
How it works) shall be tabs in one panel under them, the open tab shown in
place at its full height. A model's details shall open in a drawer over
any view. About shall show each of its parts as a row that opens on a
click, including a part that a copy of the page adds (such as a scope
note), and a link to that part shall open it. Verified by: automated tests
of the page's layout rules, and the page and the site copy in a browser
at ten window sizes from 375 x 560 to 1920 x 1080 (his laptop's 1269 x 746
among them), light and dark: no sideways scroll and nothing cut in any
view or panel.

**REQ-S37 Corrections measured.** A stratified random sample of first price
changes (D5) of models added after time zero, 100 from a model's first 7 days
and 100 from later (seed 7), shall be labelled correction, repricing or
unclear from the evidence for each row, following
`docs/corrections/labelling-guide.md`, and kept with the reason for each
label in `docs/corrections/sample.csv`. The share of corrections, and the
precision and recall of the page's tags (D11, D12), of a first-week rule, of
both, of a first-week-or-tenfold rule and of a cross-validated logistic
model, shall be reported weighted to the population, with 95% intervals from
a bootstrap of whole LiteLLM commits within strata, in
`src/llmledger/corrections_eval.json` and the README, also with the unclear
rows counted as repricings and as corrections. For each rule, the share of
corrections among the first price changes it does not call one shall be
reported too, with its interval. The first-week-or-tenfold rule shall be the
same function as the tag D14. Verified by: automated tests of the population,
the sample, the rules, the scores and the model, a test that the report is
rebuilt exactly from the labelled sample, and a test that the page quotes
the numbers measured.

**REQ-S38 No step back.** Before publishing, every run shall compare its
data with the page that is live now and stop, publishing nothing, if it
knows fewer than 99% of the live page's models, lists fewer than 75% of
its listed models (the largest one-day clean up so far removed 10%), or
its data ends before the live page's. If the live page cannot be read,
the run shall go on and say so. Setting `LLMLEDGER_SKIP_LIVE_CHECK=1`
shall publish anyway. Verified by: automated tests at and around each
threshold, and that the check comes before the page is written.

**REQ-S39 Old data named.** When the page's data was built 3 or more days
ago, the page shall say so at the top of every view, with the build date.
The plug-in shall add the same warning to every answer. Verified by:
automated tests of the page and of the plug-in.

**REQ-S40 Failed refresh reported.** When the daily refresh does not
publish, the workflow shall open one issue about it (not one a day), and
shall close it when a later refresh is published. Verified by: an
automated test of the workflow file, and demonstration.

**REQ-S41 Agent Skill.** The folder `skills/llmledger` shall hold an Agent
Skill (agentskills.io format: `SKILL.md` with a name matching the folder, a
description of what it does and when to use it, under 500 lines) and a
script that gives the plug-in's answers as JSON with the standard
library only, from an exact copy of the plug-in's `tools.py`, `logic.py`,
`data.py` and `speed.py`, so both give the same answers from the same data. The
repository shall be a Claude Code marketplace whose one plugin is that
skill. With no data saved and none to download, the script shall say so
instead of failing. Verified by: automated tests that the copy is exact,
that `SKILL.md` and the marketplace files follow their formats, of the
script's answers on the plug-in's test data and of its errors; Claude
Code's own `plugin validate` and an install in a fresh profile.

**REQ-S42 Seen, not yet priced.** From Arena's latest overall leaderboard
and its full history, the analysis shall list the models Arena first showed
in the last 180 days that the catalogue does not list, with the day Arena
first showed them, their votes, and for a name the naming rules cannot
match, up to 3 catalogue names it may be priced under. It shall estimate,
with Kaplan-Meier and 95% bootstrap intervals (1,000 resamples), the chance
that a model is priced on or before the day Arena first shows it and within
7, 30 and 90 days, counting a model not priced yet as followed until the
day of the run, leaving out models on Arena's first leaderboard (their
first day is unknown) and unmatched names with a close catalogue name, and
reporting only while at least 20 models are followed; and, for makers with
at least 5 models, the share priced before Arena showed them and the median
wait of the rest. The page shall show both under Price history, and the
plug-in and the skill shall answer them. Verified by: automated tests on
small examples, the fallback to the live page, and the page.

**REQ-S43 Where each change came from.** Each change shall keep the LiteLLM
commit that made it (its first 12 characters, written once in a list the
changes point to), the page shall link it from a model's timeline, and the
plug-in shall give it with each change and, for a day asked about, each
listing's prices at the end of that day as the catalogue had them, with
the change that set each one. Verified by: automated tests of the list,
of a price on a day before, on and after a change, and of the page.

**REQ-S44 Cache costs and offline answers.** Records shall carry the cache
write price as well as the cache read price; an estimate with cached or
cache write tokens shall price them at those prices (at the input price,
saying so, when one is not listed) and give the cost without the cache and
the saving. Every plug-in answer shall give the day its prices are from,
and say so when it comes from the bundled copy or an old download because
today's data could not be downloaded. Verified by: automated tests.

**REQ-S45 Time learned from the user's runs.** The plug-in and the skill
shall keep timed runs (model, way of calling it, thinking on or off, prompt
and answer tokens, seconds) in a file on the user's computer, from a single
run or a promptfoo results file (each result once; cached results, calls
that did not run and tokenless results skipped, a failed check kept; the way
read from each provider and thinking from its thinking tokens unless given),
and shall estimate the time of one call and of
a whole job (calls over the number running at once) as a usual time and a
slow day, from the newest 50 runs of that model and way only: a Theil-Sen
fit of seconds on answer tokens, times the median and the 90th percentile
of the ratios of real to fitted time; with fewer than 5 runs, the slow day
at least twice the usual time and the answer marked rough. With no runs it
shall say so and name the ways that have runs. No speed table without an
open licence shall be used. Verified by: automated tests of the fit on
exact and noisy runs, of the tools, of a promptfoo file read twice and of
the skill.

**REQ-S46 promptfoo checks.** `mcp/promptfoo` shall call the plug-in's
tools through promptfoo's MCP provider, with answer keys worked out from
`data.json` alone: `estimate_cost` at a model's cheapest listing,
`compare_models` at the same cost, `price_history` with every listing.
Verified by: automated tests of the answer keys, a run on the day's data
(30 of 30 pass with plug-in 0.1.5; 28 of 30 with 0.1.2, which had the
listing slip).

**REQ-S47 A whole job quoted from a sample.** The plug-in and the skill
shall read a promptfoo results file of a sample of a job and, given the
number of tests in the whole job, give for each model (and prompt, when a
model tried more than one): the job's calls (tests times calls a test in the
sample); its time as a usual time and a slow day, per REQ-S45, from the
sample's timed calls and the user's logged runs of the same model and way
(the sample's calls once), at the sample's calls at once unless given; its
cost from the sample's average tokens (cache reads and writes included) at
the cheapest listing, and at the cheapest listing on the host the sample
used with the sample's own cost at those prices; promptfoo's figure for the
sample and the job at that rate, saying why they may differ when they do by
more than a tenth; the 90-day chance of a price change of the cheapest
listing; how often it was right (passed checks over checked results, calls
that did not run counted apart) with a Wilson 95% range; and a line against
the pick with the break-even cost of a wrong answer (the cost difference an
item over the difference in the share right). The pick shall be the cheapest
model whose range overlaps the most often right, or with a cost of a wrong
answer, the lowest cost an item counting wrong answers at it; with no checks,
the cheapest. Nothing shall be called or sent. Verified by: automated tests
of the Wilson ranges, the provider names, a sample with a cached answer, a
failed call and a local model, the cost of a wrong answer, logged runs,
prompts, repeats, another host and Claude Code, a sample without checks, bad
input, and the skill.

**REQ-S48 Local or cloud.** The daily build shall read the average
residential electricity price for the latest month in EIA's Electric Power
Monthly, Table 5.6.A, for the country and each state (no table, a changed
table or fewer than 40 states gives none), while EIA's reuse page says its
data is in the public domain; when EIA cannot be read, it shall keep the live
page's prices, and data.json shall carry them with their month and EIA's
credit line. The plug-in and the skill shall compare, for a number of calls a
month, each of 1 to 5 cloud models at its cheapest listing with running an
open model on a computer the user would buy: the local model's time from the
user's own timed runs (REQ-S45), its hours of work a month (one call at a
time) and whether they fit in a month on a slow day, its electricity from the
watts the user gives and the user's price, the state's or the country's,
the months until the computer's price is paid back by the monthly saving
(none when home power costs more), and the saving over a number of months.
With no runs or no watts it shall say what is missing and give the months
before electricity. No computer prices and no speed table shall be used.
Verified by: automated tests of the table, a changed table, the live
page's prices, the licence check, data.json, the tool before and after runs,
a state, a computer that cannot keep up, power that costs more, bad input
and the skill.

**REQ-S49 Feed and share data.** Each build shall publish an Atom feed
(`feed.xml`) with one entry a day for the last 14 days: how many models were
added, repriced, given a retirement date or removed that day, then one line
per model and kind with the LiteLLM commits behind the changes (at most 60
lines a kind), newest day first, well formed with no events. A price line
shall show a token price per 1M tokens, any other price as it is (per query,
per image, per second) and a table of prices as LiteLLM writes it, so a
build never stops on a price that is not one number. The page shall
carry share data (Open Graph and Twitter card tags, a canonical address and
a link to the feed) and a share image, and a short way to get the same
answers inside an MCP app, both inside markers so that a copy of the page on
another site can drop them.
Verified by: automated tests of the feed's entries, window, flags, price
texts and the empty case, and of the page's markers.

**REQ-S50 Price index and the weekly digest.** data.json shall carry
`index`: from the latest leaderboard that has both, what a model as good as
last year's #1 costs now against what that model cost then (the price race
of REQ-S33: per 1M tokens, 3 read for 1 written, cheapest host that day),
with the two models, the two prices and the ratio; the Trends view shall
show it as one line. Each build shall also write `digest.md`: the last 7 days
in plain words, with how many models were added, repriced, got a retirement
date or were removed (every change, corrections included), the five largest
token price cuts and rises with corrections left out and one line per
model, the retirement dates set, the newest models Arena already ranks (one
per grouped name) and the index line, and it shall read with no events.
Verified by: automated tests of the index and of the digest's counts, moves,
arrivals and the quiet week.

**REQ-S51 Watch.** The repository shall offer a GitHub Action (`action.yml`,
`action/watch.py`, standard library) that reads the day's data.json and, for
each model named by its LiteLLM key (a provider prefix LiteLLM does not use
is dropped; one key that ends with what was asked is taken; two or more are
not guessed), reports whether it is still listed, its token price changes
within a number of days (the four token prices by default, every price field
on request), its retirement date and its 90-day chance of a price change;
exits 1 when a watched change is found, 0 otherwise and 2 when the data
cannot be read; and writes the report to the step's outputs and summary.
Verified by: automated tests of the check, the key resolution, the report,
the exit codes and the Action's inputs.

**REQ-S52 Badges.** Each build shall write, for every listed model, a badge in
shields.io's endpoint format at `badge/<slug>.json` (the key with `/` as `--`
and `:` as `-`): the input and output prices per 1M tokens and either the
retirement date (orange) or the 90-day chance of a price change (amber from
10%, blue below).
Verified by: automated tests of the badge's text and colours and of the slug.

**REQ-S53 By maker.** Each build shall split the main result's subjects by
the maker the naming rules give each model (REQ-S18) and, for every maker
with at least 100 subjects (others pooled as "other makers"), estimate the
one-year cumulative incidence of each first exit (REQ-S7) with a 95%
bootstrap interval (REQ-S8), reported while at least 20 of the maker's
models are still followed, with the main result as the reference row; the
Price history view shall show the table and name the makers whose models
had their price changed most and least often.
Verified by: automated tests on a catalogue of two makers with known exits,
small makers pooled, and a maker followed too briefly.

**REQ-S54 The guard.** Each build shall measure whether LiteLLM's cost map
guard (merged 2026-09-04, PR #39835) changed the share of price changes
that carry a correction tag (D11, D12, D14): one observation per week, the
26 weeks before the guard and every week after, in a segmented logistic
regression of the tagged share on time, a step at the guard and a change of
slope, weighted by the week's price changes, with the step reported as an
odds ratio and the plain difference of shares reported next to it, both
with 95% intervals from a bootstrap that resamples whole weeks; the reading
shall be "no change the data can show" when the difference's interval
covers zero, and nothing shall be reported with fewer than two weeks on a
side.
Verified by: automated tests of the weekly series, a known drop, no change,
and too few weeks.

**REQ-S55 Your usage on other models.** The plug-in and the skill shall
read a coding agent's token export kept on the user's computer (`ccusage
daily --json`, `ccusage session --json`, `codeburn export -f json`, or a
plain list of token mixes) as units of one session (or day) and model, with
input, output, cache read and cache write tokens, reading numbers, names
and dates only; price each unit on every model rated for the kind of work,
at the cheapest listing's prices on the unit's day (REQ-S43; a day before
the listing at its first prices, said so), cache tokens at the input price
where a listing has no cache price, said so; report what the user paid (each
model used at its maker's own listing), the same work on every model with
the saving against what was paid, the models whose rating's high end reaches
the low end of the most used model's and that cost less, and for the cost
per session a 95% bootstrap range over sessions (1,000 resamples, at least 5
sessions); and for two models say "a real difference" only when the range
of their difference per session leaves out zero (paired on the same
sessions when both are priced on them; unpaired, and said to compare
different work, when each model's own sessions are used), the same for
one-shot rates from codeburn's per-model rows by Wilson ranges, else "not
enough data". Verified by: automated tests of each reader, the statistics,
the pricing by day, the shortlist, both tests and the error messages.

**REQ-S56 Tool descriptions.** Every plug-in tool's description shall
open with what the tool does (verb first), say when to use it, and name at
least one sibling tool to use instead, so that an agent choosing among the
tools can tell them apart; `find_models` shall also look one model up by
name and list every listing of it, and list up to 200 models. Verified by:
an automated test over the descriptions the server publishes, and tests of
the name lookup and the larger limit.

**REQ-S57 Prices past a prompt size.** Each record and data.json shall
carry, per listing, the standard prices LiteLLM lists for prompts above a
size (`*_above_<N>k_tokens`: input, output, cache read and cache write, per
1M tokens, as tiers from the smallest size up) and the hour long cache write
price (`cache_creation_input_token_cost_above_1hr`, also per tier), leaving
out the service tiers (priority, batches, flex, ultrafast, decisions), and
nothing for a listing that has none. Verified by: automated tests of the
parsing and of data.json.

## 5. Known limitations

- **L0** The guard's effect (REQ-S54) is measured on weeks that are far
  from alike: LiteLLM's provider-sync bot began in July 2026 and changed
  hundreds of rows in some weeks after the guard. The weekly bootstrap allows
  for that, at the cost of wide intervals; the result says what the data
  can show, not that the guard has no effect.
- **L1** Times are when LiteLLM edited its catalogue, not
  when a provider changed a price. The lag is unknown.
- **L2** Many price changes correct the catalogue rather than reprice the
  model: in the labelled sample of REQ-S37, about 59% of first price changes
  (95% interval 41 to 75%), 86% in a model's first week and 51% later. The
  main estimate counts them all. D11 and D12 tag about a third of them; the
  first-week-or-tenfold rule of D14 finds 55% (30 to 73%). Of the first
  price changes that rule does not call a correction, about 40% (24 to 61%)
  are still corrections, so even the estimate leaving out likely
  corrections (REQ-S21) overstates real price changes.
- **L3** A renamed model appears as one removal and one
  addition.
- **L4** A retirement announcement counts even if the date
  is later withdrawn.
- **L5** Later re-additions of the same model are ignored
  (REQ-S2).
- **L6** Models present in the first version are excluded
  (REQ-S1).
- **L7** The simulation check assumes constant exit rates. Real rates
  may change as a model ages, so it shows that the estimator works, not
  that the real data follows constant rates.
- **L8** In the main result, a bulk clean up of the catalogue, such
  as removing every row of one provider at once, counts as a removal
  for each model it touches. REQ-S21 shows the result without them.
- **L9** The grouped names come from naming rules, not from LiteLLM, so
  some models may be grouped wrongly or not grouped at all. The page
  always shows LiteLLM's own names as well.
- **L10** The outlook for one model is the experience of similar models
  at the same age, not a forecast of that model in particular.
- **L11** The tags in D10 to D12 and D14 come from fixed rules, not from
  reading each change. A real price cut of 100 times would be tagged as
  a unit fix, a real introductory price in a model's first week as a likely
  correction, and a clean up spread over several days of fewer than 50
  removals would not be tagged. On first price changes, the labelled sample
  of REQ-S37 measures them: 93% of those D11 or D12 tag, and 92% of those the
  first-week-or-tenfold rule of D14 calls a correction, are corrections. D14
  was measured on first price changes only; later changes may differ.
- **L12** The page depends on LiteLLM keeping the same file name and on
  GitHub Actions. If a daily refresh fails, nothing is published and the
  page keeps the last good build, with its data date in the footer; after
  3 days the page says its data is old (REQ-S39), and the repository has an
  open issue about it (REQ-S40). The check against the live page (REQ-S38)
  catches a build made from a broken copy of the history only when it is
  smaller or older than the live page.
- **L13** Prompt costs are estimates. Each model counts tokens its own
  way, often 10 to 30% differently from 4 characters per token, and
  caching, batch discounts, long prompt prices and taxes are left out.
  Modes come from LiteLLM; a few embedding and image models listed as
  chat are left out by name, and others may remain. Tokens for images,
  PDF pages, audio and video vary a lot by model and by file.
- **L14** Arena ratings measure which answer people preferred, not
  whether it was correct. Arena names are matched to the catalogue by
  naming rules, so some models are left out and a few may be matched to
  the wrong listing. A rating is for the version Arena tested, often with
  high reasoning effort, which uses more answer tokens than the default.
  Overlapping 95% ranges mean the votes cannot tell two models apart, not
  that they are equal.
- **L15** The task guess uses word rules, not a trained model, so it
  misses prompts that use other words for the same thing, and most
  languages other than the seven with their own task. Arena's labels come
  from Arena's own AI classifier, not from people, and cover only coding,
  math, creative writing and language, so the fields (legal, medicine and
  so on) are guessed but not measured. A prompt can belong to several
  tasks; a guess counts as right if it is any one of them.
- **L16** Higher effort makes a thinking model write more hidden answer
  tokens, and no openly licensed source measures how many per task at
  each level yet, so every model starts at the same answer length; the
  suggested level is a rule of thumb from the task and the prompt's words
  and length, not a measurement. Plans (Claude, ChatGPT) do not publish
  per-model limits; plan use assumes a plan is used up in step with each
  model's API price on the maker's own host.
- **L17** The plug-in's copy of the task rules reads word boundaries next
  to accented letters a little more generously than the browser does, so
  a rare prompt in Spanish, French or German can get a different guess.
- **L18** Arena recomputes every rating each time it publishes, so a
  model's line moves partly because the pool of models around it changed,
  not only because people liked it more or less. The price race only sees
  models the naming rules can match to the catalogue (about 4 in 5 of the
  top 10), and a catalogue price, not what a provider charged that day.
  "Open" means Arena lists a licence other than proprietary, which includes
  some licences that do not allow business use.
- **L19** A job quoted from a sample (REQ-S47) holds only as well as the
  sample's tests stand for the whole job, and a sample of 20 tells two
  models apart only when they differ a lot. Its times assume the whole job
  meets the rate limits and load the sample met. Its costs use the tokens
  the results list; a provider that bills more (cache writes it does not
  report, or extra calls Claude Code makes) costs more, which promptfoo's own
  figure may show.
- **L20** Local or cloud (REQ-S48) counts the computer's price and its
  electricity only: not what it is worth later, its other uses, upkeep or the
  user's time. It assumes one call at a time and the speed of the runs timed
  so far, takes the watts as given, and uses a month's average price for homes,
  not the user's tariff. It does not compare the two models' answers.

- **L21** Your usage on other models (REQ-S55) prices another model at the
  user's own token counts. Another model tokenises the same text a little
  differently and may answer at another length, so the costs are the same
  work at the same size, not a forecast of that model's bill. Comparing two
  models the user actually used compares the sessions each got, which were
  not the same work; the answer says so. One-shot rates come from codeburn's
  own reading of a turn, not from checked answers.

## 6. Known-answer example

| Subject | Days | Exit                 |
|---------|------|----------------------|
| A       | 10   | price change         |
| B       | 20   | removed              |
| C       | 30   | censored             |
| D       | 40   | price change         |
| E       | 50   | retirement announced |
| F       | 60   | censored             |

## 7. Traceability

| Item | Verified by | Method |
|---|---|---|
| REQ-S1 | `test_req_s1_day_one_models_are_excluded` | test |
| REQ-S2 | `test_req_s2_only_the_first_appearance_counts` | test |
| REQ-S3 | `test_req_s3_removal_wins_a_tie` | test |
| REQ-S4 | `test_req_s11_known_answer`, `test_drill_two_exits_on_the_same_day` | test |
| REQ-S5 | `test_req_s5_totals_sum_to_one`; also checked on every run | test |
| REQ-S6 | the rows of `data/survival.csv` | inspection |
| REQ-S7 | `test_req_s7_too_few_at_risk_is_not_reported` | test |
| REQ-S8 | `test_req_s8_s9_intervals_are_ordered_and_repeatable` | test |
| REQ-S9 | `test_req_s8_s9_intervals_are_ordered_and_repeatable` | test |
| REQ-S10 | `test_req_s10_definitions_differ_as_specified` | test |
| REQ-S11 | `test_req_s11_known_answer` | test |
| REQ-S12 | the header of `data/survival.csv` | inspection, not yet automated |
| D5 | `test_d5_a_new_price_field_is_not_a_price_change` | test |
| D6 | `test_d6_only_a_first_retirement_date_is_an_exit` | test |
| REQ-S13 | `test_req_s13_estimator_recovers_known_truth` | test |
| REQ-S14 | `data/simulation.csv` from `python -m llmledger.simulate` | analysis |
| REQ-S15 | `test_req_s15_page_names_the_data_it_was_built_from`; the daily `refresh` workflow | test, demonstration |
| REQ-S16 | `test_req_s16_versions_are_pinned_exactly`; the version line in every run log | test, inspection |
| REQ-S17 | `test_req_s17_outlook_known_answer` | test |
| REQ-S18 | `test_req_s18_one_model_on_many_hosts_is_grouped`, `test_req_s18_naming_rules`, `test_req_s18_a_vendor_in_the_name_is_not_the_model` | test |
| REQ-S19 | `test_req_s19_last_seven_days_lists_every_change` | test |
| D10 | `test_req_s20_bulk_clean_up_starts_at_50_removals_in_a_day` | test |
| D11 | `test_req_s20_unit_fix_is_100_times_either_way` | test |
| D12 | `test_req_s20_a_change_undone_within_30_days_is_reverted` | test |
| D14 | `test_req_s20_likely_correction_is_the_first_week_or_ten_times`, `test_req_s37_the_likely_correction_tag_is_the_rule_measured` | test |
| REQ-S20 | `test_req_s20_corrections_are_tagged_and_not_counted`, `test_req_s20_tags_and_the_outlook_say_what_a_correction_is` | test |
| REQ-S21 | `test_req_s21_real_changes_only`, `test_req_s21_leaving_out_likely_corrections_as_well`, `test_req_s21_page_compares_every_change_with_real_changes`, `test_req_s21_page_says_when_the_estimate_without_corrections_is_missing` | test |
| REQ-S22 | `test_req_s22_sql_and_python_agree`, `test_req_s22_sql_known_answer`, `test_req_s22_a_disagreement_stops_the_check`; the "SQL check" line in every daily run | test, demonstration |
| REQ-S23 | `test_req_s23_tokens_are_estimated_at_four_characters`, `test_req_s23_cost_known_answer`, `test_req_s23_cheapest_listing_per_model`, `test_req_s23_only_text_models_are_priced`; the Prompt cost tab | test, demonstration |
| REQ-S24 | `test_req_s24_answer_lengths_are_fixed_sizes`, `test_req_s24_attachments_add_cost_and_need_the_skill`, `test_req_s24_listed_per_unit_prices_win_over_estimates`, `test_req_s24_images_video_and_speech_out`, `test_req_s24_family_and_version_from_a_grouped_name`, `test_req_s24_records_carry_skills_size_and_media_prices`; the Prompt cost tab | test, demonstration |
| REQ-S28 | `test_req_s28_page_opens_on_the_prompt_box`; the page at 1366 and 390 pixels wide | test, demonstration |
| D13, REQ-S29 | `test_req_s29_records_carry_cache_price_and_effort_levels`, `test_req_s29_effort_is_clamped_to_the_levels_a_model_takes`, `test_req_s29_effort_suggestion_known_answers`, `test_req_s29_effort_suggestion_says_why_and_respects_the_model`, `test_req_s29_plan_use_is_relative_to_the_least`, `test_req_s29_verdict_known_answer`, `test_req_s29_verdict_on_a_plan_and_without_ratings`, `test_req_s29_the_pick_is_the_cheapest_the_votes_cannot_tell_from_the_top`, `test_req_s29_headline_and_notes_say_why`, `test_req_s29_page_compares_models_side_by_side`; the page in a browser | test, demonstration |
| REQ-S30 | `test_req_s30_arena_is_explained_on_the_page`; the page in a browser | test, demonstration |
| REQ-S31 | `test_req_s31_data_json_lists_listed_models_with_prices_and_outlook`, `test_req_s31_data_json_explains_the_tags_and_carries_the_corrections_measured`, `test_req_s43_data_json_links_each_change_to_its_commit` | test |
| REQ-S32 | `test_req_s32_plugin_guesses_the_same_task_as_the_page`, `test_req_s32_plugin_compares_the_same_way_as_the_page`; `mcp/tests/test_server.py` (15 tests) | test |
| REQ-S33 | `test_req_s33_renamed_arena_models_keep_one_line`, `test_req_s33_a_price_is_rolled_back_to_the_day`, `test_req_s33_a_likely_correction_is_not_rolled_back`, `test_req_s33_lines_makers_and_the_price_race`, `test_req_s33_no_history_means_no_trends`, `test_req_s33_yesterdays_trends_are_kept_when_arena_is_down`, `test_req_s33_a_rating_gap_in_plain_odds`, `test_req_s33_a_line_is_drawn_between_its_points_and_ends_after_a_month`, `test_req_s33_labels_never_overlap_and_stay_inside`, `test_req_s33_round_ticks`, `test_req_s33_trends_view_replays_the_leaderboards`, `test_req_s33_the_trends_package_is_checked_and_a_closed_one_drops_the_trend_charts`; the page in a browser at 1366 and 390 pixels wide, light and dark | test, demonstration |
| REQ-S34 | `test_req_s34_the_edge_keeps_only_models_nobody_beats_on_both`, `test_req_s34_cost_vs_quality_sits_on_ask`; the page in a browser | test, demonstration |
| REQ-S35 | `test_req_s35_new_arrivals_are_new_groups_with_a_text_price`, `test_req_s35_latest_changes_fold_batches_and_join_price_fields` | test |
| REQ-S37 | `test_req_s37_first_price_changes_and_strata`, `test_req_s37_the_sample_is_the_same_every_time`, `test_req_s37_rules_known_answers`, `test_req_s37_weighted_scores_known_answer`, `test_req_s37_model_learns_a_clear_pattern`, `test_req_s37_labelled_sample_is_complete`, `test_req_s37_report_rebuilds_from_the_sample`, `test_req_s37_the_likely_correction_tag_is_the_rule_measured`, `test_req_s37_the_page_quotes_the_numbers_measured`; `corrections_eval.json` | test, analysis |
| REQ-S38 | `test_req_s38_a_normal_day_passes`, `test_req_s38_a_step_back_is_named`, `test_req_s38_a_broken_build_is_not_published`, `test_req_s38_no_live_page_means_nothing_to_compare`, `test_req_s38_the_pipeline_checks_before_it_writes_the_page`; the "Live check" line in every daily run | test, demonstration |
| REQ-S39 | `test_req_s39_old_data_is_named_on_the_page`; `test_old_data_says_how_old_it_is` in `mcp/tests` | test |
| REQ-S40 | `test_req_s40_a_failed_refresh_opens_one_issue_and_a_good_one_closes_it`; the `report` job of the `refresh` workflow | test, demonstration |
| REQ-S41 | `test_req_s41_the_skill_carries_an_exact_copy_of_the_plugin_code`, `test_req_s41_skill_md_follows_the_agent_skills_format`, `test_req_s41_the_repository_is_a_claude_code_marketplace_for_the_skill`, `test_req_s41_the_script_gives_the_plugins_answers`, `test_req_s41_the_script_says_what_went_wrong`; `claude plugin validate .` and an install in a fresh profile | test, demonstration |
| REQ-S42 | `test_req_s42_close_names_for_names_the_rules_cannot_match`, `test_req_s42_recent_models_without_a_price`, `test_req_s42_how_soon_a_price_comes`, `test_req_s42_estimates_on_enough_models`, `test_req_s42_no_arena_means_no_list`, `test_req_s42_price_history_has_a_not_yet_priced_panel`; `test_not_yet_priced_lists_new_models_and_the_wait` in `mcp/tests` | test |
| REQ-S43 | `test_req_s43_each_change_keeps_the_litellm_commit_and_cache_write_price`, `test_req_s43_data_json_links_each_change_to_its_commit`, `test_req_s33_a_change_with_its_source_rolls_back_the_same`; `test_a_price_on_a_date_with_the_change_that_set_it` in `mcp/tests` | test |
| REQ-S44 | `test_cache_reads_and_writes_and_the_saving`, `test_offline_answers_say_so_with_the_date` in `mcp/tests` | test |
| REQ-S45 | `test_a_straight_line_is_found_exactly`, `test_one_slow_run_barely_moves_the_usual_time`, `test_few_runs_give_a_rough_range`, `test_logging_and_estimating_through_the_tools`, `test_a_promptfoo_results_file_counts_as_runs_once`, `test_bad_input_says_what_to_fix` in `mcp/tests/test_speed.py`; `test_req_s45_the_script_times_a_job_from_logged_runs` | test |
| REQ-S46 | `test_req_s46_answer_keys_come_from_the_data`, `test_req_s46_the_keys_agree_with_the_plugin_on_its_test_data`, `test_req_s46_the_config_runs_the_repository_plugin_through_the_mcp_provider`; a promptfoo run on the day's data | test, demonstration |
| REQ-S47 | `test_req_s47_wilson_ranges`, `test_req_s47_promptfoo_names_ways_and_hosts`, `test_req_s47_a_sample_becomes_a_quote_for_the_whole_job`, `test_req_s47_the_cost_of_a_wrong_answer_can_decide_the_pick`, `test_req_s47_logged_runs_add_to_the_sample_which_counts_once`, `test_req_s47_prompts_repeats_hosts_and_plans`, `test_req_s47_no_checks_and_bad_input`, `test_req_s47_the_script_quotes_a_job_from_a_promptfoo_sample` | test |
| REQ-S48 | `test_req_s48_residential_prices_by_state_from_eia`, `test_req_s48_a_changed_table_gives_nothing_rather_than_wrong_prices`, `test_req_s48_the_live_pages_prices_are_kept_when_eia_cannot_be_read`, `test_req_s48_the_reuse_page_must_still_say_public_domain`, `test_req_s48_electricity_prices_are_used_only_while_eia_says_public_domain`, `test_req_s48_data_json_carries_the_electricity_prices_and_their_credit`, `test_req_s48_before_any_local_run_it_says_what_is_missing`, `test_req_s48_with_runs_watts_and_a_state_it_counts_electricity`, `test_req_s48_when_home_power_costs_more_buying_never_pays_off`, `test_req_s48_bad_input_says_what_to_fix`, `test_req_s48_the_script_says_when_buying_a_computer_pays_off` | test |
| REQ-S49 | `test_req_s49_one_entry_a_day_newest_first_with_counts_and_commit_links`, `test_req_s49_only_the_last_14_days_and_a_flag_is_shown`, `test_req_s49_the_feed_is_well_formed_without_events`, `test_req_s49_a_price_table_and_a_price_per_query_or_image_are_shown_as_they_are`, `test_req_s49_every_price_value_has_a_text`, `test_req_s36_about_rows_and_the_prompt_box` | test |
| REQ-S50 | `test_req_s50_the_digest_counts_moves_arrivals_and_the_index`, `test_req_s50_the_index_comes_from_the_latest_leaderboard_with_both_prices`, `test_req_s50_a_quiet_week_still_reads` | test |
| REQ-S51 | `test_req_s51_each_watched_model_is_checked_for_the_three_changes`, `test_req_s51_a_key_without_litellms_prefix_is_found_and_batch_prices_do_not_count`, `test_req_s51_the_report_names_the_changes_and_says_when_nothing_changed`, `test_req_s51_the_script_exits_1_on_a_change_0_otherwise_2_without_data`, `test_req_s51_the_action_runs_the_script_with_its_inputs` | test |
| REQ-S52 | `test_req_s52_a_badge_per_listed_model_with_prices_outlook_and_retirement`, `test_req_s52_the_slug_is_safe_for_a_file_and_an_address` | test |
| REQ-S53 | `test_req_s53_incidence_by_maker_with_small_makers_pooled`, `test_req_s53_a_maker_row_needs_20_models_still_followed` | test |
| REQ-S54 | `test_req_s54_the_guard_series_counts_each_weeks_changes_and_tags`, `test_req_s54_a_real_drop_is_found_and_no_change_is_called_no_change`, `test_req_s54_too_few_weeks_gives_nothing` | test |
| REQ-S55 | `test_req_s55_ccusage_daily_rows_become_units_per_day_and_model`, `test_req_s55_ccusage_sessions_are_the_units`, `test_req_s55_codeburn_records_are_summed_per_session_and_day_with_the_task`, `test_req_s55_a_plain_mix_and_bad_input`, `test_req_s55_bootstrap_ranges_and_the_verdict`, `test_req_s55_the_same_work_is_priced_on_every_rated_model_at_each_days_price`, `test_req_s55_cheaper_models_that_keep_the_rating_and_the_headline`, `test_req_s55_two_models_for_real_or_not_enough_data`, `test_req_s55_a_codeburn_export_brings_one_shot_rates`, `test_req_s55_a_model_listed_after_the_usage_is_priced_at_its_first_price`, `test_req_s55_unknown_models_and_bad_input`, `test_req_s55_through_the_tool` in `mcp/tests/test_usage.py`; `test_req_s55_the_script_prices_an_export` | test |
| REQ-S56 | `test_req_s56_every_tool_says_when_to_use_it_and_names_a_sibling`, `test_req_s56_find_models_looks_one_model_up_by_name` in `mcp/tests/test_server.py` | test |
| REQ-S57 | `test_req_s57_prices_past_a_prompt_size_and_for_the_hour_long_cache`, `test_req_s57_data_json_carries_the_long_context_and_hour_long_cache_prices` | test |
| REQ-S36 | `test_req_s36_one_page_or_natural_scrolling`, `test_req_s36_about_rows_and_the_prompt_box`; every view and panel in a browser at 1920 x 1080, 1440 x 900, 1366 x 768, 1269 x 746, 1024 x 700, 768 x 1024, 390 x 844, 390 x 664, 360 x 740 and 375 x 560, on the page and on the site copy | test, demonstration |
| REQ-S27 | `test_req_s27_task_guess_known_answers`, `test_req_s27_attachments_decide_first`, `test_req_s27_the_guess_says_why`, `test_req_s27_wilson_interval_known_answer`, `test_req_s27_a_guess_is_right_when_it_is_one_of_the_tasks`, `test_req_s27_score_against_always_overall`; `route_eval.json` | test, analysis |
| REQ-S26 | `test_req_s26_open_licences`, `test_req_s26_litellm_file_must_stay_in_the_mit_part`, `test_req_s26_all_open_means_everything_is_used`, `test_req_s26_a_closed_ratings_licence_drops_the_ratings_and_is_reported`, `test_req_s26_a_closed_data_licence_stops_publishing`, `test_req_s26_unreachable_ratings_are_left_out_not_failed`; the licence line on the page | test, demonstration |
| REQ-S25 | `test_req_s25_arena_names_are_tried_longest_first`, `test_req_s25_matching_prefers_the_arena_maker`, `test_req_s25_best_variant_kept_and_unmatched_left_out`, `test_req_s25_arena_down_means_no_ratings`, `test_req_s25_best_value_is_the_cheapest_tied_with_the_top`; the Best value tab | test, demonstration |

All tests run on every pull request and before every daily refresh.