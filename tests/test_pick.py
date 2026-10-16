import json
import shutil
import subprocess
from pathlib import Path

import pytest

PICK = Path(__file__).parent.parent / "src" / "llmledger" / "pick.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="needs node to run pick.js")

ALL = '["low", "medium", "high", "xhigh", "max"]'


def run(expression):
    script = f"const p = require({json.dumps(str(PICK))}); console.log(JSON.stringify({expression}));"
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_req_s29_effort_is_clamped_to_the_levels_a_model_takes():
    assert run('[p.clamp("xhigh", ["low", "high", "max"]), p.clamp("max", ["low", "medium", "high"]), '
               'p.clamp("low", ["high", "max"]), p.clamp("high", null), p.clamp("medium", ["medium"])]') == [
        "high", "high", "high", None, "medium"]


def test_req_s29_effort_suggestion_known_answers():
    cases = [
        ('"Write a short poem about the sea"', '"creative_writing"', 9, "low"),
        ('"What is the capital of France?"', '"overall"', 8, "low"),
        ('"Explain how photosynthesis works for a school report, with examples."', '"science"', 60, "high"),
        ('"Fix this Python function so the tests pass: ..."', '"coding"', 300, "high"),
        ('"Design the architecture for a new web app from scratch"', '"webdev"', 900, "xhigh"),
        ('"Design the architecture for a new web app from scratch"', '"webdev"', 2500, "max"),
    ]
    for text, task, tokens, level in cases:
        assert run(f"p.suggestEffort({text}, {task}, {ALL}, {tokens}).level") == level, text


def test_req_s29_effort_suggestion_says_why_and_respects_the_model():
    got = run(f'p.suggestEffort("Debug this race condition in our Go server", "coding", {ALL}, 900)')
    assert got == {"level": "xhigh", "why": ["a task where thinking helps", 'it asks for "debug"']}
    assert run('p.suggestEffort("Debug this race condition", "coding", ["low", "high"], 900).level') == "high"
    assert run('p.suggestEffort("Debug this", "coding", null, 900)') == {"level": None, "why": []}
    # no prompt: the model's default level, if LiteLLM lists one
    assert run(f'[p.suggestEffort("", "coding", {ALL}, 0, "medium").level, '
               f'p.suggestEffort(" ", "coding", {ALL}, 0, "").level]') == ["medium", None]


def test_req_s29_plan_use_is_relative_to_the_least():
    assert run("p.planMultiples([2, 5, null, 1])") == [2, 5, None, 1]
    assert run("p.planMultiples([0, 0.5, 1])") == [None, 1, 2]
    assert run("p.planMultiples([null, 0])") == [None, None]


def test_req_s29_verdict_known_answer():
    # Prices from LiteLLM: Opus 5.5 $4 / $20 per 1M, Fable 5.1 $10 / $50, Sonnet 5.5 $2 / $10. Same tokens per task.
    rows = json.dumps([
        {"name": "claude-opus-5.5", "rating": 1547.5, "low": 1541, "high": 1554, "cost": 0.0172, "out": 20},
        {"name": "claude-fable-5.1", "rating": 1537.1, "low": 1529, "high": 1544, "cost": 0.043, "out": 50},
        {"name": "claude-sonnet-5.5", "rating": 1530.0, "low": 1520, "high": 1536, "cost": 0.0086, "out": 10},
        {"name": "tiny", "rating": 1300.0, "low": 1290, "high": 1310, "cost": 0.0000824, "out": 0.1},
    ])
    assert run(f'p.verdict({rows}, {{task: "coding"}})') == [
        "claude-opus-5.5 has the highest coding rating here (1548).",
        "claude-fable-5.1 costs about 2.5× as much per task, and the votes cannot tell its rating apart (1537); "
        "to cost less it would have to use under 40% of claude-opus-5.5's answer tokens.",
        "claude-sonnet-5.5 costs about 50% less per task, with a lower rating (1530 against 1548); "
        "it stays cheaper unless it uses over 2.0× claude-opus-5.5's answer tokens.",
        "tiny costs about 1/209 as much per task, with a lower rating (1300 against 1548).",
    ]


def test_req_s29_verdict_on_a_plan_and_without_ratings():
    rows = json.dumps([
        {"name": "a", "rating": None, "low": None, "high": None, "cost": 0.01, "out": 10},
        {"name": "b", "rating": None, "low": None, "high": None, "cost": 0.03, "out": 30},
    ])
    assert run(f'p.verdict({rows}, {{task: "coding", plan: true}})') == [
        "b uses the plan about 3.0× as fast, with no coding rating; "
        "to use less of the plan it would have to use under 33% of a's answer tokens."]
    assert run('p.verdict([{name: "a", cost: 1}], {})') == ["Add another model to compare."]
