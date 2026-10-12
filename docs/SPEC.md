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

## 5. Known limitations

- **L1** Times are when LiteLLM edited its catalogue, not
  when a provider changed a price. The lag is unknown.
- **L2** Some price changes in the first week correct a wrong
  first entry rather than reprice the model (issue #7).
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

All tests run on every pull request (`.github/workflows/tests.yml`).