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
anthropic / claude-3.5-sonnet).
Verified by: automated tests on named examples.

**REQ-S19 Last 7 days.** The page shall list every addition, removal,
price change and retirement date change in the 7 days before the
latest data.
Verified by: an automated test.

**REQ-S20 Corrections.** Every change that meets D10, D11 or D12 shall
be tagged as a bulk clean up, a unit fix or reverted. The page shall
show the tag next to the change, shall offer to hide tagged changes in
the last 7 days, and shall leave unit fixes and reverted changes out of
each model's count of price changes.
Verified by: automated tests at and just below each threshold.

**REQ-S21 Real changes only.** Alongside the main result, the analysis
shall report the same estimates with unit fixes and reverted changes
ignored, and with a model removed in a bulk clean up censored on that
day rather than removed. The page shall show both at 1 year, side by
side.
Verified by: automated tests on a small example and on the page.

**REQ-S22 SQL cross-check.** Every run shall build the table of
subjects (one row per model: days followed and how it ended) a second
time, in SQL, under every definition in REQ-S10 and REQ-S21, and shall
stop before publishing if the SQL and Python tables differ for any
model.
Verified by: automated tests in which each model checks one rule, and
the check line in every daily run log.

## 5. Known limitations

- **L1** Times are when LiteLLM edited its catalogue, not
  when a provider changed a price. The lag is unknown.
- **L2** Some price changes in the first week correct a wrong
  first entry rather than reprice the model (issue #7). D11 and D12
  catch the clear cases; smaller corrections still count.
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
- **L11** The tags in D10 to D12 come from fixed rules, not from
  reading each change. A real price cut of 100 times would be tagged as
  a unit fix, and a clean up spread over several days of fewer than 50
  removals would not be tagged. How often the rules are right has not
  yet been checked against a hand labelled sample (issue #7).
- **L12** The page depends on LiteLLM keeping the same file name and on
  GitHub Actions. If a daily refresh fails, nothing is published and the
  page keeps the last good build, with its data date in the footer.

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
| REQ-S18 | `test_req_s18_one_model_on_many_hosts_is_grouped`, `test_req_s18_naming_rules` | test |
| REQ-S19 | `test_req_s19_last_seven_days_lists_every_change` | test |
| D10 | `test_req_s20_bulk_clean_up_starts_at_50_removals_in_a_day` | test |
| D11 | `test_req_s20_unit_fix_is_100_times_either_way` | test |
| D12 | `test_req_s20_a_change_undone_within_30_days_is_reverted` | test |
| REQ-S20 | `test_req_s20_corrections_are_tagged_and_not_counted` | test |
| REQ-S21 | `test_req_s21_real_changes_only`, `test_req_s21_page_compares_every_change_with_real_changes` | test |
| REQ-S22 | `test_req_s22_sql_and_python_agree`, `test_req_s22_sql_known_answer`, `test_req_s22_a_disagreement_stops_the_check`; the "SQL check" line in every daily run | test, demonstration |

All tests run on every pull request and before every daily refresh.