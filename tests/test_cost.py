import json
import shutil
import subprocess
from pathlib import Path

import pytest

COST = Path(__file__).parent.parent / "src" / "llmledger" / "cost.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="needs node to run cost.js")


def run(expression):
    script = f"const c = require({json.dumps(str(COST))}); console.log(JSON.stringify({expression}));"
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_req_s23_tokens_are_estimated_at_four_characters():
    assert run('[c.estimateTokens(""), c.estimateTokens("abcd"), c.estimateTokens("abcde"), '
               'c.estimateTokens("été")]') == [0, 1, 2, 1]


def test_req_s23_cost_known_answer():
    # 1,000 prompt tokens at $3 per 1M plus 500 answer tokens at $15 per 1M.
    assert run("c.costOf(3, 15, 1000, 500)") == pytest.approx(0.0105, abs=1e-15)
    assert run("c.costOf(null, 15, 1000, 500)") is None
    assert run("c.costOf(0, 0, 1000, 500)") == 0


def test_req_s23_cheapest_listing_per_model():
    rows = run("""c.cheapestPerGroup(
        [{k: "a1", g: "a", p: 5}, {k: "a2", g: "a", p: 2}, {k: "b1", g: "b", p: 3},
         {k: "c1", g: "c", p: null}],
        r => r.g, r => r.p).map(x => [x.id, x.row.k, x.cost])""")
    assert rows == [["a", "a2", 2], ["b", "b1", 3]]


def test_req_s23_only_text_models_are_priced():
    assert run('["chat", "responses", "completion", "embedding"].map(m => c.isTextModel("x", m))') == [
        True, True, True, False]
    assert run('["vercel_ai_gateway/amazon/titan-embed-text-v2", "fireworks_ai/models/flux-1-dev", '
               '"groq/llama-guard-3-8b", "anthropic/claude-sonnet-4-5"].map(k => c.isTextModel(k, "chat"))') == [
        False, False, True, True]
