import csv
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from llmledger import arena, catalog, events, history, licences, page, route_eval, sql, survival

SOURCE = "https://github.com/BerriAI/litellm.git"
UPSTREAM = Path("data/upstream")
EVENTS = "data/events.csv"
SURVIVAL = "data/survival.csv"
SITE = "site"
LIVE = "https://pouriaetab.github.io/llmledger/"   # the published page, read back only if Arena is down


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
    tables = arena.fetch() if allowed["ratings"] else None
    data["arena"] = arena.build(tables, data["models"]) if tables else None
    if data["arena"] is None and allowed["ratings"]:
        data["arena"] = arena.previous(LIVE + "data.js")
        if data["arena"]:
            print("Arena ratings: kept the ones on the live page, published", data["arena"]["date"])
    data["licences"] = report
    if route_eval.RESULT.exists():
        data["route_eval"] = json.loads(route_eval.RESULT.read_text())
    if data["arena"]:
        print(f"Arena ratings: {data['arena']['matched']} of "
              f"{data['arena']['total']} models matched to the catalogue")
    versions = history.commits(UPSTREAM)
    sha, when = versions[-1]
    info = {
        "models": sizes["main"],
        "since": versions[0][1],
        "sha": sha,
        "when": when,
        "built": datetime.now(timezone.utc),
        "python": platform.python_version(),
    }
    print("page written:", page.main(SURVIVAL, SITE, info, data))


if __name__ == "__main__":
    main()
