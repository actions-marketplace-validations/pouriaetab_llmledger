"""Watch the models a project uses: fail, or just say so, when one changes.

Reads llmledger's daily data.json and, for each model named, reports whether it is still
listed, whether its price changed in the last `days` days, and whether it has a retirement
date. Standard library only. Used by the GitHub Action in action.yml, and from a shell:

    python action/watch.py --models "openai/gpt-5,anthropic/claude-sonnet-4-5" --days 7

Exit 1 when a watched change is found (the Action turns that into a failed check or an
issue, as the workflow decides), 0 otherwise, 2 when the data cannot be read.
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import date, timedelta

DATA = "https://pouriaetab.github.io/llmledger/data.json"
PAGE = "https://pouriaetab.github.io/llmledger/"
CHANGES = ("price", "retirement", "removed")
# the prices most projects pay; --fields all watches every price field (batches, long context, ...)
FIELDS = {"input_cost_per_token": "input", "output_cost_per_token": "output",
          "cache_read_input_token_cost": "cache read", "cache_creation_input_token_cost": "cache write"}


def fetch(url=DATA):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def per_million(value):
    if value is None:
        return "none"
    v = float(value) * 1e6
    return f"${v:,.2f}" if v >= 0.1 else f"${v:,.4f}"


def resolve(asked, listed):
    """The listed key for what was asked: as given, or without a provider prefix LiteLLM does not
    use (openai/gpt-5 is listed as gpt-5), or the one key that ends with it."""
    if asked in listed:
        return asked, listed[asked]
    tail = asked.split("/")[-1]
    if tail in listed:
        return tail, listed[tail]
    ends = [k for k in listed if k.lower().endswith("/" + tail.lower()) or k.lower() == tail.lower()]
    if len(ends) == 1:
        return ends[0], listed[ends[0]]
    return asked, None


def check(machine, keys, days=7, today=None, fields=None):
    """[{key, listed, price_changes: [...], retire, note}] for each watched key. fields: the price
    fields that count (None: the four token prices in FIELDS; "all": every one)."""
    today = today or date.fromisoformat(machine["built"][:10])
    since = (today - timedelta(days=days)).isoformat()
    listed = {m["key"]: m for m in machine["models"]}
    out = []
    for asked in keys:
        key, m = resolve(asked, listed)
        row = {"key": asked, "listed": m is not None, "price_changes": [], "retire": None}
        if m is None:
            close = [k for k in listed if asked.lower().split("/")[-1] in k.lower()][:3]
            row["note"] = ("not listed in LiteLLM's catalogue today (removed, renamed or never listed)"
                           + (f"; close: {', '.join(close)}" if close else ""))
            out.append(row)
            continue
        if key != asked:
            row["key"] = f"{asked} (listed as {key})"
        for day, kind, field, old, new, flag, _ in machine["events"].get(key, []):
            if kind == "price" and day >= since and (fields == "all" or field in (fields or FIELDS)):
                row["price_changes"].append({"day": day, "field": FIELDS.get(field, field), "old": per_million(old),
                                             "new": per_million(new), "flag": flag})
        row["retire"] = m.get("retire")
        outlook = (m.get("outlook") or {}).get("90")
        if outlook and outlook.get("price"):
            row["chance_90d"] = round(100 * outlook["price"][0], 1)
        out.append(row)
    return out


def changed(row, watch=CHANGES):
    return (("removed" in watch and not row["listed"]) or ("price" in watch and row["price_changes"])
            or ("retirement" in watch and row.get("retire")))


def report(rows, days, watch=CHANGES):
    lines = []
    for r in rows:
        if not r["listed"]:
            lines.append(f"- {r['key']}: {r['note']}")
            continue
        bits = []
        if r["price_changes"]:
            bits.append("; ".join(f"{c['day']} {c['field']} {c['old']} -> {c['new']} per 1M" + (f" ({c['flag']})" if c["flag"] else "")
                                  for c in r["price_changes"]))
        if r.get("retire"):
            bits.append(f"retirement date {r['retire']}")
        state = ", ".join(bits) if bits else f"no change in the last {days} days"
        chance = f" ({r['chance_90d']}% chance of a price change in 90 days)" if r.get("chance_90d") is not None else ""
        lines.append(f"- {r['key']}: {state}{chance}")
    flagged = [r for r in rows if changed(r, watch)]
    head = (f"{len(flagged)} of {len(rows)} watched models changed" if flagged
            else f"No change in the {len(rows)} watched models")
    return head + f" ({PAGE}, data of the day)\n" + "\n".join(lines) + "\n", bool(flagged)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--models", required=True, help="LiteLLM keys, comma separated")
    ap.add_argument("--days", type=int, default=7, help="price changes within this many days count")
    ap.add_argument("--watch", default=",".join(CHANGES), help="which changes count: price,retirement,removed")
    ap.add_argument("--fields", default="", help="price fields that count: the token prices by default, or all")
    ap.add_argument("--data", default=DATA)
    args = ap.parse_args(argv)
    keys = [k.strip() for k in args.models.split(",") if k.strip()]
    watch = tuple(w.strip() for w in args.watch.split(",") if w.strip())
    try:
        machine = fetch(args.data) if args.data.startswith("http") else json.load(open(args.data))
    except Exception as e:                                                       # noqa: BLE001
        print(f"could not read {args.data}: {e}")
        return 2
    fields = "all" if args.fields.strip() == "all" else (tuple(f.strip() for f in args.fields.split(",") if f.strip()) or None)
    text, flagged = report(check(machine, keys, args.days, fields=fields), args.days, watch)
    print(text, end="")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"changed={'true' if flagged else 'false'}\n")
            f.write("report<<EOF\n" + text + "EOF\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("### llmledger watch\n\n" + text)
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
