"""Quality ratings from the Arena leaderboard, matched to the catalogue.

Arena (lmarena-ai) publishes its leaderboard as a dataset on Hugging Face under
CC BY 4.0. The pipeline reads the latest ratings once a day. If Arena cannot be
reached, the page is built without them and nothing else is affected.
"""
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from llmledger.names import canonical

DATASET = "lmarena-ai/leaderboard-dataset"
SOURCE = "https://huggingface.co/datasets/" + DATASET
ROWS = ("https://datasets-server.huggingface.co/rows?dataset=" + DATASET +
        "&config={config}&split=latest&offset={offset}&length=100")
PAGE = 100

# (id, label, Arena table, Arena category)
TEXT = "text_style_control"
TASKS = [
    ("overall", "Everything (overall)", TEXT, "overall"),
    ("coding", "Coding", TEXT, "coding"),
    ("math", "Math", TEXT, "math"),
    ("creative_writing", "Creative writing", TEXT, "creative_writing"),
    ("instruction_following", "Following detailed instructions", TEXT, "instruction_following"),
    ("hard_prompts", "Hard prompts", TEXT, "hard_prompts"),
    ("longer_query", "Long prompts", TEXT, "longer_query"),
    ("multi_turn", "Long conversations", TEXT, "multi_turn"),
    ("expert", "Expert questions", TEXT, "expert"),
    ("business", "Business and finance", TEXT,
     "industry_business_and_management_and_financial_operations"),
    ("legal", "Legal and government", TEXT, "industry_legal_and_government"),
    ("medicine", "Medicine and health", TEXT, "industry_medicine_and_healthcare"),
    ("science", "Science", TEXT, "industry_life_and_physical_and_social_science"),
    ("software", "Software and IT", TEXT, "industry_software_and_it_services"),
    ("writing", "Writing and literature", TEXT,
     "industry_writing_and_literature_and_language"),
    ("media", "Entertainment, sports and media", TEXT,
     "industry_entertainment_and_sports_and_media"),
    ("chinese", "In Chinese", TEXT, "chinese"),
    ("french", "In French", TEXT, "french"),
    ("german", "In German", TEXT, "german"),
    ("japanese", "In Japanese", TEXT, "japanese"),
    ("korean", "In Korean", TEXT, "korean"),
    ("russian", "In Russian", TEXT, "russian"),
    ("spanish", "In Spanish", TEXT, "spanish"),
    ("vision", "Understanding images", "vision_style_control", "overall"),
    ("document", "Understanding documents", "document_style_control", "overall"),
    ("webdev", "Building websites and apps", "webdev", "overall"),
]
CONFIGS = sorted({config for _, _, config, _ in TASKS})

# Arena lists one model several times by reasoning effort ("-high", "(xHigh)")
# or with a date or preview tag. These come off one at a time, longest name
# first, so "qwen3.8-max" matches before "qwen3.8" is tried.
SUFFIX = re.compile(
    r"-(minimal|low|medium|high|xhigh|max|thinking|reasoning|non-reasoning|"
    r"nothinking|no-thinking|preview|exp|latest|beta\d*|nvfp4|fp8|fp4|\d+k|"
    r"20\d{6}|\d{4}|\d{3})$")


def _get(url, tries=4):
    request = urllib.request.Request(url, headers={"User-Agent": "llmledger"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)


def fetch_table(config):
    first = _get(ROWS.format(config=config, offset=0))
    rows = [item["row"] for item in first["rows"]]
    offsets = range(PAGE, first["num_rows_total"], PAGE)
    with ThreadPoolExecutor(8) as pool:
        pages = pool.map(lambda o: _get(ROWS.format(config=config, offset=o)), offsets)
        for page in pages:
            rows.extend(item["row"] for item in page["rows"])
    return rows


def fetch():
    try:
        return {config: fetch_table(config) for config in CONFIGS}
    except Exception as error:
        print("Arena ratings skipped:", error)
        return None


def candidates(arena_name):
    """Names to try in the catalogue, longest first."""
    name = re.sub(r"\s*\(.*?\)\s*", "", arena_name).strip().lower()
    name = re.sub(r"\s+", "-", name)
    seen = []
    while True:
        seen.append(canonical(name)[1])
        shorter = SUFFIX.sub("", name)
        if shorter == name:
            return list(dict.fromkeys(seen))
        name = shorter


def match(arena_name, organization, groups):
    """The catalogue group ("maker / name") for an Arena model, or None.

    groups maps a grouped name to the makers that list it.
    """
    for name in candidates(arena_name):
        makers = groups.get(name)
        if makers:
            maker = organization if organization in makers else sorted(makers)[0]
            return maker + " / " + name
    return None


def build(tables, records):
    """Ratings per task, kept only for models the catalogue can price.

    records are catalog.model_records rows: [key, maker, name, ...].
    Each task row: [group, arena name, rating, low, high, votes, arena rank].
    """
    groups = {}
    for record in records:
        groups.setdefault(record[2], set()).add(record[1])
    found = {}
    tasks = {}
    names = set()
    dates = set()
    for task, _, config, category in TASKS:
        best = {}
        for row in tables.get(config, []):
            if row["category"] != category:
                continue
            names.add(row["model_name"])
            dates.add(row["leaderboard_publish_date"])
            if row["model_name"] not in found:
                found[row["model_name"]] = match(
                    row["model_name"], row.get("organization", ""), groups)
            group = found[row["model_name"]]
            if group is None:
                continue
            kept = best.get(group)
            if kept is None or row["rating"] > kept[2]:
                best[group] = [group, row["model_name"], round(row["rating"], 1),
                               round(row["rating_lower"], 1),
                               round(row["rating_upper"], 1),
                               int(row["vote_count"]), int(row["rank"])]
        tasks[task] = sorted(best.values(), key=lambda r: -r[2])
    return {
        "source": SOURCE,
        "date": max(dates) if dates else "",
        "tasks": tasks,
        "labels": [[task, label] for task, label, _, _ in TASKS],
        "matched": sum(1 for name in names if found.get(name)),
        "total": len(names),
    }
