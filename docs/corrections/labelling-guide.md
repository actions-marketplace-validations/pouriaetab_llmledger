# Labelling guide: corrections and real price changes

Issue #7 asks whether a model's first price change is a correction of the
catalogue's entry or a real change in what the host charges. This guide
says how each row of `sample.csv` was labelled, so anyone can check a label or
change it and rebuild the numbers with `python -m llmledger.corrections`.

## What is labelled

1. **Population.** Every model added after the catalogue's first version
   (6 September 2023) whose price later changed from one number to a different
   number (D5), up to the events of 17 October 2026, 06:56 UTC. One row per
   model: its first such change. 800 rows, 165 of them within 7 days of the
   model being added.
2. **Sample.** 100 rows drawn at random from the first 7 days and 100 from
   later (`random.Random(7)`, `corrections.draw`). The numbers are weighted
   back to the population: each first-week row stands for 1.65 rows, each
   later row for 6.35.

## The three labels

- **correction**: the change is about the catalogue, not the host's price.
  Almost always it fixes a number that was wrong when it was entered; one row
  in the sample is a slip of its own (a decimal moved in an unrelated commit).
- **repricing**: the number was right when it was entered, and the host's
  price changed later. A change recorded months after the host changed its
  price is still a repricing.
- **unclear**: the evidence cannot tell the two apart.

## Evidence, in this order

1. **The LiteLLM commit that made the change.** For a merge, the branch name
   and the merged commits that touch the price file; the one naming the model
   or its host is used.
2. **The numbers themselves.** The old and new value, and their ratio.
3. **Published price changes.** A host's announced cut, increase,
   introductory price or repricing, named in the commit or known from the
   host's own announcement (each such row says which).

The number of days since the model was added and the page's tags (D10 to D12)
are not evidence for a label: they are what the rules being tested use.

## Rules for each label

A row is a **correction** when any of these holds and nothing says the host
changed its price:

1. The commit or branch says the number was wrong or fixes it: fix, correct,
   wrong, drop unverified, price at the standard tier, extrapolate, align or
   sync this model's price with the host's page.
2. The old number is a placeholder (0).
3. The change is a unit or scale mistake: 100 times or more, or a slip of
   scale (per 1K instead of per 1M tokens, per minute instead of per second,
   a decimal moved) that brings the number to the host's published price.
4. The old number is another model's or another tier's price: a copied row,
   or a regional row that had the global price (Bedrock's in-region prices are
   10% above the global ones).
5. The two numbers are the same price written with different rounding (under
   0.5% apart).
6. The change was made inside the pull request that added the model.

A row is a **repricing** when:

1. The commit names a price change by the host: a cut, an increase, an
   introductory or promotional price, a retirement repricing, a new version's
   pricing.
2. Or the change came from an automated copy of the host's own price list
   (LiteLLM's price-sync bot, or a host's own catalogue refresh such as
   DeepInfra's) and nothing says the old number was wrong.

Everything else is **unclear**: release and staging merges where no merged
commit names the row, maintenance passes ("registry audit", "update pricing")
that give no reason, and alias rows (`*-latest`) whose alias may have moved.

## Notes

1. Rows labelled from the numbers alone (unit mistakes, placeholders,
   rounding) are corrections by any reading. The page's tags catch the unit
   mistakes too, which makes the tags look as good as they are on those rows
   and no better.
2. One LiteLLM commit can change many rows at once (Novita's 10,000 times unit
   fix of January 2026 changed 82 first prices). Rows of one commit are not
   independent, so the intervals come from a bootstrap that resamples whole
   commits.
3. Each row of `sample.csv` keeps the reason for its label and the commit's
   first line.
