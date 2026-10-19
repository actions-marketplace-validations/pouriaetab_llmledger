# llmledger and promptfoo

[promptfoo](https://github.com/promptfoo/promptfoo) (MIT) runs prompts against models and checks the answers.
llmledger works with it in three ways: promptfoo checks the plug-in's answers, the plug-in learns from
promptfoo's timed runs how long your jobs take, and it quotes a whole job from a promptfoo run of a sample.

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
calls that did not run and calls with no tokens are skipped, and a file logged twice counts once. A result
whose checks failed is still a timed call. How each model was called is read from its provider (`ollama:`
is a local model, `anthropic:claude-agent-sdk` is Claude Code, a host such as `openai:` is its API), and a
result that counts thinking tokens is marked as thinking on.

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

## 3. Quote the whole job from a sample

promptfoo runs a job but has no estimate before the run, prices calls from a table kept in its own code,
and knows nothing of other hosts or price changes. Run a random sample of the job first, then ask the
plug-in to `forecast_job` with that file and the size of the whole job (the skill: `forecast sample.json
--items 5000`):

```bash
npx promptfoo@latest eval --filter-sample 20 --filter-sample-seed 7 -o sample.json
```

For each model (and prompt, when a model tried more than one) in the sample it gives:

- the whole job's time, as a usual time and a slow day, from the sample's own timed calls and your logged
  runs of the same model called the same way, at the sample's number of calls at once unless you give
  another (`concurrency`);
- the cost of every call of the job from the sample's average tokens, at the model's cheapest listing next
  to the listing the sample used, and promptfoo's own figure for the sample with the job at that rate (when
  the two differ by more than a tenth, the answer says why they may);
- the chance of a price change within 90 days on the cheapest listing (as `price_history`);
- how often it was right: the share of checked results that passed, with a Wilson 95% range (18 of 20 is
  70% to 97%; 20 of 20 is 84% to 100%), and calls that did not run counted apart;
- the break-even against the pick: what a wrong answer must cost you to catch and fix before a dearer model
  that was right more often pays for itself (the cost difference an item over the difference in how often
  each was right).

The pick is the cheapest of the models the sample cannot tell apart from the most often right (their
ranges overlap), as `compare_models` picks among ratings. Give `wrong_answer_cost` and it is instead the
lowest cost an item with each wrong answer counted at that cost. A sample of 20 tells models apart only
when they differ a lot; the answer says when it cannot. Nothing is called or sent: the tool reads the file.

