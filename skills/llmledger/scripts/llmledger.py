#!/usr/bin/env python3
"""llmledger from the command line: the plug-in's answers, for the Agent Skill. Standard library only.

Prints one JSON object. The data (LiteLLM's prices, Arena's ratings, every price change since 2023) is
downloaded once a day from the llmledger page and kept in ~/.cache/llmledger-mcp/, the same copy the
plug-in uses. llmledger_mcp/ next to this file is a copy of the plug-in's own code (mcp/src in the repo).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llmledger_mcp import data, logic, speed, tools  # noqa: E402


def _names(text):
    return [part.strip() for part in text.split(",") if part.strip()]


def parser():
    p = argparse.ArgumentParser(prog="llmledger.py", description="Which AI model, and what it costs. Prints JSON.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("suggest", help="guess the kind of work in a prompt and suggest models with cost and effort")
    s.add_argument("prompt", help="the prompt, or a description of the work")
    s.add_argument("--pay", choices=tools.PAYS, default="api", help="api: dollars; claude or chatgpt: within that plan")
    s.add_argument("--answer", choices=list(logic.ANSWERS), default="medium", help="typical answer length")

    c = sub.add_parser("compare", help="2 to 6 models side by side: rating, prices, cost per task and the pick")
    c.add_argument("models", nargs="+", help="model names, for example claude-opus-5.5 gpt-6.1")
    c.add_argument("--task", choices=logic.TASKS, default="overall")
    c.add_argument("--input", type=int, default=1000, help="prompt tokens per task")
    c.add_argument("--output", type=int, default=800, help="answer tokens per task, hidden thinking included")
    c.add_argument("--pay", choices=tools.PAYS, default="api")

    e = sub.add_parser("cost", help="what a workload costs per call, per day and per 30 days")
    e.add_argument("models", nargs="+", help="1 to 10 model names")
    e.add_argument("--input", type=int, required=True, help="prompt tokens per call")
    e.add_argument("--output", type=int, required=True, help="answer tokens per call, hidden thinking included")
    e.add_argument("--cached", type=int, default=0, help="prompt tokens read from the cache")
    e.add_argument("--cache-write", type=int, default=0, help="prompt tokens written to the cache")
    e.add_argument("--calls-per-day", type=float, default=1)

    f = sub.add_parser("find", help="the highest rated models for a kind of work, within limits; or one model by --name")
    f.add_argument("--name", help="look one model up: every listing of it")
    f.add_argument("--task", choices=logic.TASKS, default="overall")
    f.add_argument("--needs", type=_names, default=[], help="comma separated: " + ",".join(tools.NEEDS))
    f.add_argument("--max-output-price", type=float, help="dollars per 1M answer tokens")
    f.add_argument("--min-context", type=int, help="smallest prompt size, in tokens")
    f.add_argument("--maker", help="for example anthropic or openai")
    f.add_argument("--limit", type=int, default=5)

    h = sub.add_parser("history", help="every change to a model's prices and the chance of the next one")
    h.add_argument("model")
    h.add_argument("--date", help="YYYY-MM-DD: each listing's prices that day and the change that set them")

    u = sub.add_parser("unpriced", help="new models on Arena that have no price yet, and how soon prices usually come")
    u.add_argument("--maker", help="for example meta or ibm")

    t = sub.add_parser("time", help="how long a call and a whole job take, learned from your own timed runs")
    t.add_argument("model")
    t.add_argument("--input", type=int, required=True, help="prompt tokens per call")
    t.add_argument("--output", type=int, required=True, help="answer tokens per call, hidden thinking included")
    t.add_argument("--calls", type=int, default=1)
    t.add_argument("--at-once", type=int, default=1, help="calls running at the same time")
    t.add_argument("--way", choices=speed.WAYS, default="api", help="how the model is called")
    t.add_argument("--thinking", action="store_true")

    g = sub.add_parser("log", help="keep a timed run (or a promptfoo results file) so time estimates learn from it")
    g.add_argument("model", nargs="?")
    g.add_argument("--input", type=int)
    g.add_argument("--output", type=int)
    g.add_argument("--seconds", type=float)
    g.add_argument("--way", choices=speed.WAYS, help="default api; for a promptfoo file, read from each provider")
    g.add_argument("--thinking", action="store_true")
    g.add_argument("--task")
    g.add_argument("--promptfoo", help="a promptfoo results file: promptfoo eval -o results.json")

    q = sub.add_parser("forecast", help="quote a whole job (time, cost, how often right) from a promptfoo sample run")
    q.add_argument("promptfoo", help="the sample's results file: promptfoo eval --filter-sample 20 -o sample.json")
    q.add_argument("--items", type=int, required=True, help="how many tests the whole job has")
    q.add_argument("--at-once", type=int, help="calls running at the same time (default: as the sample ran)")
    q.add_argument("--way", choices=speed.WAYS, help="how the models are called (default: read from each provider)")
    q.add_argument("--thinking", action="store_true")
    q.add_argument("--wrong-cost", type=float, help="dollars a wrong answer costs to catch and fix")

    lc = sub.add_parser("local", help="buy a computer for an open model, or pay a cloud model: when buying pays off")
    lc.add_argument("local_model", help="the open model as Ollama names it, for example llama3.1:8b")
    lc.add_argument("cloud_models", nargs="+", help="1 to 5 cloud models to compare with")
    lc.add_argument("--input", type=int, required=True, help="prompt tokens per call")
    lc.add_argument("--output", type=int, required=True, help="answer tokens per call, hidden thinking included")
    lc.add_argument("--calls-per-month", type=float, required=True)
    lc.add_argument("--hardware-price", type=float, required=True, help="what the computer costs, in dollars")
    lc.add_argument("--watts", type=float, help="power the computer draws while it answers")
    lc.add_argument("--kwh-price", type=float, help="your electricity price, dollars per kWh")
    lc.add_argument("--state", help="a US state, for EIA's average price there")
    lc.add_argument("--months", type=int, default=36)
    lc.add_argument("--cached", type=int, default=0, help="prompt tokens read from the cloud model's cache")
    lc.add_argument("--way", choices=speed.WAYS, default="ollama", help="how the local model is called")

    us = sub.add_parser("usage", help="your own coding agent usage (ccusage or codeburn export) priced on every rated model")
    us.add_argument("export", help="the export file: ccusage daily --json, ccusage session --json, or codeburn export -f json")
    us.add_argument("--task", help="the kind of work (default: codeburn's categories, else coding)")
    us.add_argument("--compare", nargs=2, metavar="MODEL", help="two models to test on the same sessions")
    us.add_argument("--limit", type=int, default=25)

    sub.add_parser("tasks", help="the kinds of work Arena rates, and what the data holds today")
    return p


def run(args, shelf):
    if args.command == "local":
        return tools.local_or_cloud(shelf, args.local_model, args.cloud_models, args.input, args.output,
                                    args.calls_per_month, args.hardware_price, watts=args.watts,
                                    electricity_price=args.kwh_price, state=args.state, months=args.months,
                                    cached_tokens=args.cached, local_way=args.way)
    if args.command == "forecast":
        return tools.forecast_job(shelf, args.promptfoo, args.items, concurrency=args.at_once, way=args.way,
                                  thinking=args.thinking, wrong_answer_cost=args.wrong_cost)
    if args.command == "usage":
        return tools.price_my_usage(shelf, export=args.export, task=args.task, compare=args.compare,
                                    limit=max(1, min(args.limit, 200)))
    if args.command == "time":
        return tools.estimate_time(shelf, args.model, args.input, args.output, calls=args.calls, way=args.way,
                                   thinking=args.thinking, concurrency=args.at_once)
    if args.command == "log":
        return tools.log_run(shelf, model=args.model, input_tokens=args.input, output_tokens=args.output,
                             seconds=args.seconds, way=args.way, thinking=args.thinking, task=args.task,
                             promptfoo_results=args.promptfoo)
    if args.command == "suggest":
        return tools.suggest_for_project(shelf, args.prompt, pay=args.pay, answer=args.answer)
    if args.command == "compare":
        return tools.compare_models(shelf, args.models, task=args.task, input_tokens=args.input,
                                    output_tokens=args.output, pay=args.pay)
    if args.command == "cost":
        return tools.estimate_cost(shelf, args.models, args.input, args.output, cached_tokens=args.cached,
                                   calls_per_day=args.calls_per_day, cache_write_tokens=args.cache_write)
    if args.command == "find":
        return tools.find_models(shelf, task=args.task, max_output_price=args.max_output_price,
                                 min_context=args.min_context, needs=args.needs, maker=args.maker,
                                 limit=max(1, min(args.limit, 200)), name=args.name)
    if args.command == "history":
        return tools.price_history(shelf, args.model, date=args.date)
    if args.command == "unpriced":
        return tools.not_yet_priced(shelf, maker=args.maker)
    return tools.snapshot(shelf)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        try:
            shelf = data.Shelf(*data.load())
        except RuntimeError:
            if args.command not in ("time", "log", "forecast"):
                raise
            shelf = None                                # timing needs no prices
        out = run(args, shelf)
    except (tools.NotFound, RuntimeError) as error:
        print(json.dumps({"error": str(error)}))
        return 1
    print(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
