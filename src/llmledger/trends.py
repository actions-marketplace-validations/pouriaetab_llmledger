"""Arena's ratings over time, and what top quality has cost, for the Trends view.

Arena publishes every past leaderboard in one file (the "full" split of its dataset on
Hugging Face, CC BY 4.0, the same dataset as the ratings). The pipeline reads the overall
text ratings from it once a day with pyarrow. If the file or pyarrow is missing, the page
keeps yesterday's trends from the live page, or is built without them.

Three series come out:
- lines: every model that was ever in the top 3 of the closed models or of the open ones
  (weights anyone can download), with its rating at each leaderboard;
- best: for every maker that was ever in the top 5, its best rating at each leaderboard;
- race: at each leaderboard, the price of the top rated model we can price, the cheapest
  of the top 10, and the cheapest model rated at least as high as the model that was
  first a year earlier. A price is per 1M tokens, 3 read for every 1 written, at the
  model's cheapest host that day, rebuilt from the history of every price change.
"""
import json
import re
import shutil
import tempfile
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from llmledger import arena

FULL = ("https://huggingface.co/datasets/" + arena.DATASET +
        "/resolve/main/text_style_control/full-00000-of-00001.parquet")
COLUMNS = ["model_name", "organization", "license", "rating", "leaderboard_publish_date"]
TOP_EACH = 3        # lines per group in Open vs closed
TOP_MAKERS = 5      # makers in Top 5 makers
RACE_TOP = 10       # "the top 10" in the price race
YEAR = 365
MIX = (3, 1)        # tokens read for every token written, in the blended price
TEXT_MODES = {"chat", "responses", "completion", ""}
PRICES = ("input_cost_per_token", "output_cost_per_token")


def is_open(licence):
    """Arena marks closed models "Proprietary"; any other licence means the weights can be downloaded."""
    text = str(licence or "").strip().lower()
    return bool(text) and text != "proprietary"


