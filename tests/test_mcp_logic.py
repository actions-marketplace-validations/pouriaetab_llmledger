"""The plug-in (mcp/) repeats the page's logic in Python. These tests check both give the same answers."""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")
spec = importlib.util.spec_from_file_location("logic", ROOT / "mcp" / "src" / "llmledger_mcp" / "logic.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

PROMPTS = [
    "Fix this Python function so the tests pass: def add(a, b): return a - b",
    "Write a short poem about the sea",
    "Build a landing page with Tailwind and React for my bakery",
    "Solve the equation 3x + 5 = 20 and explain each step",
    "What is the capital of France?",
    "Summarize this article in three bullet points",
    "Draft an email to my landlord about the broken heater",
    "My patient has symptoms of fever and cough; what diagnosis should I consider?",
    "Review this contract clause for liability issues",
    "Explain photosynthesis for a biology class",
    "Write a business plan for a coffee startup with revenue projections",
    "Who won the NBA finals last season?",
    "Привет, как дела? Расскажи мне о погоде сегодня в Москве пожалуйста",
    "请帮我写一个快速排序的函数，并解释它的时间复杂度是多少",
    "こんにちは、今日の天気について教えてください。よろしくお願いします",
    "안녕하세요, 오늘 날씨에 대해 알려주세요. 감사합니다 정말로",
    "Hola, ¿cómo estás? Necesito ayuda con mi tarea de historia para el lunes",
    "Bonjour, je voudrais savoir pour quoi les chats dorment autant dans la journée",
    "Hallo, ich brauche bitte Hilfe mit der Steuererklärung und das ist nicht einfach",
    "SELECT name FROM users WHERE id = 3; why is this slow?",
    "```js\nconsole.log('hi')\n```",
    "Design the architecture for a new web app from scratch, then debug the slow queries",
    "Translate this sentence into English",
    "Tell me a story about a dragon and a knight",
    "Calculate the average of 3, 5, 9, 12 and 20",
    "",
]


def node(expression):
    script = (f"const r = require({json.dumps(str(ROOT / 'src/llmledger/route.js'))}); "
              f"const p = require({json.dumps(str(ROOT / 'src/llmledger/pick.js'))}); "
              f"console.log(JSON.stringify({expression}));")
    return json.loads(subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(NODE is None, reason="needs node to run route.js and pick.js")
def test_req_s32_plugin_guesses_the_same_task_as_the_page():
    page = node(f"{json.dumps(PROMPTS)}.map(t => r.guessTask(t, {{}}))")
    plugin = [L.guess_task(t) for t in PROMPTS]
    assert [(g["task"], g["language"]) for g in plugin] == [(g["task"], g["language"]) for g in page]
    assert [g["why"] for g in plugin] == [g["why"] for g in page]


@pytest.mark.skipif(NODE is None, reason="needs node to run pick.js")
def test_req_s32_plugin_compares_the_same_way_as_the_page():
    levels = ["low", "medium", "high", "xhigh", "max"]
    cases = [(t, task, n) for t in PROMPTS[:12] for task, n in (("coding", 30), ("overall", 900), ("webdev", 9000))]
    page = node(f"{json.dumps(cases)}.map(([t, k, n]) => p.suggestEffort(t, k, {json.dumps(levels)}, n))")
    assert [L.suggest_effort(t, k, levels, n) for t, k, n in cases] == page
    rows = [{"name": "opus", "rating": 1548, "low": 1534, "high": 1561, "cost": 0.0172, "out": 20},
            {"name": "fable", "rating": 1550, "low": 1545, "high": 1556, "cost": 0.043, "out": 50},
            {"name": "sonnet", "rating": 1520, "low": 1510, "high": 1530, "cost": 0.0086, "out": 10},
            {"name": "tiny", "rating": None, "low": None, "high": None, "cost": 0.00001, "out": 0.1}]
    for plan in (False, True):
        page = node(f"(() => {{ const r = {json.dumps(rows)}; const k = p.bestPick(r); "
                    f"return [k.name, p.headline(r, {{plan: {json.dumps(plan)}}}), r.map(x => p.versus(x, k, {json.dumps(plan)})), "
                    f"p.planMultiples(r.map(x => x.cost))]; }})()")
        pick = L.best_pick(rows)
        assert [pick["name"], L.headline(rows, plan), [L.versus(x, pick, plan) for x in rows],
                L.plan_multiples([x["cost"] for x in rows])] == page
