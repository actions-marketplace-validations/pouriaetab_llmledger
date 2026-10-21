"""The promptfoo checks of the plug-in (mcp/promptfoo): answer keys worked out from data.json on its own."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
FIXTURE = json.loads((ROOT / "mcp" / "tests" / "fixture.json").read_text())
spec = importlib.util.spec_from_file_location("make_tests", ROOT / "mcp" / "promptfoo" / "make_tests.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def test_req_s46_answer_keys_come_from_the_data():
    data = json.loads(json.dumps(FIXTURE))
    data["models"].append(dict(data["models"][0], key="free/claude-opus-5-5", host="free", input=0.0, output=0.0))
    tests = M.cases(data, 4)
    cost = {json.loads(t["vars"]["prompt"])["args"]["models"][0]: t["vars"]["expected"]
            for t in tests if '"estimate_cost"' in t["vars"]["prompt"]}
    # opus: $4/$20 and $4.40/$22 listings (and a free one, which does not count): 2,000 in and 600 out
    assert cost["anthropic / claude-opus-5.5"] == (2000 * 4 + 600 * 20) / 1e6
    history = [t for t in tests if '"price_history"' in t["vars"]["prompt"]]
    assert all(isinstance(t["vars"]["expected"], int) for t in history)
    pairs = [t for t in tests if '"compare_models"' in t["vars"]["prompt"]]
    assert pairs and all(len(t["vars"]["expected"]) == 2 for t in pairs)
    usage = [t for t in tests if '"price_my_usage"' in t["vars"]["prompt"]]
    assert len(usage) == 3 and usage[0]["vars"]["expected"] == ["anthropic / claude-opus-5.5", 5 * (2000 * 4 + 600 * 20) / 1e6]
    assert all(a["value"].startswith("file://check.js:") for t in tests for a in t["assert"])


def test_req_s46_the_keys_agree_with_the_plugin_on_its_test_data():
    sys.path.insert(0, str(ROOT / "skills" / "llmledger" / "scripts"))
    try:
        from llmledger_mcp import data, tools
    finally:
        sys.path.pop(0)
    shelf = data.Shelf(FIXTURE, "test")
    for t in M.cases(FIXTURE, 4):
        call = json.loads(t["vars"]["prompt"])
        if call["tool"] == "estimate_cost":
            got = tools.estimate_cost(shelf, **call["args"])["models"][0]["per_call"]
            assert abs(got - t["vars"]["expected"]) < 1e-12, call
        if call["tool"] == "price_my_usage":
            group, want = t["vars"]["expected"]
            row = next(r for r in tools.price_my_usage(shelf, **call["args"])["every_model"] if r["model"] == group)
            assert abs(row["cost"] - want) < 1e-9, call


def test_req_s46_the_config_runs_the_repository_plugin_through_the_mcp_provider():
    config = (ROOT / "mcp" / "promptfoo" / "promptfooconfig.yaml").read_text()
    assert "- id: mcp" in config and "args: ['--from', '..', 'llmledger-mcp']" in config
    assert "tests: file://tests.json" in config
    checks = (ROOT / "mcp" / "promptfoo" / "check.js").read_text()
    for name in ("perCall", "listingsInTotal", "costPerTask", "usageCost"):
        assert f"module.exports.{name} = " in checks
