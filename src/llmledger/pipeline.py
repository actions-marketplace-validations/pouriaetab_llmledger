import csv
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from llmledger import (arena, catalog, corrections, electricity, events, flags, guard, guard_effect, history,
                       licences, makers, page, route_eval, sql, survival, trends, unpriced)

SOURCE = "https://github.com/BerriAI/litellm.git"
UPSTREAM = Path("data/upstream")
EVENTS = "data/events.csv"
SURVIVAL = "data/survival.csv"
SITE = "site"
LIVE = "https://pouriaetab.github.io/llmledger/"   # the published page: compared before publishing, and read back if Arena is down


def check_python(pin_file=".python-version"):
    wanted = Path(pin_file).read_text().strip()
    running = platform.python_version()
    if running == wanted:
        return f"python {running}, as pinned in {pin_file}"
    return (f"WARNING: python {running}, but {pin_file} pins {wanted}; "
            "numbers may differ slightly")


def update(repo=UPSTREAM):
    if repo.exists():
        subprocess.run(("git", "fetch", "--quiet", "origin", "main"),
                       cwd=repo, check=True)
    else:
        subprocess.run(("git", "clone", "--quiet", "--filter=blob:none",
                        "--no-checkout", SOURCE, str(repo)), check=True)


def main():
    print(check_python())
    report, allowed = licences.main()
    if not allowed["data"]:
        raise SystemExit("Stopped: LiteLLM's licence is no longer open; nothing was published.")
    update()
    print("versions fetched:", history.prefetch(UPSTREAM))
    last = {}
    events.main(UPSTREAM, EVENTS, last)
    sizes = survival.main(EVENTS, SURVIVAL)
    with open(EVENTS, newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"SQL check: all {sql.check(rows):,} models agree")
    data = catalog.build(rows, last, catalog.end_of(rows))
    marked = flags.mark(rows)
    data["makers"] = makers.build(marked, catalog.end_of(rows))
    data["guard"] = guard_effect.build(marked)
    print(f"By maker: {len(data['makers']['rows']) - 1} rows; guard: {data['guard']['reading'] if data['guard'] else 'not measured'}")
    tables = arena.fetch() if allowed["ratings"] else None
    data["arena"] = arena.build(tables, data["models"]) if tables else None
    if data["arena"] is None and allowed["ratings"]:
        data["arena"] = arena.previous(LIVE + "data.js")
        if data["arena"]:
            print("Arena ratings: kept the ones on the live page, published", data["arena"]["date"])
    rows_over_time = trends.fetch() if allowed["trends"] else None
    data["trends"] = trends.build(rows_over_time, data["models"], data["events"]) if rows_over_time else None
    if data["trends"] is None and allowed["trends"]:
        data["trends"] = trends.previous(LIVE + "data.js")
        if data["trends"]:
            print("Trends: kept the ones on the live page, up to", data["trends"]["date"])
    elif data["trends"]:
        print(f"Trends: {len(data['trends']['dates'])} Arena leaderboards, "
              f"{data['trends']['dates'][0]} to {data['trends']['date']}")
    data["licences"] = report
    if route_eval.RESULT.exists():
        data["route_eval"] = json.loads(route_eval.RESULT.read_text())
    if corrections.OUT.exists():
        data["corrections"] = corrections.summary(json.loads(corrections.OUT.read_text()))
    if data["arena"]:
        print(f"Arena ratings: {data['arena']['matched']} of "
              f"{data['arena']['total']} models matched to the catalogue")
    versions = history.commits(UPSTREAM)
    sha, when = versions[-1]
    built = datetime.now(timezone.utc)
    if allowed["ratings"] and allowed["trends"]:
        data["unpriced"] = unpriced.build(tables, rows_over_time, data["models"], versions[0][1].date().isoformat(),
                                          built.date())
        if data["unpriced"] is None:
            data["unpriced"] = unpriced.previous(LIVE + "data.js")
        if data["unpriced"]:
            print(f"Not yet priced: {len(data['unpriced']['models'])} recent Arena models, "
                  f"{data['unpriced']['timing']['models']} timed")
    # EIA's prices: fresh while its reuse page says public domain; the live page's while that cannot be read
    eia = next((row["status"] for row in report if row["role"] == "electricity"), None)
    if eia in ("open", "unchecked"):
        data["electricity"] = (electricity.fetch() if eia == "open" else None) or electricity.previous(LIVE + "data.js")
        if data["electricity"]:
            print(f"Electricity: {data['electricity']['label']}, US average "
                  f"${data['electricity']['us']:.4f} a kWh, {len(data['electricity']['states'])} states")
    info = {
        "models": sizes["main"],
        "since": versions[0][1],
        "sha": sha,
        "when": when,
        "built": built,
        "python": platform.python_version(),
    }
    data["built"] = info["built"].isoformat(timespec="seconds")
    guard.check(data, LIVE + "data.js")
    print("page written:", page.main(SURVIVAL, SITE, info, data))


if __name__ == "__main__":
    main()
