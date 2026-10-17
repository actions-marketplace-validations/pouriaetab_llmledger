"""The page's own logic, in Python, for the plug-in: the task guess (route.js), prompt cost
(cost.js) and the side-by-side comparison (pick.js). Pure functions; no network, no FastMCP.

The task rules are copied from route.js; tests/test_mcp_logic.py in the repo checks that both
give the same answers. Python reads word boundaries next to accented letters a little more
generously than JavaScript does, so a rare prompt in Spanish, French or German can differ.
"""
import math
import re

# ---------- task guess (route.js) ----------
# task: (strong pattern, its flags, weak pattern, its flags); a strong match counts 2, a weak one 1.
RULES = {
    "webdev": ("\\b(html|css|tailwind|react|next\\.js|nextjs|vue|svelte|landing page|web ?page|website|web app|frontend|front-end)\\b", "i",
        "\\b(navbar|button|layout|responsive|dom|jsx|tsx)\\b", "i"),
    "coding": ("```|\\b(python|javascript|typescript|java|c\\+\\+|c#|golang|rust|kotlin|swift|flutter|php|ruby|bash|powershell|sql|regex|numpy|pandas|pytorch|tensorflow|django|flask|fastapi|node\\.?js|npm|docker\\w*|kubernetes|git|github|api|json|yaml|code|coding|script|function|debug|refactor|compile\\w*|stack ?trace|traceback|exception|bug|algorithm|leetcode|unit test|programm\\w*|linux|ubuntu|terminal|excel formula|vba)\\b|(\\bdef |\\bimport |console\\.log|#include|public static|=>|!=|==|\\w+\\(\\)\\s*[{;:]|[{};]\\s*$|\\bSELECT\\b[\\s\\S]*\\bFROM\\b)|(код|программ|функци|скрипт|代码|程序|函数|编程|コード|プログラム|関数|코드|프로그램|함수|programowa\\w*|\\bkod\\w*|funkcj\\w*|código|programa\\w*|fonction|Programmier\\w*|پایتون|کد)", "im",
        "\\b(variable|loop|array|class|method|library|install\\w*|error|server|database|query|plugin|app|framework|sdk|cpu|gpu|windows|version|command|config\\w*|network|router)\\b", "i"),
    "math": ("\\b(solve|equation|integral|derivative|prove|proof|theorem|lemma|probability|calculus|algebra|geometry|matrix|matrices|eigen\\w*|polynomial|logarithm|factorial|combinatorics|arithmetic)\\b|\\\\(frac|int|sum|sqrt)|\\d\\s*[\\^×÷]\\s*\\d|\\b\\d+\\s*[+\\-*\\/]\\s*\\d+\\s*=", "i",
        "\\b(calculate|compute|how many|how long|percent\\w*|average|mean|median|standard deviation|variance|sum of|formula|area of|volume of|limit|next number|x\\s*=|f\\(x\\))\\b|\\d+\\s*%|(\\d+\\s*,\\s*){3,}|(数学|方程|计算|概率|確率|計算|수학|방정식|matemat\\w*|oblicz\\w*|równani\\w*|вычисл\\w*|уравнени\\w*|задач\\w*)", "i"),
    "creative_writing": ("\\b(story|stories|poem|poetry|lyrics|song|novel|fiction|fanfic\\w*|screenplay|script for a|haiku|limerick|sonnet|fairy tale|roleplay|role-play|role play|role playing)\\b|(小说|故事|诗|歌词|рассказ|стих\\w*|песн\\w*|сказк\\w*|opowiada\\w*|wiersz\\w*|piosenk\\w*|histoire|poème|chanson|Geschichte|Gedicht|cuento|poema|canción|小説|物語|이야기|소설)", "i",
        "\\b(character|plot|chapter|scene|scenario|imagine|creative|narrat\\w*|villain|hero|speech|toast|slogan)\\b", "i"),
    "legal": ("\\b(lawsuit|attorney|lawyer|contract|legal|statute|court|plaintiff|defendant|gdpr|liabilit\\w*|clause)\\b", "i",
        "\\b(law|rights|regulation|compliance|tenant|landlord)\\b", "i"),
    "medicine": ("\\b(symptom\\w*|diagnos\\w*|medication|dosage|clinical|patient|disease|treatment|doctor|surgery|pregnan\\w*|vaccine)\\b", "i",
        "\\b(health|pain|medical|drug|therapy|blood|nutrition)\\b", "i"),
    "business": ("\\b(marketing|revenue|profit|startup|business plan|investor|pricing strategy|sales funnel|kpi|roi|invoice|accounting|financial statement|stock market|valuation)\\b", "i",
        "\\b(business|customer|budget|finance|company|market|sales|brand|product)\\b", "i"),
    "science": ("\\b(physics|chemistry|biology|molecule|quantum|thermodynamic\\w*|photosynthesis|dna|genome|neuron|astronom\\w*|hypothesis|experiment)\\b", "i",
        "\\b(atom|energy|cell|evolution|climate|species|planet|element)\\b", "i"),
    "writing": ("\\b(essay|proofread|rewrite|rephrase|paraphrase|summari[sz]e|grammar|cover letter|resume|email to|draft an? (email|letter))\\b", "i",
        "\\b(email|letter|article|blog|tone|wording|sentence|paragraph)\\b", "i"),
    "media": ("\\b(movie|film|tv show|series|anime|manga|album|football|soccer|basketball|nba|nfl|olympic\\w*|video game|celebrity)\\b", "i",
        "\\b(music|sport\\w*|game|actor|singer|team|season|episode)\\b", "i")
}
LABELS = {
    "overall": "Everything (overall)",
    "coding": "Coding",
    "math": "Math",
    "creative_writing": "Creative writing",
    "instruction_following": "Following detailed instructions",
    "hard_prompts": "Hard prompts",
    "longer_query": "Long prompts",
    "multi_turn": "Long conversations",
    "expert": "Expert questions",
    "business": "Business and finance",
    "legal": "Legal and government",
    "medicine": "Medicine and health",
    "science": "Science",
    "software": "Software and IT",
    "writing": "Writing and literature",
    "media": "Entertainment, sports and media",
    "chinese": "In Chinese",
    "french": "In French",
    "german": "In German",
    "japanese": "In Japanese",
    "korean": "In Korean",
    "russian": "In Russian",
    "spanish": "In Spanish",
    "vision": "Understanding images",
    "document": "Understanding documents",
    "webdev": "Building websites and apps"
}
ORDER = ["webdev", "coding", "math", "creative_writing", "legal", "medicine", "science", "business", "writing", "media"]
TASKS = list(LABELS)
LANGUAGES = [
    ("japanese", r"[\u3040-\u30ff]"),
    ("korean", r"[\uac00-\ud7af]"),
    ("chinese", r"[\u4e00-\u9fff]"),
    ("russian", r"[\u0400-\u04ff]"),
    ("spanish", r"[ñ¿¡]|\b(el|los|las|que|por|para|una|con|del|es|está|cómo|qué|puedes|necesito)\b"),
    ("french", r"[çœ]|\b(les|des|est|une|pour|dans|avec|qui|pas|je|vous|c'est|n'est|qu'il)\b"),
    ("german", r"ß|\b(der|die|das|und|ist|nicht|mit|ein|eine|ich|sie|auf|für|über|wie|bitte)\b"),
]
SCRIPTS = ("japanese", "korean", "chinese", "russian")
ENGLISH = re.compile(r"\b(the|and|is|are|to|of|you|what|how|with|for|this|that|in)\b", re.I)


