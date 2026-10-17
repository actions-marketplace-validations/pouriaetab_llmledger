"""Check, every run, that each outside source is still open for business use.

A source is open when its licence is on the OPEN list below: free to use,
including commercially, at most with credit. Anything else (a non-commercial
licence, a custom licence, no licence) is not open.

The pipeline calls check() before building:
- the LiteLLM price file is the data itself, so if it is not open the run
  stops and nothing is published;
- the Arena ratings are optional, so if they are not open the page is built
  without them;
- pyarrow reads Arena's past leaderboards for the Trends view, so if it is not open the page
  is built without the trend charts;
- the test tools are only used to run the tests, and the plug-in's packages (mcp/) only by
  the plug-in, so a change to either is reported.
Every problem is written to data/licence-problems.txt, and the daily refresh
opens a GitHub issue from that file. Results go on the page as licences.json.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

OPEN = {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "cc-by-4.0",
        "cc0-1.0", "unlicense", "0bsd", "psf-2.0", "python-2.0"}
CLASSIFIERS = {"MIT License": "mit", "Apache Software License": "apache-2.0",
               "BSD License": "bsd-3-clause", "ISC License (ISCL)": "isc"}
LITELLM_LICENSE = "https://raw.githubusercontent.com/BerriAI/litellm/main/LICENSE"
LITELLM_FILE = "model_prices_and_context_window.json"
ARENA = "https://huggingface.co/api/datasets/lmarena-ai/leaderboard-dataset"
ARENA_PROMPTS = "https://huggingface.co/api/datasets/lmarena-ai/arena-human-preference-140k"
PYPI = "https://pypi.org/pypi/{name}/{version}/json"
# Packages in requirements.txt that the daily build itself uses; the rest only run the tests.
PIPELINE = {"pyarrow"}
PROBLEMS = Path("data/licence-problems.txt")


def is_open(expression):
    """True if an SPDX licence expression allows business use."""
    if not expression:
        return False
    text = expression.strip().lower().strip("()")
    if " or " in text:
        return any(is_open(part) for part in text.split(" or "))
    if " and " in text:
        return all(is_open(part) for part in text.split(" and "))
    return text in OPEN


def litellm_licence(text, path=LITELLM_FILE):
    """'mit' if the file we read is under LiteLLM's MIT part, else what we found."""
    closed = re.findall(r'resides under the "([^"]+)" directory', text)
    if any(path.startswith(folder) for folder in closed):
        return "restricted folder"
    if "MIT License" in text and "Permission is hereby granted, free of charge" in text:
        return "mit"
    return "not MIT any more"


def pypi_licence(info):
    if info.get("license_expression"):
        return info["license_expression"]
    names = [CLASSIFIERS[c.split(" :: ")[-1]] for c in info.get("classifiers", [])
             if c.startswith("License ::") and c.split(" :: ")[-1] in CLASSIFIERS]
    return " or ".join(names) or (info.get("license") or "")


def _text(url):
    request = urllib.request.Request(url, headers={"User-Agent": "llmledger"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode()


def _requirements(path="requirements.txt"):
    pins = []
    for line in Path(path).read_text().split():
        name, _, version = line.partition("==")
        pins.append((name, version))
    return pins


def _plugin_requirements(path="mcp/pyproject.toml"):
    """The exact versions the plug-in (mcp/) pins: its dependencies and its build tool."""
    file = Path(path)
    return re.findall(r'"([A-Za-z0-9_.-]+)==([0-9][^"]*)"', file.read_text()) if file.exists() else []


def sources(get=_text, requirements=_requirements, plugin=_plugin_requirements):
    """(name, role, licence found) for every outside source; None if unreachable."""
    def attempt(read):
        try:
            return read()
        except Exception:
            return None
    found = [
        ("LiteLLM price file", "data",
         attempt(lambda: litellm_licence(get(LITELLM_LICENSE)))),
        ("Arena leaderboard", "ratings",
         attempt(lambda: (json.loads(get(ARENA)).get("cardData") or {}).get("license"))),
        ("Arena prompts", "measuring",
         attempt(lambda: (json.loads(get(ARENA_PROMPTS)).get("cardData") or {}).get("license"))),
    ]
    pins = [("pipeline" if name in PIPELINE else "tests", name, version) for name, version in requirements()]
    pins += [("plug-in", name, version) for name, version in plugin()]
    for role, name, version in pins:
        found.append((f"{name} {version}", role, attempt(
            lambda n=name, v=version: pypi_licence(json.loads(get(PYPI.format(name=n, version=v)))["info"]))))
    return found


def check(get=_text, requirements=_requirements, plugin=_plugin_requirements):
    """Returns (report, allowed): allowed says which optional parts may be used."""
    report = []
    for name, role, licence in sources(get, requirements, plugin):
        if licence is None:
            status = "unchecked"
        else:
            status = "open" if is_open(licence) else "not open"
        report.append({"source": name, "role": role, "licence": licence, "status": status})
    roles = {row["role"]: row["status"] for row in report if row["role"] in ("data", "ratings")}
    allowed = {"data": roles.get("data") != "not open", "ratings": roles.get("ratings") == "open"}
    allowed["trends"] = allowed["ratings"] and all(row["status"] != "not open" for row in report
                                                   if row["role"] == "pipeline")
    return report, allowed


def problems(report):
    lines = []
    for row in report:
        if row["status"] == "not open":
            action = {"data": "Nothing was published.",
                      "ratings": "The page was built without them.",
                      "measuring": "Measure the task guess on another dataset.",
                      "tests": "Find an open replacement for the tests.",
                      "pipeline": "The trend charts were left out; find an open replacement.",
                      "plug-in": "Find an open replacement for the plug-in (mcp/) before its next release."}[row["role"]]
            lines.append(f"- {row['source']}: licence is now {row['licence']!r}, "
                         f"which is not open for business use. {action}")
        elif row["status"] == "unchecked" and row["role"] not in ("tests", "plug-in", "pipeline"):
            lines.append(f"- {row['source']}: the licence could not be checked today."
                         + (" The ratings were left out." if row["role"] == "ratings" else ""))
    return lines


def main():
    PROBLEMS.unlink(missing_ok=True)
    report, allowed = check()
    for row in report:
        print(f"licence {row['status']:>9}: {row['source']} ({row['licence']})")
    found = problems(report)
    if found:
        PROBLEMS.parent.mkdir(parents=True, exist_ok=True)
        PROBLEMS.write_text("\n".join(found) + "\n")
    return report, allowed


if __name__ == "__main__":
    report, allowed = main()
    sys.exit(0 if allowed["data"] and all(r["status"] != "not open" for r in report) else 1)
