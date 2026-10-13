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


CHAT = '{key: "x", mode: "chat", input: 3, output: 15, skills: ["vision", "pdf"], media: null}'


def test_req_s24_answer_lengths_are_fixed_sizes():
    assert run("Object.fromEntries(Object.entries(c.ANSWERS).map(([k, a]) => [k, a.tokens]))") == {
        "short": 250, "medium": 800, "long": 2000, "very_long": 6000}


def test_req_s24_attachments_add_cost_and_need_the_skill():
    got = run(f"""[{{want: "text", inTok: 1000, outTok: 500}},
                   {{want: "text", inTok: 1000, outTok: 500, images: 2}},
                   {{want: "text", pages: 10}},
                   {{want: "text", audioSeconds: 60}}].map(q => c.priceFor({CHAT}, q))""")
    assert got[0] == pytest.approx(0.0105, abs=1e-15)
    assert got[1] == pytest.approx(0.0105 + 2 * 1000 * 3e-6, abs=1e-15)   # about 1,000 tokens per image
    assert got[2] == pytest.approx(10 * 1500 * 3e-6, abs=1e-15)            # about 1,500 tokens per page
    assert got[3] is None                                                  # no audio skill


def test_req_s24_listed_per_unit_prices_win_over_estimates():
    model = '{key: "g", mode: "chat", input: 1, output: 2, skills: ["vision", "audio"], media: {in_img: 0.001, aud_s: 0.0001}}'
    got = run(f'[c.priceFor({model}, {{want: "text", images: 3}}), c.priceFor({model}, {{want: "text", audioSeconds: 60}})]')
    assert got == pytest.approx([0.003, 0.006], abs=1e-15)


def test_req_s24_images_video_and_speech_out():
    got = run("""[
      c.priceFor({key: "dall-e-3", mode: "image_generation", media: {out_img: 0.04}}, {want: "image", count: 3}),
      c.priceFor({key: "1024-x-1024/dall-e-2", mode: "image_generation", media: {px_in: 2e-8}}, {want: "image", count: 1}),
      c.priceFor({key: "sora-2", mode: "video_generation", media: {out_vid_s: 0.1}}, {want: "video", count: 10}),
      c.priceFor({key: "tts-1", mode: "audio_speech", media: {in_chr: 1.5e-5}}, {want: "speech", count: 1000}),
      c.priceFor({key: "x", mode: "chat", input: 3, output: 15}, {want: "image", count: 1})]""")
    assert got[:4] == pytest.approx([0.12, 1024 * 1024 * 2e-8, 1.0, 0.015], abs=1e-12)
    assert got[4] is None


def test_req_s24_family_and_version_from_a_grouped_name():
    got = run('["claude-sonnet-4.5", "qwen3.8-max", "gemini-2.5-flash", "mistral-large"].map(c.familyOf)')
    assert got == [["claude-sonnet", "4.5"], ["qwen-max", "3.8"], ["gemini-flash", "2.5"],
                   ["mistral-large", ""]]


def test_req_s25_best_value_is_the_cheapest_tied_with_the_top():
    got = run("""c.bestValue([{rating: 1500, low: 1495, high: 1505, cost: 5},
                               {rating: 1497, low: 1490, high: 1504, cost: 1},
                               {rating: 1480, low: 1470, high: 1490, cost: 0.1}])""")
    assert got["cost"] == 1
    assert run("c.bestValue([])") is None
