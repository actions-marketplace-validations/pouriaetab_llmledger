"""How often does the task guess (route.js) pick the right task?

Measured on real prompts from Arena's human preference dataset
(lmarena-ai/arena-human-preference-140k, CC BY 4.0), whose rows carry Arena's
own labels: coding, math, creative writing, and the prompt's language.

The sample is drawn once, with a fixed seed, as 200 small pieces of 10 rows
spread across the dataset, and kept apart from the 1,000 prompts the rules were
tuned on. Run by hand after changing the rules; it needs the network and node:

    PYTHONPATH=src python -m llmledger.route_eval

It writes src/llmledger/route_eval.json, which the page shows.
"""
import json
import math
import random
import subprocess
import time
import urllib.request
from datetime import date
from pathlib import Path

DATASET = "lmarena-ai/arena-human-preference-140k"
SOURCE = "https://huggingface.co/datasets/" + DATASET
ROWS = ("https://datasets-server.huggingface.co/rows?dataset=" + DATASET +
        "&config=default&split=train&offset={offset}&length={length}")
TOTAL = 135_600
TUNE = (1, 10, 100)       # seed, pieces, rows per piece: the 1,000 prompts used to tune
TEST = (2, 200, 10)       # the 2,000 prompts used to measure, never used to tune
LANGUAGES = {"ru": "russian", "zh": "chinese", "ja": "japanese", "ko": "korean",
             "es": "spanish", "fr": "french", "de": "german"}
LABELLED = ("coding", "math", "creative_writing")
HERE = Path(__file__).parent
RESULT = HERE / "route_eval.json"


def wilson(hits, n, z=1.96):
    """95% Wilson interval for a proportion; (0, 1) when n is 0."""
    if n == 0:
        return (0.0, 1.0)
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def truth(row):
    """The Arena tasks a prompt belongs to, by Arena's own labels."""
    tasks = {task for task in LABELLED if row[task]}
    if row["language"] in LANGUAGES:
        tasks.add(LANGUAGES[row["language"]])
    return tasks


def correct(guess, tasks):
    """A guess is right if it is one of the prompt's tasks. Building websites
    counts as coding. When the prompt has none of the labelled tasks, any
    other guess (overall or a field) is right, because Arena labels no field."""
    if guess == "webdev":
        guess = "coding"
    if guess in tasks:
        return True
    labelled = set(LABELLED) | set(LANGUAGES.values())
    return not tasks and guess not in labelled


def score(rows, guesses):
    n = len(rows)
    right = sum(correct(g, truth(r)) for r, g in zip(rows, guesses))
    baseline = sum(not truth(r) for r in rows)
    report = {
        "n": n,
        "right": [right, *wilson(right, n)],
        "always_overall": [baseline, *wilson(baseline, n)],
        "tasks": {},
    }
    for task in (*LABELLED, *LANGUAGES.values()):
        said = [g == task or (task == "coding" and g == "webdev") for g in guesses]
        actual = [task in truth(r) for r in rows]
        tp = sum(s and a for s, a in zip(said, actual))
        predicted, present = sum(said), sum(actual)
        report["tasks"][task] = {
            "present": present,
            "precision": [tp, predicted, *wilson(tp, predicted)],
            "recall": [tp, present, *wilson(tp, present)],
        }
    return report


def first_prompt(conversation):
    for turn in conversation or []:
        if turn.get("role") == "user":
            return " ".join(part.get("text") or "" for part in turn.get("content", [])
                            if part.get("type") == "text")
    return ""


def _get(url, tries=4):
    request = urllib.request.Request(url, headers={"User-Agent": "llmledger"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(3 * (attempt + 1))


def sample(seed, pieces, length):
    offsets = sorted(random.Random(seed).sample(range(0, TOTAL - 100, 100), pieces))
    rows = []
    for offset in offsets:
        try:
            page = _get(ROWS.format(offset=offset, length=length))
        except Exception as error:      # a piece the server cannot serve is skipped, and counted
            print(f"skipped the piece at {offset}: {error}")
            continue
        for item in page["rows"]:
            row = item["row"]
            tags = row.get("category_tag") or {}
            rows.append({
                "piece": offset,
                "text": first_prompt(row.get("conversation_a")),
                "language": row.get("language"),
                "coding": bool(row.get("is_code")),
                "math": bool((tags.get("math_v0.1") or {}).get("math")),
                "creative_writing": bool((tags.get("creative_writing_v0.1") or {}).get("creative_writing")),
            })
        time.sleep(0.3)
    return rows


def guesses(rows):
    script = ("const r = require(%s); let s = ''; process.stdin.on('data', d => s += d);"
              "process.stdin.on('end', () => console.log(JSON.stringify("
              "JSON.parse(s).map(t => r.guessTask(t, {}).task))));") % json.dumps(str(HERE / "route.js"))
    done = subprocess.run(["node", "-e", script], input=json.dumps([r["text"] for r in rows]),
                          capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def main(cache="data/route_test.json"):
    path = Path(cache)
    if path.exists():
        rows = json.loads(path.read_text())
    else:
        rows = sample(*TEST)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows))
    report = score(rows, guesses(rows))
    pieces = len({row["piece"] for row in rows})
    report.update(source=SOURCE, licence="CC BY 4.0", measured=date.today().isoformat(),
                  sample=(f"{len(rows):,} prompts from {pieces} pieces of 10 spread across the dataset "
                          f"(seed {TEST[0]}; {TEST[1] - pieces} pieces the server could not serve were "
                          "skipped), kept apart from the 1,000 prompts used to write the rules"))
    RESULT.write_text(json.dumps(report, indent=1) + "\n")
    right, low, high = report["right"]
    base, blow, bhigh = report["always_overall"]
    print(f"task guess right {right / report['n']:.1%} ({low:.1%} to {high:.1%}); "
          f"always 'overall' {base / report['n']:.1%} ({blow:.1%} to {bhigh:.1%})")
    return report


if __name__ == "__main__":
    main()
