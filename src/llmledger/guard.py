"""Before publishing: a new build must not be a step back from the page that is live now (REQ-S38).

LiteLLM's history only grows, so a build that knows fewer models, or whose data ends earlier, than the
live page was made from a broken or partial copy of that history. Listed models fall in one day only in a
clean up: the largest so far took 10% of them (9 October 2026), so a fall of a quarter or more is treated
as a broken build. Nothing is published then, and the live page stays as it was.

Set LLMLEDGER_SKIP_LIVE_CHECK=1 to publish anyway, for example after LiteLLM rewrites its history.
"""
import json
import os

from llmledger import arena

KEPT = 0.99      # models ever seen may fall by 1% at most (an old version that no longer reads)
LISTED = 0.75    # listed models may fall by less than a quarter in one build


def _listed(data):
    return sum(1 for record in data["models"] if record[5] == "listed")


def live(url, tries=3):
    """The data of the page that is live now, or None when it cannot be read (first run, offline)."""
    for _ in range(tries):
        try:
            text = arena._get_text(url)
            return json.loads(text[text.index("{"):text.rstrip().rstrip(";").rindex("}") + 1])
        except Exception as error:
            last = error
    print(f"Live check: the live page could not be read ({tries} tries), so there is nothing to compare with:", last)
    return None


def problems(new, old):
    """Why the new build is a step back from the old one; empty when it is not."""
    found = []
    if len(new["models"]) < KEPT * len(old["models"]):
        found.append(f"it knows {len(new['models']):,} models, the live page {len(old['models']):,}")
    if new["end"] < old["end"]:
        found.append(f"its data ends {new['end']}, before the live page's {old['end']}")
    if _listed(new) < LISTED * _listed(old):
        found.append(f"it lists {_listed(new):,} models, the live page {_listed(old):,}")
    return found


def check(new, url):
    """Stop before publishing when the new build is a step back from the live page."""
    if os.environ.get("LLMLEDGER_SKIP_LIVE_CHECK") == "1":
        print("Live check: skipped (LLMLEDGER_SKIP_LIVE_CHECK=1)")
        return
    old = live(url)
    if old is None:
        return
    found = problems(new, old)
    if found:
        raise SystemExit("Stopped: this build looks broken, so nothing was published: " + "; ".join(found) +
                         ". Set LLMLEDGER_SKIP_LIVE_CHECK=1 to publish it anyway.")
    print(f"Live check: {len(new['models']):,} models (live page {len(old['models']):,}), "
          f"{_listed(new):,} listed (live page {_listed(old):,}), data to {new['end']}")
