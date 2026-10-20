"""An Atom feed of the catalogue's changes, published as site/feed.xml.

One entry a day for the last DAYS days: how many models were added, repriced, given a
retirement date or removed, then one line per model with the LiteLLM commits behind it. A feed reader, a Slack channel or a script can follow it; nothing to install.
"""
import html
from datetime import date, timedelta

DAYS = 14
MAX_LINES = 60
PAGE = "https://pouriaetab.github.io/llmledger/"
LITELLM = "https://github.com/BerriAI/litellm/commit/"
KINDS = (("price", "price change", "price changes"),
         ("deprecation", "retirement date", "retirement dates"),
         ("added", "model added", "models added"),
         ("removed", "model removed", "models removed"))
FIELDS = {"input_cost_per_token": "input", "output_cost_per_token": "output",
          "cache_read_input_token_cost": "cache read", "cache_creation_input_token_cost": "cache write"}


def per_million(value):
    if value is None:
        return "none"
    v = float(value) * 1e6
    return f"${v:,.2f}" if v >= 0.1 else f"${v:,.4f}"


def by_day(machine):
    """{day: [(key, event), ...]} for the last DAYS days of the catalogue's events."""
    built = date.fromisoformat(machine["built"][:10])
    cut = (built - timedelta(days=DAYS)).isoformat()
    days = {}
    for key, events in machine["events"].items():
        for event in events:
            if event[0] >= cut and event[1] in {k for k, _, _ in KINDS}:
                days.setdefault(event[0], []).append((key, event))
    return days


def describe(key, events, sources):
    """One line for a model's changes of one kind on one day, with the LiteLLM commits behind them."""
    kind = events[0][1]
    shas = []
    for e in events:
        sha = sources[e[6]] if isinstance(e[6], int) and 0 <= e[6] < len(sources) else ""
        if sha and sha not in shas:
            shas.append(sha)
    links = " ".join(f'<a href="{LITELLM}{sha}">{html.escape(sha[:7])}</a>' for sha in shas)
    name = html.escape(key)
    if kind == "price":
        bits = []
        for day, kind, field, old, new, flag, source in events:
            what = FIELDS.get(field, field.replace("_cost_per_token", "").replace("_", " "))
            bits.append(f"{html.escape(what)} {per_million(old)} &rarr; {per_million(new)}" + (f" ({html.escape(flag)})" if flag else ""))
        return f"<li>{name}: {', '.join(bits)} per 1M {links}</li>"
    if kind == "deprecation":
        return f"<li>{name}: retirement date {html.escape(str(events[0][4]))} {links}</li>"
    return f"<li>{name} {links}</li>"


def entry(day, rows, sources):
    groups = {}
    for key, event in rows:
        groups.setdefault((event[1], key), []).append(event)
    counts = {kind: sum(1 for k, _ in groups if k == kind) for kind, _, _ in KINDS}
    parts = [f"{counts[k]} {one if counts[k] == 1 else many}" for k, one, many in KINDS if counts[k]]
    when = date.fromisoformat(day)
    title = f"{when.day} {when:%B %Y}: " + ", ".join(parts)
    body = []
    for kind, one, many in KINDS:
        chosen = sorted(((key, events) for (k, key), events in groups.items() if k == kind), key=lambda r: r[0])
        if not chosen:
            continue
        body.append(f"<h3>{html.escape(many.capitalize())} ({len(chosen)})</h3><ul>")
        body.extend(describe(key, events, sources) for key, events in chosen[:MAX_LINES])
        if len(chosen) > MAX_LINES:
            body.append(f"<li>and {len(chosen) - MAX_LINES} more on the page</li>")
        body.append("</ul>")
    content = html.escape("".join(body))
    return (f"<entry><title>{html.escape(title)}</title>"
            f'<link href="{PAGE}#week"/><id>{PAGE}feed/{day}</id>'
            f"<updated>{day}T00:00:00Z</updated>"
            f'<content type="html">{content}</content></entry>')


def build(machine):
    """The feed as text, newest day first."""
    sources = machine.get("sources") or []
    days = by_day(machine)
    entries = "".join(entry(day, days[day], sources) for day in sorted(days, reverse=True))
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<title>llmledger: price changes and retirements</title>"
            "<subtitle>Every change to LiteLLM's model price catalogue, one entry a day. Not financial or procurement advice.</subtitle>"
            f'<link href="{PAGE}"/><link rel="self" href="{PAGE}feed.xml"/>'
            f"<id>{PAGE}feed.xml</id><updated>{machine['built']}</updated>"
            "<author><name>llmledger</name></author>"
            f"{entries}</feed>\n")


def write(path, machine):
    with open(path, "w") as f:
        f.write(build(machine))