def same(name):
    """One key for one model across leaderboards: Arena renamed many models on 15 Oct 2026
    ("claude-opus-4-6-high" became "Claude Opus 4.6 (High)")."""
    text = re.sub(r"[()]", " ", str(name).strip().lower())
    text = re.sub(r"(?<=\d)\.(?=\d)", "-", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def fetch(url=FULL):
    """Every past overall leaderboard as rows {name, maker, open, rating, date}, or None."""
    try:
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "full.parquet"
            request = urllib.request.Request(url, headers={"User-Agent": "llmledger"})
            with urllib.request.urlopen(request, timeout=180) as response, open(path, "wb") as f:
                shutil.copyfileobj(response, f)
            table = pq.read_table(path, columns=COLUMNS, filters=[("category", "=", "overall")])
        return [{"name": r["model_name"], "maker": r["organization"] or "", "open": is_open(r["license"]),
                 "rating": float(r["rating"]), "date": str(r["leaderboard_publish_date"])[:10]}
                for r in table.to_pylist() if r["rating"] is not None]
    except Exception as error:
        print("Arena history skipped:", error)
        return None


def previous(url):
    """The trends on the page that is live now, if Arena's history cannot be read today."""
    try:
        text = arena._get_text(url)
        data = json.loads(text[text.index("{"):text.rstrip().rstrip(";").rindex("}") + 1])
        return data.get("trends")
    except Exception as error:
        print("No earlier trends either:", error)
        return None


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def blend(read, written):
    """Dollars per 1M tokens for the MIX of tokens read and written."""
    return (MIX[0] * read + MIX[1] * written) / sum(MIX)


def price_at(record, events, day):
    """A listing's blended price per 1M tokens on a day (YYYY-MM-DD), or None.

    record is a catalog.model_records row; events its catalogue history
    ([day, kind, field, old, new, flag, source], oldest first). The price today is rolled back
    through every later change of the two token prices. Unit fixes and likely corrections
    (D14) are not rolled back: the price before a fix was a mistake, not a price anyone paid.
    """
    added, removed = record[6], record[7]
    if (added and day < added) or (removed and day >= removed):
        return None
    now = {PRICES[0]: record[9], PRICES[1]: record[10]}
    for when, kind, field, old, new, flag, *_ in reversed(events):
        if when <= day:
            break
        if kind == "price" and field in now and flag not in ("unit", "likely"):
            old = _number(old)
            now[field] = None if old is None else old * 1_000_000
    read, written = now[PRICES[0]], now[PRICES[1]]
    if not read or not written or read < 0 or written < 0:
        return None      # missing, or free (a free listing is not a price)
    return blend(read, written)


class _Names:
    def __init__(self):
        self.items, self.at = [], {}

    def __call__(self, name):
        if name not in self.at:
            self.at[name] = len(self.items)
            self.items.append(name)
        return self.at[name]


def _round(price):
    return None if price is None else float(f"{price:.4g}")


def build(rows, records, events):
    """The Trends view's data, or None when there are no rows."""
    if not rows:
        return None
    by_date, shown = defaultdict(list), {}
    for row in sorted(rows, key=lambda r: r["date"]):
        row = dict(row, key=same(row["name"]))
        by_date[row["date"]].append(row)
        shown[row["key"]] = row["name"]          # the name it has on its latest leaderboard
    dates = sorted(by_date)
    ranked = {d: sorted(by_date[d], key=lambda r: -r["rating"]) for d in dates}
    names, makers = _Names(), _Names()

    keep, top_makers = set(), defaultdict(int)
    for d in dates:
        for group in (False, True):
            keep.update(r["key"] for r in [r for r in ranked[d] if r["open"] == group][:TOP_EACH])
        seen = []
        for r in ranked[d]:
            if r["maker"] and r["maker"] not in seen:
                seen.append(r["maker"])
                if len(seen) == TOP_MAKERS:
                    break
        for maker in seen:
            top_makers[maker] += 1
    # makers in the order they were most often in the top 5, so their colours stay fixed
    maker_order = sorted(top_makers, key=lambda m: (-top_makers[m], m))
    for maker in maker_order:
        makers(maker)

    lines, best = {}, {}
    for i, d in enumerate(dates):
        for r in ranked[d]:
            if r["key"] in keep:
                line = lines.setdefault(r["key"], [names(shown[r["key"]]), makers(r["maker"]), int(r["open"]), []])
                if not line[3] or line[3][-2] != i:      # one point per leaderboard
                    line[3].extend((i, round(r["rating"])))
            if r["maker"] in top_makers and (r["maker"], i) not in best:
                best[(r["maker"], i)] = (round(r["rating"]), names(shown[r["key"]]))
    best_out = []
    for maker in maker_order:
        points = []
        for i in range(len(dates)):
            if (maker, i) in best:
                points.extend((i, *best[(maker, i)]))
        best_out.append([makers(maker), points])

    return {
        "source": arena.SOURCE,
        "date": dates[-1],
        "dates": dates,
        "mix": list(MIX),
        "lines": sorted(lines.values(), key=lambda line: line[0]),
        "best": best_out,
        "race": race(ranked, dates, records, events, lambda r: names(shown[r["key"]])),
        "names": names.items,
        "makers": makers.items,
    }


def race(ranked, dates, records, events, name_of):
    """[date index, top price, its name, its rank, cheapest of the top 10, its name,
    a year's quality price, its name, last year's top model, its price then] per leaderboard."""
    groups, members = {}, defaultdict(list)
    for record in records:
        groups.setdefault(record[2], set()).add(record[1])
        if record[4] in TEXT_MODES:
            members[record[1] + " / " + record[2]].append(record)
    found, cache = {}, {}

    def priced(row, day):
        name = row["name"]
        if name not in found:
            found[name] = arena.match(name, row["maker"], groups)
        group = found[name]
        if group is None:
            return None
        if (group, day) not in cache:
            prices = [p for p in (price_at(rec, events.get(rec[0], []), day) for rec in members.get(group, []))
                      if p is not None]
            cache[(group, day)] = min(prices) if prices else None
        return cache[(group, day)]

    out = []
    for i, day in enumerate(dates):
        top = next(((rank, r, p) for rank, r in enumerate(ranked[day], 1)
                    if (p := priced(r, day)) is not None), None)
        ten = [(p, r) for r in ranked[day][:RACE_TOP] if (p := priced(r, day)) is not None]
        cheap = min(ten, key=lambda pr: pr[0]) if ten else None
        year = [None, None, None, None]
        back = (date.fromisoformat(day) - timedelta(days=YEAR)).isoformat()
        earlier = [d for d in dates[:i] if d <= back]
        if earlier:
            then = earlier[-1]
            first = ranked[then][0]
            now = next((r for r in ranked[day] if r["key"] == first["key"]), None)
            if now is not None:
                good = [(p, r) for r in ranked[day] if r["rating"] >= now["rating"]
                        and (p := priced(r, day)) is not None]
                if good:
                    p, r = min(good, key=lambda pr: pr[0])
                    year = [_round(p), name_of(r), name_of(first), _round(priced(first, then))]
        out.append([i,
                    _round(top[2]) if top else None, name_of(top[1]) if top else None, top[0] if top else None,
                    _round(cheap[0]) if cheap else None, name_of(cheap[1]) if cheap else None,
                    *year])
    return out