def _flags(text):
    return (re.I if "i" in text else 0) | (re.M if "m" in text else 0)


_COMPILED = {task: (re.compile(s, _flags(sf)), re.compile(w, _flags(wf))) for task, (s, sf, w, wf) in RULES.items()}
_LANG = [(name, re.compile(p, 0 if name in SCRIPTS else re.I)) for name, p in LANGUAGES]


def language(text):
    """A language with its own Arena task, or None. Writing systems decide Japanese, Korean,
    Chinese and Russian; Spanish, French and German need 3 or more of their common words,
    and more than English ones."""
    english = len(ENGLISH.findall(text))
    best = None
    for name, pattern in _LANG:
        hits = sum(1 for _ in pattern.finditer(text))
        if name in SCRIPTS:
            if hits >= 5:
                return name
            continue
        if hits >= 3 and hits > english and (best is None or hits > best[1]):
            best = (name, hits)
    return best[0] if best else None


def _score(text, task):
    found, points = [], 0
    for pattern, weight in zip(_COMPILED[task], (2, 1)):
        for m in pattern.finditer(text):
            points += weight
            word = m.group(0).strip().lower()
            if len(found) < 4 and word not in found:
                found.append(word)
    return points, found


def guess_task(text, images=0, pages=0):
    """The Arena task a prompt most likely belongs to: {task, why, language}."""
    text = str(text or "")
    if pages > 0:
        return {"task": "document", "why": ["a PDF is attached"], "language": language(text)}
    if images > 0:
        return {"task": "vision", "why": ["an image is attached"], "language": language(text)}
    best = None
    for task in ORDER:
        points, found = _score(text, task)
        if points >= 2 and (best is None or points > best[1]):
            best = (task, points, found)
    lang = language(text)
    if best:
        return {"task": best[0], "why": best[2], "language": lang}
    if lang:
        return {"task": lang, "why": ["written in " + lang.capitalize()], "language": lang}
    return {"task": "overall", "why": ["no clear task"], "language": lang}


