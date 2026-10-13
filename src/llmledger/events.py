import csv
import json
from collections import Counter

from llmledger import history

COLUMNS = ["when", "sha", "model", "kind", "field", "old", "new"]


def _is_price(field):
    return "cost" in field or "pricing" in field

def _row(when, sha, model, kind, field="", old=None, new=None):
    return {
        "when": when,
        "sha": sha,
        "model": model,
        "kind": kind,
        "field": field,
        "old": json.dumps(old),
        "new": json.dumps(new),
    }


def _diff(when, sha, before, after):
    rows = []
    for model in sorted(after.keys() - before.keys()):
        rows.append(_row(when, sha, model, "added"))
    for model in sorted(before.keys() - after.keys()):
        rows.append(_row(when, sha, model, "removed"))
    for model in sorted(before.keys() & after.keys()):
        old_entry = before[model]
        new_entry = after[model]
        for field in sorted(old_entry.keys() | new_entry.keys()):
            old = old_entry.get(field)
            new = new_entry.get(field)
            if old == new:
                continue
            if _is_price(field):
                kind = "price"
            elif field == "deprecation_date":
                kind = "deprecation"
            else:
                continue
            rows.append(_row(when, sha, model, kind, field, old, new))
    return rows


def build(repo):
    versions = history.commits(repo)
    rows = []
    skipped = []
    before = None
    for number, (sha, when) in enumerate(versions, start=1):
        if number % 100 == 0:
            print(f"{number}/{len(versions)}  {when:%Y-%m-%d}")
        try:
            after, _ = history.snapshot(repo, sha)
        except json.JSONDecodeError:
            skipped.append(sha)
            continue
        stamp = when.isoformat()
        if before is None:
            for model in sorted(after):
                rows.append(_row(stamp, sha, model, "start"))
        else:
            rows.extend(_diff(stamp, sha, before, after))
        before = after
    return rows, skipped


def main(repo="data/upstream", out="data/events.csv"):
    rows, skipped = build(repo)
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    counts = Counter(row["kind"] for row in rows)
    print("rows written:", len(rows))
    for kind, n in sorted(counts.items()):
        print(f"  {kind}: {n}")
    print("broken versions skipped:", len(skipped))


if __name__ == "__main__":
    main()