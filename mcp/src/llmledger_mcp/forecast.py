"""The whole-job quote from a promptfoo sample run (standard library only).

Run a random sample of a job's tests first (promptfoo eval --filter-sample 20 --filter-sample-seed 7 -o
sample.json), then give the file and the size of the whole job. This module reads the sample: for each model
(and prompt, when the sample tried more than one) how many results were checked and how many passed, how many
failed to run, the tokens each call used and how long it took. tools.forecast_job adds the prices.

How often a model was right is the share of checked results that passed, with a Wilson 95% range: it holds
for small samples and never leaves 0 to 100% (18 of 20 gives 70% to 97%; 20 of 20 gives 84% to 100%).
"""
import math

from llmledger_mcp import speed

Z = 1.959964                    # the normal quantile for a 95% range
AT_ONCE = 4                     # promptfoo eval runs 4 calls at once unless -j says otherwise
# promptfoo's first part of a provider id, and the LiteLLM hosts that sell the same model there
HOSTS = {
    "anthropic": ("anthropic",), "openai": ("openai",), "azure": ("azure",), "azureopenai": ("azure",),
    "bedrock": ("bedrock",), "vertex": ("vertex_ai",), "google": ("gemini",), "mistral": ("mistral",),
    "groq": ("groq",), "deepseek": ("deepseek",), "xai": ("xai",), "togetherai": ("together_ai",),
    "fireworks": ("fireworks_ai",), "cohere": ("cohere",), "perplexity": ("perplexity",),
    "cerebras": ("cerebras",), "deepinfra": ("deepinfra",), "hyperbolic": ("hyperbolic",),
    "sambanova": ("sambanova",), "novita": ("novita",), "nscale": ("nscale",), "watsonx": ("watsonx",),
    "cloudflare-ai": ("cloudflare",), "databricks": ("databricks",), "openrouter": ("openrouter",),
    "vercel": ("vercel_ai_gateway",),
}


class ForecastError(ValueError):
    """A sample or a request that cannot be used; the message says why."""


def wilson(right, n):
    """The Wilson 95% range for right out of n, or None for n = 0."""
    if n <= 0:
        return None
    p = right / n
    scale = 1 + Z * Z / n
    centre = (p + Z * Z / (2 * n)) / scale
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / scale
    return max(0.0, centre - half), min(1.0, centre + half)


def overlap(a, b):
    """The sample cannot tell two shares apart: their Wilson ranges overlap."""
    return a[1] >= b[0] and b[1] >= a[0]


def hosts_of(provider_id):
    """The LiteLLM hosts a promptfoo provider is billed on (Claude Code: Anthropic's own prices), or () when
    unknown (a local model, a script)."""
    return HOSTS.get(provider_id.split(":", 1)[0].lower(), ())


def checked(result):
    """The result was graded: its test has checks (asserts)."""
    grading = result.get("gradingResult") or {}
    return bool(grading.get("componentResults")) or bool((result.get("testCase") or {}).get("assert"))


def read(results_path, way=None, thinking=False, resolve=None):
    """The sample, by model: {"rows": [...], "items": tests in the sample, "results", "at_once", "seconds",
    "eval"}. Each row is one model (and prompt) with its results, checks, errors and timed calls."""
    try:
        report, results, eval_id = speed.read_promptfoo(results_path)
    except speed.SpeedError as error:
        raise ForecastError(str(error)) from None
    if not results:
        raise ForecastError("The promptfoo results file has no results.")
    table = report["results"]
    labels = [p.get("label") or p.get("raw") or "" for p in table.get("prompts") or []]
    # promptfoo numbers each prompt and provider pair, so a provider tried more than one prompt only when it has
    # results under more than one number
    used = {}
    for result in results:
        used.setdefault(speed.provider_of(result), set()).add(result.get("promptIdx", 0))
    options = {**((report.get("config") or {}).get("evaluateOptions") or {}), **(report.get("runtimeOptions") or {})}
    at = table.get("timestamp") or ""
    rows = {}
    for index, result in enumerate(results):
        provider_id, _ = speed.provider_of(result)
        model = speed.model_of(result, resolve)
        prompt = result.get("promptIdx", 0) if len(used[speed.provider_of(result)]) > 1 else None
        row = rows.get((model, provider_id, prompt))
        if row is None:
            row = rows[(model, provider_id, prompt)] = {
                "model": model, "provider": provider_id, "way": way or speed.way_of(provider_id),
                "prompt": (labels[prompt] if prompt is not None and prompt < len(labels) else None),
                "results": 0, "tests": set(), "errors": 0, "checked": 0, "right": 0, "cached": 0,
                "calls": [], "promptfoo_cost": None, "costed": 0, "thinking": bool(thinking)}
        row["results"] += 1
        row["tests"].add(result.get("testIdx", index))
        if speed.failed(result):
            row["errors"] += 1
        elif checked(result):
            row["checked"] += 1
            row["right"] += bool(result.get("success"))
        cost = result.get("cost")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            row["promptfoo_cost"] = (row["promptfoo_cost"] or 0.0) + cost
            row["costed"] += 1
        reason = speed.skip_reason(result)
        if reason == "cached":
            row["cached"] += 1
        if reason is None:
            run = speed.as_run(result, f"promptfoo:{eval_id}:{index}", at, row["way"], thinking, resolve)
            row["calls"].append({**run, **speed.usage_of(result)})
            row["thinking"] = row["thinking"] or run["thinking"]
    tests = {r.get("testIdx", i) for i, r in enumerate(results)}
    return {"rows": list(rows.values()), "items": len(tests), "results": len(results), "eval": eval_id,
            "at_once": int(options.get("maxConcurrency") or AT_ONCE),
            "seconds": ((table.get("stats") or {}).get("durationMs") or 0) / 1000}


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def tokens(row):
    """The average tokens of a timed call in the row, or None when the sample timed none."""
    calls = row["calls"]
    if not calls:
        return None
    return {k: round(mean(c[k] for c in calls)) for k in ("input", "output", "cache_read", "cache_write",
                                                           "thinking_tokens")}


