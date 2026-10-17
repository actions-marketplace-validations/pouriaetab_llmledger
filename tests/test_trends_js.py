import json
import shutil
import subprocess
from pathlib import Path

import pytest

TRENDS = Path(__file__).parent.parent / "src" / "llmledger" / "trends.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="needs node to run trends.js")


def run(expression):
    script = f"const t = require({json.dumps(str(TRENDS))}); console.log(JSON.stringify({expression}));"
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_req_s33_a_rating_gap_in_plain_odds():
    assert run("[t.odds(0), t.odds(100), t.odds(200), t.odds(-100)].map(x => Math.round(100 * x))") == [50, 64, 76, 36]


def test_req_s34_the_edge_keeps_only_models_nobody_beats_on_both():
    pts = '[{x: 1, y: 1300, n: "a"}, {x: 2, y: 1350, n: "b"}, {x: 2, y: 1340, n: "c"}, {x: 3, y: 1320, n: "d"},' \
          ' {x: 10, y: 1400, n: "e"}, {x: 0, y: 1500, n: "free"}]'
    assert run(f"t.frontier({pts}).map(p => p.n)") == ["a", "b", "e"]
    assert run("t.frontier([])") == []


def test_req_s33_a_line_is_drawn_between_its_points_and_ends_after_a_month():
    pts = "[[10, 1400], [20, 1500], [30, 1450]]"
    assert run(f"[t.valueAt({pts}, 5), t.valueAt({pts}, 15), t.valueAt({pts}, 30), t.valueAt({pts}, 60), t.valueAt({pts}, 61)]") == [
        None, 1450, 1450, 1450, None]
    assert run(f"t.valueAt({pts}, 15, true)") == 1400                      # prices hold until the next point
    assert run(f"t.pointAt({pts}, 25)") == [20, 1500]


def test_req_s33_labels_never_overlap_and_stay_inside():
    out = run("t.spread([50, 52, 53, 200, 199], 19, 10, 210)")
    assert len(out) == 5 and all(10 <= y <= 210 for y in out)
    ys = sorted(out)
    assert all(b - a >= 19 - 1e-9 for a, b in zip(ys, ys[1:]))
    assert run("t.spread([100], 19, 10, 210)") == [100]


def test_req_s33_round_ticks():
    assert run("t.ticks(1452, 1531, 4)") == [1460, 1480, 1500, 1520]
    assert run("t.logTicks(0.08, 120)") == [0.1, 1, 10, 100]
    assert run("t.logTicks(0.3, 4)") == [0.5, 1, 2]


def test_req_s35_new_arrivals_are_new_groups_with_a_text_price():
    models = json.dumps([
        {"maker": "acme", "name": "new-1", "added": "2026-10-15", "status": "listed", "mode": "chat", "input": 1, "output": 2},
        {"maker": "acme", "name": "new-1", "added": "2026-10-16", "status": "listed", "mode": "chat", "input": 1, "output": 2},
        {"maker": "acme", "name": "old-1", "added": "", "status": "listed", "mode": "chat", "input": 1, "output": 2},
        {"maker": "acme", "name": "old-1", "added": "2026-10-16", "status": "listed", "mode": "chat", "input": 1, "output": 2},
        {"maker": "acme", "name": "img-1", "added": "2026-10-16", "status": "listed", "mode": "image_generation",
         "input": None, "output": None},
        {"maker": "beta", "name": "new-2", "added": "2026-10-10", "status": "listed", "mode": "chat", "input": 1, "output": 2},
    ])
    assert run(f"t.arrivals({models}, 5).map(g => [g.id, g.first])") == [["acme / new-1", "2026-10-15"],
                                                                         ["beta / new-2", "2026-10-10"]]


def test_req_s35_latest_changes_fold_batches_and_join_price_fields():
    recent = json.dumps(
        [["2026-10-16", f"x/m{i}", "removed", "", None, None, "bulk"] for i in range(5)]
        + [["2026-10-16", "a/m", "price", "input_cost_per_token", 2e-6, 1e-6, ""],
           ["2026-10-16", "a/m", "price", "output_cost_per_token", 8e-6, 4e-6, ""],
           ["2026-10-15", "b/m", "added", "", None, None, ""],
           ["2026-10-14", "c/m", "deprecation", "deprecation_date", None, "2026-12-01", ""]])
    out = run(f"t.digest({recent}).map(e => [e.day, e.kind, e.count, e.keys ? e.keys.length : e.fields.length])")
    assert out == [["2026-10-16", "bulk", 5, 5], ["2026-10-16", "price", 1, 2],
                   ["2026-10-15", "added", 1, 1], ["2026-10-14", "deprecation", 1, 1]]
