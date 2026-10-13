import re

MAKERS = {
    "anthropic": ("claude",),
    "openai": ("gpt", "o1", "o3", "o4", "chatgpt", "text-embedding", "dall-e",
               "whisper", "tts", "davinci", "babbage", "codex", "sora",
               "omni-moderation", "text-moderation", "computer-use"),
    "google": ("gemini", "gemma", "imagen", "veo", "palm", "chat-bison",
               "text-bison", "code-bison", "codechat-bison", "textembedding"),
    "meta": ("llama", "codellama", "muse-spark"),
    "mistral": ("mistral", "mixtral", "codestral", "pixtral", "ministral",
                "magistral", "devstral", "open-mistral", "open-mixtral",
                "voxtral"),
    "cohere": ("command", "embed-english", "embed-multilingual", "rerank",
               "c4ai"),
    "deepseek": ("deepseek",),
    "alibaba": ("qwen", "qwq", "qvq"),
    "xai": ("grok",),
    "moonshot": ("kimi", "moonshot"),
    "zhipu": ("glm", "chatglm"),
    "amazon": ("nova", "titan"),
    "ai21": ("jamba", "j2"),
    "microsoft": ("phi", "wizardlm"),
    "minimax": ("minimax", "abab"),
    "nvidia": ("nemotron", "llama-nemotron"),
    "xiaomi": ("mimo",),
}
VENDORS = {"anthropic", "openai", "google", "meta", "meta-llama", "mistral",
           "mistralai", "cohere", "deepseek", "deepseek-ai", "qwen", "alibaba",
           "xai", "x-ai", "moonshotai", "zhipuai", "amazon", "ai21",
           "microsoft", "minimax", "nvidia", "fal-ai", "bytedance"}
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


def _clean(name):
    dots = name.split(".")
    while len(dots) > 1 and dots[0] in ROUTING:
        dots = dots[1:]
    if len(dots) > 1 and dots[0] in VENDORS:
        dots = dots[1:]
    name = ".".join(dots)
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


def canonical(key):
    segments = _segments(key)
    for i, segment in enumerate(segments):
        cleaned = _clean(segment)
        maker = _maker(cleaned)
        if maker:
            return maker, "/".join([cleaned] + segments[i + 1:])
    return "other", _clean(segments[-1])