def runs_for(row, logged):
    """The runs a row's time is learned from, and how many of them are logged runs: the user's logged runs of the
    same model and way (not the sample's own calls logged earlier), then the sample's timed calls, the newest 50."""
    own = {c["source"] for c in row["calls"]}
    earlier = [r for r in logged if r.get("model") == row["model"] and r.get("way") == row["way"]
               and bool(r.get("thinking")) == row["thinking"] and r.get("source") not in own]
    runs = (earlier + row["calls"])[-speed.RECENT:]
    return runs, len(runs) - min(len(row["calls"]), len(runs))


def right(row):
    if not row["checked"]:
        return None
    low, high = wilson(row["right"], row["checked"])
    return {"right": row["right"], "of": row["checked"], "share": round(row["right"] / row["checked"], 4),
            "low": round(low, 4), "high": round(high, 4)}


def dollars(x):
    if x is None:
        return None
    if x >= 1:
        return f"${x:,.2f}"
    if x <= 0:
        return "$0"
    text = f"{x:.{max(2, 1 - math.floor(math.log10(x)))}f}"                 # two significant digits
    while text.endswith("0") and len(text.split(".")[1]) > 2:
        text = text[:-1]
    return "$" + text


def points(x):
    return f"{round(100 * abs(x))} point" + ("" if round(100 * abs(x)) == 1 else "s")


def versus(row, pick):
    """One line on a model against the pick: what it saves or costs more an item, and the break-even cost of a
    wrong answer (the cost difference per item over the difference in how often each is right)."""
    if pick is None or row is pick:
        return None
    name = pick["name"]
    if row.get("per_item") is None:
        if row["right"] is None or pick["right"] is None:
            return None
        gap = row["right"]["share"] - pick["right"]["share"]
        if abs(gap) < 1e-9:
            return f"No token price to compare with {name}; it was right as often."
        more = "more" if gap > 0 else "less"
        return f"No token price to compare with {name}; it was right {points(gap)} {more} often."
    cost = row["per_item"] - pick["per_item"]
    a, b = row["right"], pick["right"]
    if a is None or b is None:
        if abs(cost) < 1e-12:
            return f"Costs the same as {name}; the sample has no checks to tell which is right more often."
        return (f"Costs {dollars(abs(cost))} {'more' if cost > 0 else 'less'} an item than {name}; the sample has no "
                "checks to tell which is right more often.")
    gap = a["share"] - b["share"]
    tied = overlap((a["low"], a["high"]), (b["low"], b["high"]))
    unsure = " The sample cannot tell the two apart yet." if tied else ""
    if abs(gap) < 1e-9:
        if abs(cost) < 1e-12:
            return f"Costs the same as {name} and was right as often."
        return f"Right as often as {name} and costs {dollars(abs(cost))} {'more' if cost > 0 else 'less'} an item."
    if gap > 0 and cost > 0:
        return (f"Right {points(gap)} more often than {name} and costs {dollars(cost)} more an item: worth it if a "
                f"wrong answer costs you more than {dollars(cost / gap)} to catch and fix." + unsure)
    if gap < 0 and cost < 0:
        return (f"Saves {dollars(-cost)} an item against {name} but was right {points(gap)} less often: the better "
                f"buy only if a wrong answer costs you less than {dollars(cost / gap)}." + unsure)
    if gap < 0:
        more = "as much" if abs(cost) < 1e-12 else f"{dollars(cost)} more an item"
        return f"Costs {more} and was right {points(gap)} less often than {name}." + unsure
    return f"Costs {dollars(-cost)} less an item than {name} and was right {points(gap)} more often." + unsure


def best(rows, wrong_answer_cost=None):
    """The pick. With the cost of a wrong answer: the lowest cost an item counting wrong answers at that cost.
    Without it: among the models the sample cannot tell apart from the most often right, the cheapest; with no
    checks in the sample, the cheapest."""
    priced = [r for r in rows if r.get("per_item") is not None]
    if not priced:
        return None
    graded = [r for r in priced if r["right"] is not None]
    if not graded:
        return min(priced, key=lambda r: r["per_item"])
    if wrong_answer_cost is not None:
        return min(graded, key=lambda r: (r["per_item"] + (1 - r["right"]["share"]) * wrong_answer_cost,
                                          -r["right"]["share"]))
    top = max(graded, key=lambda r: (r["right"]["share"], r["right"]["of"]))
    span = (top["right"]["low"], top["right"]["high"])
    return min((r for r in graded if overlap((r["right"]["low"], r["right"]["high"]), span)),
               key=lambda r: (r["per_item"], -r["right"]["share"]))
