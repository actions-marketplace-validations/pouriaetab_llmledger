import re

MAKERS = {
    "anthropic": ("claude",),
    "openai": ("gpt", "o1", "o3", "o4", "chatgpt", "text-embedding", "dall-e",
               "whisper", "tts", "davinci", "babbage", "codex", "sora",
               "omni-moderation", "text-moderation", "computer-use"),
    "google": ("gemini", "gemma", "imagen", "veo", "palm", "chat-bison",
               "text-bison", "code-bison", "codechat-bison", "textembedding",
               "lyria", "nano-banana", "deep-research"),
    "meta": ("llama", "codellama", "code-llama", "muse-spark"),
    "mistral": ("mistral", "mixtral", "codestral", "pixtral", "ministral",
                "magistral", "devstral", "open-mistral", "open-mixtral",
                "voxtral"),
    "cohere": ("command", "embed-english", "embed-multilingual", "rerank",
               "c4ai", "embed-v", "parse-v"),
    "deepseek": ("deepseek",),
    "alibaba": ("qwen", "qwq", "qvq", "wan2", "wan3"),
    "xai": ("grok",),
    "moonshot": ("kimi", "moonshot"),
    "zhipu": ("glm", "chatglm", "cogview", "cogvideo"),
    "amazon": ("nova", "titan"),
    "ai21": ("jamba", "j2"),
    "microsoft": ("phi", "wizardlm", "mai-"),
    "minimax": ("minimax", "abab"),
    "nvidia": ("nemotron", "llama-nemotron"),
    "xiaomi": ("mimo",),
    "stability": ("stable-diffusion", "sd3", "stable-image", "stable-video"),
    "bytedance": ("doubao", "seed-", "seed1", "seed2", "seedance", "seedream"),
    "baidu": ("ernie",),
    "tencent": ("hunyuan", "hy3", "hy4"),
    "stepfun": ("step-",),
    "black-forest-labs": ("flux",),
    "ibm": ("granite",),
    "perplexity": ("sonar", "pplx"),
    "voyage": ("voyage", "rerank-"),
    "nous": ("hermes", "nous-"),
    "01-ai": ("yi-",),
    "writer": ("palmyra",),
    "reflection": ("beam",),
    "meituan": ("longcat",),
    "inception": ("mercury",),
    "snowflake": ("arctic",),
    "databricks": ("dbrx",),
    "twelvelabs": ("marengo", "pegasus"),
}
# A vendor segment or prefix that names the maker even when the model's own
# name does not (bedrock's deepseek.v3.2, gradient_ai/openai-gpt-4o).
VENDOR_MAKER = {
    "anthropic": "anthropic", "openai": "openai", "google": "google",
    "meta": "meta", "meta-llama": "meta", "mistral": "mistral",
    "mistralai": "mistral", "cohere": "cohere", "deepseek": "deepseek",
    "deepseek-ai": "deepseek", "qwen": "alibaba", "alibaba": "alibaba",
    "xai": "xai", "x-ai": "xai", "moonshotai": "moonshot",
    "moonshot": "moonshot", "zhipuai": "zhipu", "zai": "zhipu",
    "zai-org": "zhipu", "amazon": "amazon", "ai21": "ai21",
    "microsoft": "microsoft", "minimax": "minimax", "nvidia": "nvidia",
    "bytedance": "bytedance", "stability": "stability",
    "stabilityai": "stability", "tencent": "tencent", "baidu": "baidu",
    "ibm": "ibm", "ibm-granite": "ibm", "perplexity": "perplexity",
    "nousresearch": "nous", "voyage": "voyage", "reflection": "reflection",
    "black-forest-labs": "black-forest-labs", "writer": "writer",
    "xiaomi": "xiaomi", "xiaomi_mimo": "xiaomi", "stepfun": "stepfun",
    "stepfun-ai": "stepfun", "01-ai": "01-ai", "twelvelabs": "twelvelabs",
    "databricks": "databricks", "snowflake": "snowflake",
}
VENDORS = set(VENDOR_MAKER) | {"fal-ai", "fw", "accounts", "fireworks", "models"}
# Host prefixes glued to a name with a dash or a colon, not the maker.
ALIASES = ("ft:", "fw-", "coding-", "cc-", "databricks-")
ROUTING = {"invoke", "converse", "high", "medium", "low", "standard", "hd",
           "global", "global-standard", "eu", "us", "apac", "jp", "au", "ca",
           "us-gov", "ap", "data-zone", "datazone"}
ENDPOINTS = {"edit", "text-to-image", "image-to-image", "text-to-video",
             "image-to-video", "reference-to-video", "generate", "inpaint",
             "upscale"}
SKIP = re.compile(r"^(\d+-x-\d+|\d+-month-commitment|[a-z]{2}(-[a-z]+)+-\d+)$")
BEDROCK = re.compile(r"(-\d{8})?-v\d+:0$")
DATE = re.compile(r"[-_@](20\d{2}-?\d{2}-?\d{2})(?=$|[-_:])")
MONTH_DAY = re.compile(r"-(0[1-9]|1[0-2])[0-3]\d$")
DIGITS = re.compile(r"(?<=\d)[-_p](?=\d(?![\d.bkm]))")
LLAMA = re.compile(r"^llama(?=\d)")


def _segments(key):
    parts = key.lower().split("/")
    if len(parts) > 1:
        parts = parts[1:]
    kept = [p for p in parts
            if p not in VENDORS and p not in ROUTING and not SKIP.match(p)]
    while len(kept) > 1 and kept[-1] in ENDPOINTS:
        kept.pop()
    return kept or parts[-1:]


def _vendor_hint(key):
    """The maker named by a vendor segment or prefix of the key, if any."""
    for part in key.lower().split("/"):
        if part in VENDOR_MAKER:
            return VENDOR_MAKER[part]
        head = re.split(r"[-.:]", part, maxsplit=1)[0]
        if head in VENDOR_MAKER and head != part:
            return VENDOR_MAKER[head]
    return None


def _clean(name):
    for alias in ALIASES:
        name = name.removeprefix(alias)
    dots = name.split(".")
    while len(dots) > 1 and dots[0] in ROUTING:
        dots = dots[1:]
    if len(dots) > 1 and dots[0] in VENDORS:
        dots = dots[1:]
    name = ".".join(dots)
    name = _unprefix(name)
    name = name.replace(":latest", "").removesuffix("-latest").removesuffix("@default")
    name = BEDROCK.sub("", name)
    name = DATE.sub("", name)
    name = MONTH_DAY.sub("", name)
    name = LLAMA.sub("llama-", name)
    return DIGITS.sub(".", name)


def _maker(name):
    for maker, prefixes in MAKERS.items():
        if name.startswith(prefixes):
            return maker
    return None


def _unprefix(name):
    """Drop a vendor glued to the front of a name (databricks-claude-opus-4,
    openai-gpt-4o, meta-llama-3-70b) only when what is left names a maker;
    deepseek-v4-flash and mistral-large keep their maker's name."""
    if _maker(name):
        return name
    for vendor in sorted(VENDOR_MAKER, key=len, reverse=True):
        rest = name[len(vendor) + 1:]
        if name.startswith(vendor + "-") and rest and _maker(rest):
            return rest
    return name


def canonical(key):
    segments = _segments(key)
    for i, segment in enumerate(segments):
        cleaned = _clean(segment)
        maker = _maker(cleaned)
        if maker:
            return maker, "/".join([cleaned] + segments[i + 1:])
    return _vendor_hint(key) or "other", _clean(segments[-1])
