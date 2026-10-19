"""Write tests.yaml for promptfoo: calls to the plug-in's tools, each checked against an answer worked out here
from data.json itself, not by the plug-in's code (standard library only).

    python make_tests.py [path or address of data.json] [how many models, default 12]

Checks, for the most rated text models of the day:
1. estimate_cost prices a model at the cheapest of its listings for those tokens (a listing with both token
   prices 0 is a free tier and does not count);
2. compare_models gives the same cost per task as estimate_cost for the same tokens;
3. price_history lists every listing of the model that data.json lists.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

SOURCE = "https://pouriaetab.github.io/llmledger/data.json"
TEXT_MODES = ("chat", "responses", "completion")
NOT_TEXT = re.compile(r"embed|rerank|flux|diffusion|sdxl|controlnet|dall-e|imagen|whisper|tts")
TOKENS = (2000, 600)


def load(source):
    if re.match(r"https?://", source):
        with urllib.request.urlopen(urllib.request.Request(source, headers={"User-Agent": "llmledger"}), timeout=60) as r:
            return json.loads(r.read())
    return json.loads(Path(source).read_text())


def cheapest(listings, tokens_in, tokens_out):
    costs = [(m["input"] * tokens_in + m["output"] * tokens_out) / 1e6 for m in listings
             if m.get("mode") in TEXT_MODES and not NOT_TEXT.search(m["key"].lower())
             and m.get("input") is not None and m.get("output") is not None and (m["input"] > 0 or m["output"] > 0)]
    return min(costs) if costs else None


def cases(data, count=12):
    groups = {}
    for m in data["models"]:
        groups.setdefault(m["maker"] + " / " + m["name"], []).append(m)
    rated = [row[0] for row in ((data.get("ratings") or {}).get("tasks") or {}).get("overall", [])]
    picked = [g for g in rated if g in groups and cheapest(groups[g], *TOKENS) is not None][:count]
    out = []
    for group in picked:
        cost = cheapest(groups[group], *TOKENS)
        name = group.split(" / ", 1)[1]
        out.append({"description": f"estimate_cost: {name} at its cheapest listing",
                    "vars": {"prompt": json.dumps({"tool": "estimate_cost", "args": {
                        "models": [group], "input_tokens": TOKENS[0], "output_tokens": TOKENS[1]}}),
                             "expected": cost},
                    "assert": [{"type": "javascript", "value": "file://check.js:perCall"}]})
        out.append({"description": f"price_history: every listing of {name}",
                    "vars": {"prompt": json.dumps({"tool": "price_history", "args": {"model": group}}),
                             "expected": len(groups[group])},
                    "assert": [{"type": "javascript", "value": "file://check.js:listingsInTotal"}]})
    for first, second in zip(picked[::2], picked[1::2]):
        costs = [cheapest(groups[g], *TOKENS) for g in (first, second)]
        out.append({"description": f"compare_models: {first} and {second} cost what estimate_cost says",
                    "vars": {"prompt": json.dumps({"tool": "compare_models", "args": {
                        "models": [first, second], "input_tokens": TOKENS[0], "output_tokens": TOKENS[1]}}),
                             "expected": costs},
                    "assert": [{"type": "javascript", "value": "file://check.js:costPerTask"}]})
    return out


def main(argv):
    source = argv[1] if len(argv) > 1 else SOURCE
    count = int(argv[2]) if len(argv) > 2 else 12
    data = load(source)
    tests = cases(data, count)
    path = Path(__file__).with_name("tests.json")
    path.write_text(json.dumps(tests, indent=1) + "\n")
    print(f"{path.name}: {len(tests)} checks on {count} models, data built {data.get('built')}")


if __name__ == "__main__":
    main(sys.argv)
