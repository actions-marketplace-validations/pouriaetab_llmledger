import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROUTE = Path(__file__).parent.parent / "src" / "llmledger" / "route.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="needs node to run route.js")


def guess(text, extra=None):
    script = (f"const r = require({json.dumps(str(ROUTE))});"
              f"console.log(JSON.stringify(r.guessTask({json.dumps(text)}, {json.dumps(extra or {})})));")
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


@pytest.mark.parametrize("text, task", [
    ("Write a python function that reverses a list", "coding"),
    ("Build a landing page in React with Tailwind", "webdev"),
    ("Solve the equation 2x + 3 = 11 and prove the answer", "math"),
    ("Write a poem about the sea at night", "creative_writing"),
    ("Draft a contract clause for a lawsuit settlement", "legal"),
    ("Как мне лучше провести выходные с семьёй?", "russian"),
    ("今日はとても良い天気ですね、散歩に行きましょう", "japanese"),
    ("¿Cómo está usted? Necesito ayuda con esto, por favor, para el lunes", "spanish"),
    ("Hello there, how are you today?", "overall"),
])
def test_req_s27_task_guess_known_answers(text, task):
    assert guess(text)["task"] == task


def test_req_s27_attachments_decide_first():
    assert guess("Write a python function", {"pages": 2})["task"] == "document"
    assert guess("What is in this picture?", {"images": 1})["task"] == "vision"


def test_req_s27_the_guess_says_why():
    found = guess("Write a python function that reverses a list")["why"]
    assert "python" in found and "function" in found


def test_req_s27_every_guess_is_a_task_the_page_offers():
    from llmledger.arena import TASKS
    script = (f"const r = require({json.dumps(str(ROUTE))});"
              "console.log(JSON.stringify({labels: Object.keys(r.LABELS), order: r.ORDER}));")
    got = json.loads(subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True).stdout)
    offered = [task for task, *_ in TASKS]
    assert got["labels"] == offered
    assert set(got["order"]) <= set(offered)