# ---------- prompt cost (cost.js) ----------
CHARS_PER_TOKEN = 4
TEXT_MODES = ("chat", "responses", "completion")
NOT_TEXT = re.compile(r"embed|rerank|flux|diffusion|sdxl|controlnet|dall-e|imagen|whisper|tts")
ANSWERS = {"short": 250, "medium": 800, "long": 2000, "very_long": 6000}


def estimate_tokens(text):
    return math.ceil(len(str(text or "")) / CHARS_PER_TOKEN)


def is_text_model(model):
    return model.get("mode") in TEXT_MODES and not NOT_TEXT.search(str(model.get("key", "")).lower())


def cost_of(model, input_tokens, output_tokens, cached_tokens=0):
    """Dollars for one call: prompt tokens at the input price (the cached part at the cache
    read price when the model lists one), answer tokens at the output price. None if unpriced."""
    if model.get("input") is None or model.get("output") is None:
        return None
    cached = min(max(cached_tokens, 0), input_tokens)
    cache_price = model.get("cache_read")
    if cache_price is None:
        cache_price, cached = model["input"], cached
    return ((input_tokens - cached) * model["input"] + cached * cache_price + output_tokens * model["output"]) / 1e6


# ---------- compare side by side (pick.js) ----------
LEVELS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]
HARD_TASKS = ("coding", "webdev", "math", "hard_prompts", "expert", "software", "science")
DEEP = re.compile(r"\b(architect\w*|design\w*|from scratch|refactor\w*|debug\w*|root cause|prove|proof|optimi[sz]\w*|"
                  r"migrat\w*|security|concurren\w*|race condition|trade-?offs?|specification|multi-?step|end to end|production)\b", re.I)
LIGHT = re.compile(r"\b(summari[sz]e|translate|rewrite|rephrase|proofread|typos?|reformat|format|short|quick(ly)?|one line|"
                   r"tl;?dr|classify|extract)\b", re.I)
SCORE_LEVEL = ["low", "medium", "high", "high", "xhigh", "max"]


def clamp(level, levels):
    """The closest level a model takes: the nearest one below, else the lowest one above."""
    if not levels:
        return None
    if level in levels:
        return level
    at = LEVELS.index(level)
    for i in range(at, -1, -1):
        if LEVELS[i] in levels:
            return LEVELS[i]
    return next((x for x in levels if LEVELS.index(x) > at), levels[0])


def suggest_effort(text, task, levels, prompt_tokens, fallback=""):
    """A suggested effort level: a rule of thumb from the task and the prompt's words and length."""
    if not levels:
        return {"level": None, "why": []}
    text = str(text or "")
    if not text.strip():
        return {"level": fallback if fallback in levels else None, "why": []}
    why, score = [], 1
    if task in HARD_TASKS:
        score += 1
        why.append("a task where thinking helps")
    deep = DEEP.search(text)
    light = None if deep else LIGHT.search(text)
    if deep:
        score += 2
        why.append('it asks for "' + deep.group(0).lower() + '"')
    if light:
        score -= 1
        why.append('it asks for "' + light.group(0).lower() + '"')
    tokens = prompt_tokens or 0
    if tokens > 8000:
        score += 2
        why.append("a very long prompt")
    elif tokens > 2000:
        score += 1
        why.append("a long prompt")
    elif tokens < 40 and not deep:
        score -= 1
        why.append("a short prompt")
    level = SCORE_LEVEL[max(0, min(len(SCORE_LEVEL) - 1, score))]
    return {"level": clamp(level, levels), "why": why}


