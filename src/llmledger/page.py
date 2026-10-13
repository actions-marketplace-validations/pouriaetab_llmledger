import csv
import html
import json
import shutil
from pathlib import Path
from string import Template

from llmledger.survival import OUTCOMES

LABELS = {
    "price": "Price change",
    "retirement": "Retirement announced",
    "removed": "Removed",
    "none": "None of these",
}
DAY_LABELS = {30: "30 days", 90: "90 days", 180: "6 months",
              365: "1 year", 730: "2 years"}
DEFINITION_LABELS = {
    "main": "Any price field (main result)",
    "headline": "Input and output token prices only",
    "no_first_week": "Ignoring changes in the first week",
    "real_only": "Leaving out corrections",
}
COMPARED = {
    "main": "Every change (main result)",
    "real_only": "Real changes only",
}
REPO = "https://github.com/pouriaetab/llmledger"
LITELLM = "https://github.com/BerriAI/litellm"


def load(path):
    results = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["definition"], int(row["days"]), row["outcome"])
            results[key] = (float(row["estimate"]), float(row["ci_low"]),
                            float(row["ci_high"]), int(row["at_risk"]))
    return results


def day_month_year(when):
    return f"{when.day} {when:%B %Y}"


def stamp(when):
    return f"{when.day} {when:%B %Y, %H:%M} UTC"


def percent(value):
    return f"{100 * value:.1f}%"


def interval(results, key):
    estimate, low, high, _ = results[key]
    return f"{percent(estimate)} ({100 * low:.1f} to {100 * high:.1f})"


def cell(results, key):
    estimate, low, high, _ = results[key]
    return (f"{percent(estimate)}"
            f"<small>{100 * low:.1f} to {100 * high:.1f}</small>")


def bars(results, days):
    lines = []
    for day in days:
        segments = []
        for outcome in OUTCOMES:
            key = ("main", day, outcome)
            estimate = results[key][0]
            tip = f"{LABELS[outcome]}: {interval(results, key)}"
            segments.append(
                f'<span class="seg {outcome}" style="flex: {estimate:.6f}" '
                f'title="{html.escape(tip)}"></span>'
            )
        lines.append(
            f'<div class="row"><span class="when">{DAY_LABELS[day]}</span>'
            f'<span class="bar">{"".join(segments)}</span></div>'
        )
    return "\n".join(lines)


def table(results, days):
    head = "".join(f"<th>{LABELS[o]}</th>" for o in OUTCOMES)
    body = []
    for day in days:
        cells = "".join(
            f"<td>{cell(results, ('main', day, o))}</td>" for o in OUTCOMES
        )
        at_risk = results[("main", day, "none")][3]
        body.append(f"<tr><th>{DAY_LABELS[day]}</th>{cells}"
                    f"<td>{at_risk:,}</td></tr>")
    return (f"<table><thead><tr><th>Within</th>{head}<th>Still followed</th>"
            f"</tr></thead><tbody>{''.join(body)}</tbody></table>")


def sensitivity(results):
    body = "".join(
        f"<tr><th>{label}</th>"
        f"<td>{cell(results, (definition, 365, 'price'))}</td></tr>"
        for definition, label in DEFINITION_LABELS.items()
        if (definition, 365, "price") in results
    )
    return ("<table><thead><tr><th>What counts as a price change</th>"
            "<th>Within 1 year</th></tr></thead>"
            f"<tbody>{body}</tbody></table>")


def corrections(results):
    head = "".join(f"<th>{LABELS[o]}</th>" for o in OUTCOMES)
    body = "".join(
        f"<tr><th>{label}</th>"
        + "".join(f"<td>{cell(results, (definition, 365, o))}</td>"
                  for o in OUTCOMES)
        + "</tr>"
        for definition, label in COMPARED.items()
        if (definition, 365, "none") in results
    )
    return (f"<table><thead><tr><th>Within 1 year</th>{head}</tr></thead>"
            f"<tbody>{body}</tbody></table>")


def render(results, info):
    days = sorted({day for d, day, _ in results if d == "main"})
    year = {o: percent(results[("main", 365, o)][0]) for o in OUTCOMES}
    template = Template(Path(__file__).with_name("page.html").read_text())
    return template.substitute(
        models=f"{info['models']:,}",
        since=day_month_year(info["since"]),
        price=year["price"],
        retirement=year["retirement"],
        removed=year["removed"],
        bars=bars(results, days),
        table=table(results, days),
        sensitivity=sensitivity(results),
        corrections=corrections(results),
        sha=html.escape(info["sha"]),
        short=html.escape(info["sha"][:7]),
        data_date=stamp(info["when"]),
        built=stamp(info["built"]),
        python=html.escape(info["python"]),
        repo=REPO,
        litellm=LITELLM,
    )


def data_script(data):
    text = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return f"window.LLMLEDGER = {text};\n"


def main(source, out_dir, info, data):
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).parent
    (folder / "index.html").write_text(render(load(source), info))
    (folder / "survival.csv").write_text(Path(source).read_text())
    (folder / "data.js").write_text(data_script(data))
    for name in ("app.js", "cost.js", "route.js", "table_protocol.js"):
        shutil.copyfile(here / name, folder / name)
    return folder / "index.html"
