# llmledger and promptfoo

[promptfoo](https://github.com/promptfoo/promptfoo) (MIT) runs prompts against models and checks the answers.
llmledger works with it in two ways: promptfoo checks the plug-in's answers, and the plug-in learns from
promptfoo's timed runs how long your jobs take.

## 1. Check the plug-in's answers

`mcp/promptfoo` calls the plug-in's tools directly through promptfoo's MCP provider (no AI model is called,
so it costs nothing) and checks each answer against a key worked out from `data.json` itself, not by the
plug-in's code:

- `estimate_cost` prices a model at the cheapest of its listings for the tokens asked about;
- `compare_models` gives the same cost per task as `estimate_cost`;
- `price_history` shows every listing of the model.

```bash
cd mcp/promptfoo
python make_tests.py                # today's data.json; writes tests.json (about 30 checks)
npx promptfoo@latest eval           # runs the plug-in built from this repository (needs uv)
```

`make_tests.py` takes a local `data.json` and the number of models as arguments. To check the published
plug-in instead, change the server in `promptfooconfig.yaml` to `command: uvx` and `args: ['llmledger-mcp']`.
These checks would have caught the listing slip fixed in plug-in 0.1.3: run against 0.1.2 on the data of
19 October 2026, 2 of 30 fail (for example claude-fable-5 at one host's $11/$55 instead of $10/$50).

## 2. Learn how long a job takes

`estimate_time` gives the time of one call and of a whole job, as a usual time and a slow day, from your own
timed runs of that model called that way: through the API, Claude Code started fresh, a Claude Code session
kept open, a local model in Ollama, with thinking on or off. No public speed table is used: the open ones
either do not measure your setup or do not carry an open licence, so an estimate starts at your first run.

A promptfoo results file counts as runs, one per result (its `latencyMs` and `tokenUsage`); cached results,
failures and calls with no tokens are skipped, and a file logged twice counts once.

```bash
npx promptfoo@latest eval -c your-config.yaml -o results.json
```

Then ask the plug-in to `log_run` with `promptfoo_results` set to that file (the skill: `log --promptfoo
results.json`), and `estimate_time` for the job. Runs stay in `~/.local/share/llmledger-mcp/runs.jsonl` on your
computer (`LLMLEDGER_RUNS` names another file); nothing is sent anywhere.

How the estimate is made: for one model and way, a call's time is fitted as a fixed start plus a time per
answer token by the Theil-Sen estimator (the median of the slopes between pairs of runs), so one odd run cannot
pull it far. The usual time is the fit times the median ratio of real to fitted time over the newest 50 runs,
and a slow day the 90th percentile of that ratio; with fewer than 5 runs, a slow day is at least twice the
usual time, and the answer says it is rough.