def plan_multiples(costs):
    """How fast each choice uses a plan compared with the one that uses it least (assumes a
    plan runs down in step with API prices)."""
    known = [c for c in costs if c is not None and c > 0]
    if not known:
        return [None for _ in costs]
    least = min(known)
    return [None if c is None or c <= 0 else c / least for c in costs]


def tied(a, b):
    """The votes cannot tell two ratings apart: their 95% ranges overlap."""
    return a["high"] >= b["low"] and b["high"] >= a["low"]


def best_pick(rows):
    """Among the choices tied with the highest rated, the cheapest; without ratings, the cheapest."""
    priced = [r for r in rows if r.get("cost") is not None]
    if not priced:
        return None
    rated = [r for r in priced if r.get("rating") is not None]
    if not rated:
        return min(priced, key=lambda r: r["cost"])
    top = max(rated, key=lambda r: r["rating"])
    return min((r for r in rated if tied(r, top)), key=lambda r: r["cost"])


def _times(x):
    return (f"{x:.1f}" if x < 10 else f"{x:.0f}") + "×"


def _percent(x):
    return f"{round(100 * x)}%"


def headline(rows, plan=False):
    """One sentence on which to pick, and why (as the page says it)."""
    pick = best_pick(rows)
    if pick is None:
        return ""
    priced = [r for r in rows if r.get("cost") is not None]
    if len(priced) < 2:
        return "Add a model to compare with " + pick["name"] + "."
    rated = [r for r in priced if r.get("rating") is not None]
    top = max(rated, key=lambda r: r["rating"]) if rated else None
    least = min(priced, key=lambda r: r["cost"])
    light = "lightest on your plan" if plan else "cheapest"
    if top is None:
        return pick["name"] + " is the " + light + " here; none of these is rated for this task."
    if pick is top and pick is least:
        return pick["name"] + " is the pick: the highest rated here, and the " + light + "."
    if pick is top:
        return (pick["name"] + " is the pick: the highest rated here. The ones that "
                + ("use less of the plan" if plan else "cost less") + " are rated lower.")
    return (pick["name"] + " is the pick: the votes cannot tell it apart from the highest rated, " + top["name"]
            + ", and it " + ("uses less of the plan" if plan else "costs less") + ".")


def versus(r, pick, plan=False):
    """A short note on one choice against the pick, with the break-even share of answer tokens."""
    if pick is None or r is pick or r.get("cost") is None or not (pick.get("cost") or 0) > 0:
        return ""
    ratio = r["cost"] / pick["cost"]
    name = pick["name"]
    if plan:
        if ratio >= 1.05:
            line = "Uses the plan " + _times(ratio) + " as fast as " + name
        elif ratio <= 0.95:
            line = "Uses " + ("1/" + str(round(1 / ratio)) + " as much" if ratio <= 0.1 else _percent(1 - ratio) + " less") + " of the plan than " + name
        else:
            line = "Uses the plan at about the same rate as " + name
    else:
        if ratio >= 1.05:
            line = "Costs " + _times(ratio) + " as much as " + name
        elif ratio <= 0.95:
            line = "Costs " + ("1/" + str(round(1 / ratio)) + " as much as " if ratio <= 0.1 else _percent(1 - ratio) + " less than ") + name
        else:
            line = "Costs about the same as " + name
    k = r["out"] / pick["out"] if (r.get("out") or 0) > 0 and (pick.get("out") or 0) > 0 else None
    if k is not None and 0.1 < k < 10 and abs(k - 1) >= 0.05:
        if k > 1:
            line += "; it only " + ("uses less" if plan else "costs less") + " if it needs under " + _percent(1 / k) + " of the answer tokens"
        else:
            line += "; it stays " + ("lighter" if plan else "cheaper") + " unless it needs over " + _times(1 / k) + " the answer tokens"
    return line + "."
