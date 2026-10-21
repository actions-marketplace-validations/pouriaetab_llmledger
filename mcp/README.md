# llmledger-mcp

<!-- mcp-name: io.github.pouriaetab/llmledger -->

Ask Claude (or Cursor, ChatGPT desktop, any app that speaks MCP) which AI model to use and what it
costs, in the middle of your work. The answers come from [llmledger](https://pouriaetab.github.io/llmledger/):
LiteLLM's public price catalogue, Arena's ratings by task, and every price change since 2023 with how
likely a price is to change next. Rebuilt every day.

## Install

Needs [uv](https://docs.astral.sh/uv/). Nothing to host and no keys: the plug-in runs on your computer
and reads the day's data from the llmledger page, cached for a day, with a bundled copy for offline use.

Claude Code:

```bash
claude mcp add llmledger -- uvx llmledger-mcp
```

Claude Desktop (Settings, Developer, Edit config) or Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "llmledger": { "command": "uvx", "args": ["llmledger-mcp"] }
  }
}
```

A LiteLLM proxy can offer it to a whole team through its MCP gateway, as a stdio server with the same
command.

The same answers also come as an Agent Skill, which takes far less of an agent's context until it is used
and needs only Python: the folder `skills/llmledger` in the repository,
https://github.com/pouriaetab/llmledger/tree/main/skills/llmledger
In Claude Code: `/plugin marketplace add pouriaetab/llmledger`, then `/plugin install llmledger@llmledger`.

## What you can ask

| Tool | For example |
|---|---|
| `suggest_for_project` | "Which model and effort for this project?" with the starting prompt; `pay` can be `claude` or `chatgpt` to compare within a plan |
| `compare_models` | "Opus 5.5 or Fable 5.1 for coding, and when is Fable cheaper?" |
| `estimate_cost` | "What do 2,000 calls a day of 10K tokens in and 1K out cost on these three?", and with `cached_tokens` and `cache_write_tokens`, how much the cache saves |
| `find_models` | "The best rated coding models under $10 per 1M answer tokens that read images"; or `name` to look one model up with every host that lists it |
| `price_history` | "Has Claude Opus 5.5's price changed, and how likely is it to change soon?"; with `date`, "What did it cost on 1 March?" Each change links the LiteLLM change behind it |
| `not_yet_priced` | "Which new models on Arena have no price yet, and how long does a price usually take?" |
| `estimate_time` | "How long will 5,000 calls of 2K tokens in and 600 out take on Opus 5.5 through the API, 4 at a time?" Learned from your own runs |
| `log_run` | "I timed this call: 2,100 in, 640 out, 9.2 seconds", or a promptfoo results file; kept on your computer only |
| `forecast_job` | "Here is a promptfoo run of 20 of my 5,000 tests: what will the whole job cost and take on each model, and which should I pick?" Reads the file only |
| `local_or_cloud` | "Should I buy a $2,000 computer to run llama3.1:8b at home, or keep paying for GPT-6.1 at 30,000 calls a month?" The local model's speed from your own runs, electricity from EIA or your price |
| `price_my_usage` | "Here is my `ccusage session --json` (or `codeburn export -f json`) file: what would last month's work have cost on every other model, which ones keep the quality for less, and is the gap real?" Each session at the price of its day, Arena ratings for that kind of work, a 95% range per session; token counts only |

Plus a resource, `llmledger://snapshot` (data dates and sources), and a prompt, `pick_a_model`.

## Good to know

- Costs and ratings are estimates. Arena ratings say which answers people preferred, not what will work
  best for you. Plan use (Claude, ChatGPT) assumes a plan runs down in step with API prices, because
  plans do not publish per-model limits. Not financial or procurement advice.
- Effort levels come from LiteLLM; the suggested level is a rule of thumb. No open source measures
  tokens per task at each effort level yet.
- Many price changes in the catalogue fix a wrong entry rather than change a price: in a labelled sample,
  about 6 in 10 first price changes. `price_history` says what each flag on a change means (a likely
  correction, a unit fix, a change undone) and how often such changes were corrections.
- Every answer carries the date of its data. When the data is 3 or more days old, the answer says so.
- `price_my_usage` prices other models at your own token counts; another model tokenises the same work a little
  differently (usually within 10 to 20%) and may answer at another length. Models you used are compared on the
  sessions each one got, which were not the same work, and the answer says so. A model with no cache price has cache
  tokens counted at its input price, and the row says so.
- Times come only from your own runs (and the sample's own timed calls for `forecast_job`), always as a
  usual time and a slow day. How often a model was right is the share of a sample's checks it passed, with
  a 95% range; with 20 tests the range is wide, and the answer says when two models cannot be told apart.
- What the plug-in reads: a prompt given to `suggest_for_project` is only counted and matched against word
  lists; a promptfoo results file (`log_run`, `forecast_job`) is read for numbers and names only (provider id,
  latency, token counts, pass or fail), and the prompts, answers and grader text inside it are never passed on
  or treated as instructions; a ccusage or codeburn export (`price_my_usage`) is read for model names, dates, session
  ids and token counts only, never project paths or file names. Timed runs stay on your computer as numbers. The only network call is the daily
  download of `data.json`.
- Set `LLMLEDGER_DATA` to a local data.json or another address to use your own copy.

## Data and licences

Prices: LiteLLM's `model_prices_and_context_window.json` (MIT). Ratings: the Arena leaderboard
(CC BY 4.0). Electricity: the U.S. Energy Information Administration's Electric Power Monthly
(public domain). Price history and outlook: [llmledger](https://github.com/pouriaetab/llmledger) (MIT).
Built with [FastMCP](https://github.com/PrefectHQ/fastmcp) (Apache-2.0). Independent; not affiliated
with BerriAI, LiteLLM or Arena.
