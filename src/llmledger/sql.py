import csv
import sqlite3
from pathlib import Path

from llmledger import flags, survival

QUERY = Path(__file__).with_name("survival.sql").read_text()


def load(rows):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE events (n INTEGER PRIMARY KEY, at TEXT, "
               "sha TEXT, model TEXT, kind TEXT, field TEXT, "
               "old TEXT, new TEXT)")
    db.executemany(
        "INSERT INTO events (at, sha, model, kind, field, old, new) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ((row["when"], row["sha"], row["model"], row["kind"],
          row["field"], row["old"], row["new"]) for row in rows),
    )
    return db


def sql_table(db, definition="main"):
    return {model: (days, kind) for model, days, kind
            in db.execute(QUERY, {"definition": definition})}


def python_table(rows, definition="main"):
    return {
        model: ((when - start).total_seconds() / 86400, kind)
        for model, (start, when, kind)
        in survival.subject_table(rows, definition).items()
    }


def check(rows):
    flags.mark(rows)
    db = load(rows)
    for definition in survival.DEFINITIONS:
        ours, theirs = sql_table(db, definition), python_table(rows, definition)
        differ = sorted(model for model in ours.keys() | theirs.keys()
                        if ours.get(model) != theirs.get(model))
        if differ:
            raise AssertionError(
                f"{definition}: SQL and Python disagree on {len(differ)} "
                f"models, for example {differ[:3]}")
    return len(theirs)


def main(source="data/events.csv"):
    with open(source, newline="") as f:
        rows = list(csv.DictReader(f))
    models = check(rows)
    print(f"SQL check: all {models:,} models agree under "
          f"{len(survival.DEFINITIONS)} definitions")
    return models


if __name__ == "__main__":
    main()
