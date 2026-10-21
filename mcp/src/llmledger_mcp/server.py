"""llmledger as a plug-in (an MCP server) for Claude and other AI apps.

Eleven tools answer "which model, what will it cost, and how long will it take?" from the same
data as the llmledger page: LiteLLM's price catalogue (MIT), Arena's ratings (CC BY 4.0), every
price change since 2023 with how likely a price is to change next, and EIA's electricity prices
(public domain); times come from the user's own timed runs. Runs on the user's own computer over stdio; reads the day's data.json,
cached for a day. The answers themselves are in tools.py, which the Agent Skill
(skills/llmledger) runs too.
"""
import time
from typing import Annotated, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from llmledger_mcp import __version__, data, logic, speed, tools

Task = Literal[tuple(logic.TASKS)]
Pay = Literal[tools.PAYS]
Need = Literal[tools.NEEDS]
Way = Literal[speed.WAYS]
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
WRITES_LOCAL = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False,
                               open_world_hint=False)

mcp = FastMCP(
    "llmledger",
    instructions=(
        "Which AI model to use, and what it costs. Prices come from LiteLLM's public catalogue, quality from "
        "Arena's votes, and each price's full history from llmledger. Pick one tool by the question: "
        "'which model for this work' -> suggest_for_project; 'these named models, which one' -> compare_models; "
        "'what will this many tokens cost' -> estimate_cost; 'show me models that fit limits' or 'look up this "
        "model' -> find_models; 'has this price changed' or 'price on a date' -> price_history; 'new models with "
        "no price yet' -> not_yet_priced; 'how long will it take' -> estimate_time (learns from log_run); 'quote a "
        "whole job from a promptfoo sample' -> forecast_job; 'buy a computer or pay the cloud' -> local_or_cloud; "
        "'what would my own usage have cost elsewhere' -> price_my_usage. Costs and ratings are estimates; pass "
        "on the credits line."),
    version=__version__,
)

_SHELF = None


def shelf():
    """The data, loaded once and refreshed after a day."""
    global _SHELF
    if _SHELF is None or time.time() - _SHELF.loaded > data.MAX_AGE:
        _SHELF = data.Shelf(*data.load())
    return _SHELF


def shelf_if_any():
    """The data when it can be loaded; timing a local model needs no prices."""
    try:
        return shelf()
    except Exception:
        return None


@mcp.tool(annotations=READ_ONLY)
def find_models(
    task: Annotated[Task, Field(description="The kind of work, as Arena rates it")] = "overall",
    max_output_price: Annotated[float | None, Field(description="Highest answer price, dollars per 1M tokens", ge=0)] = None,
    min_context: Annotated[int | None, Field(description="Smallest prompt size the model must take, in tokens", ge=0)] = None,
    needs: Annotated[list[Need], Field(description="What the model must be able to do")] = [],
    maker: Annotated[str | None, Field(description="Only this maker, for example anthropic or openai")] = None,
    limit: Annotated[int, Field(description="How many models to list (up to 200 for the whole catalogue)", ge=1, le=200)] = 5,
    name: Annotated[str | None, Field(description="Look up one model by name instead of browsing: all its listings")] = None,
) -> dict:
    """List the highest rated models for a kind of work within price, prompt size, ability and maker limits, each
    at its cheapest listing with its rating; or, with `name`, look one model up and list every host that offers
    it. Use when browsing or filtering the catalogue, or to find a model's exact name. Not for choosing between
    named models (compare_models), for a prompt you have in hand (suggest_for_project), or for a budget
    (estimate_cost)."""
    try:
        return tools.find_models(shelf(), task=task, max_output_price=max_output_price, min_context=min_context,
                                 needs=needs, maker=maker, limit=limit, name=name)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.tool(annotations=READ_ONLY)
def compare_models(
    models: Annotated[list[str], Field(description="2 to 6 model names, for example claude-opus-5.5, gpt-6.1-sol", min_length=2, max_length=6)],
    task: Annotated[Task, Field(description="The kind of work, as Arena rates it")] = "overall",
    input_tokens: Annotated[int, Field(description="Prompt tokens per task", ge=0)] = 1000,
    output_tokens: Annotated[int, Field(description="Answer tokens per task, including hidden thinking", ge=0)] = 800,
    answer_tokens: Annotated[dict[str, int] | None, Field(description="Answer tokens per model when they differ, by the names given")] = None,
    pay: Annotated[Pay, Field(description="api: dollars; claude or chatgpt: how fast each uses that plan")] = "api",
) -> dict:
    """Compare 2 to 6 named models for a kind of work: rating, prices, cost per task (or how fast each uses a
    Claude or ChatGPT plan), the pick, and for each model the share of answer tokens at which it would beat the
    pick. Use when the user already has candidate models in mind. Not for finding candidates (find_models), for
    reading a prompt to guess the work (suggest_for_project), or for a monthly budget (estimate_cost)."""
    try:
        return tools.compare_models(shelf(), models=models, task=task, input_tokens=input_tokens,
                                    output_tokens=output_tokens, answer_tokens=answer_tokens, pay=pay)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.tool(annotations=READ_ONLY)
def estimate_cost(
    models: Annotated[list[str], Field(description="1 to 10 model names", min_length=1, max_length=10)],
    input_tokens: Annotated[int, Field(description="Prompt tokens per call", ge=0)],
    output_tokens: Annotated[int, Field(description="Answer tokens per call, including hidden thinking", ge=0)],
    cached_tokens: Annotated[int, Field(description="How many of the prompt tokens are read from the cache", ge=0)] = 0,
    calls_per_day: Annotated[float, Field(description="Calls per day", ge=0)] = 1,
    cache_write_tokens: Annotated[int, Field(description="How many of the prompt tokens are written to the cache", ge=0)] = 0,
) -> dict:
    """Price a workload on 1 to 10 models at each one's cheapest listing: dollars per call, per day and per 30
    days, and with cache tokens the saving the cache makes. Use when the question is a budget or a bill: token
    counts and calls a day are known. Not for deciding which model is better (compare_models) or for pricing
    past usage from an export (price_my_usage)."""
    try:
        return tools.estimate_cost(shelf(), models=models, input_tokens=input_tokens, output_tokens=output_tokens,
                                   cached_tokens=cached_tokens, calls_per_day=calls_per_day,
                                   cache_write_tokens=cache_write_tokens)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.tool(annotations=READ_ONLY)
def price_history(
    model: Annotated[str, Field(description="A model name, for example claude-opus-5.5, or one listing such as bedrock/anthropic.claude-opus-5-5")],
    date: Annotated[str | None, Field(description="A day as YYYY-MM-DD: each listing's prices that day and the change that set them")] = None,
) -> dict:
    """Show one model's price history: every price and retirement date change since 2023 on every host, each
    with the LiteLLM change behind it, the chance of a price change, retirement or removal in the next 90 days
    and year, and with `date`, the prices on that day. Use when the question is about one model over time, a
    past price, or how likely a price is to move. Not for today's cheapest price of several models (find_models
    or estimate_cost)."""
    try:
        return tools.price_history(shelf(), model=model, date=date)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.tool(annotations=READ_ONLY)
def suggest_for_project(
    prompt: Annotated[str, Field(description="The project's starting prompt, or a description of the work")],
    pay: Annotated[Pay, Field(description="api: dollars; claude or chatgpt: compare within that plan")] = "api",
    answer: Annotated[Literal["short", "medium", "long", "very_long"], Field(description="Typical answer length")] = "medium",
) -> dict:
    """Suggest a model and effort level for a prompt or a described project: it guesses the kind of work and
    names the best value (the cheapest model the votes cannot tell apart from the top), the top rated and the
    cheapest rated, each with its cost per task. Use when the user asks "which model should I use for this" and
    the work itself is in hand. Not for named candidates (compare_models) or for browsing by limits
    (find_models)."""
    try:
        return tools.suggest_for_project(shelf(), prompt=prompt, pay=pay, answer=answer)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.tool(annotations=READ_ONLY)
def not_yet_priced(
    maker: Annotated[str | None, Field(description="Only this maker, for example meta or ibm")] = None,
) -> dict:
    """List the models Arena has rated that LiteLLM's catalogue does not price yet, with how soon the catalogue
    usually prices a maker's models after Arena first shows them. Use when a brand-new model is missing from the
    other tools' answers, or to ask what is coming. Not for models that already have a price (find_models)."""
    try:
        return tools.not_yet_priced(shelf(), maker=maker)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.tool(annotations=READ_ONLY)
def estimate_time(
    model: Annotated[str, Field(description="A model name, as the catalogue or Ollama names it")],
    input_tokens: Annotated[int, Field(description="Prompt tokens per call", ge=0)],
    output_tokens: Annotated[int, Field(description="Answer tokens per call, including hidden thinking", ge=0)],
    calls: Annotated[int, Field(description="How many calls the job makes", ge=1)] = 1,
    way: Annotated[Way, Field(description="How the model is called")] = "api",
    thinking: Annotated[bool, Field(description="Thinking turned on")] = False,
    concurrency: Annotated[int, Field(description="Calls running at once", ge=1)] = 1,
) -> dict:
    """Estimate how long one call and a whole job take, as a usual time and a slow day, from the user's own timed
    runs of that model called that way (kept by log_run). Use when the question is time, not money, and some
    runs have been logged; it says so when none have. Not for cost (estimate_cost) or for a job you have a
    promptfoo sample of (forecast_job gives time and cost together)."""
    try:
        return tools.estimate_time(shelf_if_any(), model=model, input_tokens=input_tokens, output_tokens=output_tokens,
                                   calls=calls, way=way, thinking=thinking, concurrency=concurrency)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.tool(annotations=WRITES_LOCAL)
def log_run(
    model: Annotated[str | None, Field(description="The model that ran")] = None,
    input_tokens: Annotated[int | None, Field(description="Prompt tokens of the call", ge=0)] = None,
    output_tokens: Annotated[int | None, Field(description="Answer tokens of the call, hidden thinking included", ge=0)] = None,
    seconds: Annotated[float | None, Field(description="How long the call took", gt=0)] = None,
    way: Annotated[Way | None, Field(description="How the model was called (default api; for a promptfoo file, read from each provider)")] = None,
    thinking: Annotated[bool, Field(description="Thinking was on (a promptfoo result that counts thinking tokens is marked on by itself)")] = False,
    task: Annotated[str | None, Field(description="The kind of work, if known")] = None,
    promptfoo_results: Annotated[str | None, Field(description="Path of a promptfoo results file (promptfoo eval -o results.json): every result becomes a run")] = None,
) -> dict:
    """Record a timed run (model, tokens, seconds, how it was called), or every result of a promptfoo results
    file, in a file on this computer so estimate_time can learn from it. Use right after a call or a promptfoo
    run whose time is known. Not a query: it stores and returns what it stored. Nothing is sent anywhere."""
    try:
        return tools.log_run(shelf_if_any(), model=model, input_tokens=input_tokens, output_tokens=output_tokens,
                             seconds=seconds, way=way, thinking=thinking, task=task,
                             promptfoo_results=promptfoo_results)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.tool(annotations=READ_ONLY)
def forecast_job(
    promptfoo_results: Annotated[str, Field(description="Path of a promptfoo results file from a sample of the job (promptfoo eval --filter-sample 20 -o sample.json)")],
    items: Annotated[int, Field(description="How many tests the whole job has", ge=1)],
    concurrency: Annotated[int | None, Field(description="Calls running at once in the whole job (default: as the sample ran)", ge=1)] = None,
    way: Annotated[Way | None, Field(description="How the models are called (default: read from each provider)")] = None,
    thinking: Annotated[bool, Field(description="Thinking turned on")] = False,
    wrong_answer_cost: Annotated[float | None, Field(description="Dollars a wrong answer costs you to catch and fix; the pick then counts it", ge=0)] = None,
) -> dict:
    """Estimate a whole job's time, cost and accuracy from a promptfoo run of a sample of it: for each model in
    the sample, the time as a usual time and a slow day, the cost at its cheapest listing next to the listing the
    sample used, the 90-day chance of a price change, how often it was right (95% range) and the break-even
    against the pick. Use when a promptfoo results file of a sample exists and the whole job's size is known.
    Not for a job with no sample (estimate_cost for money, estimate_time for time)."""
    try:
        return tools.forecast_job(shelf_if_any(), promptfoo_results=promptfoo_results, items=items,
                                  concurrency=concurrency, way=way, thinking=thinking,
                                  wrong_answer_cost=wrong_answer_cost)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.tool(annotations=READ_ONLY)
def local_or_cloud(
    local_model: Annotated[str, Field(description="The open model you would run at home, as Ollama names it, for example llama3.1:8b")],
    cloud_models: Annotated[list[str], Field(description="1 to 5 cloud models to compare with", min_length=1, max_length=5)],
    input_tokens: Annotated[int, Field(description="Prompt tokens per call", ge=0)],
    output_tokens: Annotated[int, Field(description="Answer tokens per call, including hidden thinking", ge=0)],
    calls_per_month: Annotated[float, Field(description="Calls a month", gt=0)],
    hardware_price: Annotated[float, Field(description="What the computer costs you, in dollars", ge=0)],
    watts: Annotated[float | None, Field(description="Power the computer draws while it answers, in watts", gt=0)] = None,
    electricity_price: Annotated[float | None, Field(description="Your electricity price, dollars per kWh (default: EIA's average for homes)", ge=0)] = None,
    state: Annotated[str | None, Field(description="A US state, for EIA's average there, for example Texas")] = None,
    months: Annotated[int, Field(description="How many months to compare over", ge=1)] = 36,
    cached_tokens: Annotated[int, Field(description="Prompt tokens read from the cloud model's cache", ge=0)] = 0,
    local_way: Annotated[Way, Field(description="How the local model is called")] = "ollama",
    thinking: Annotated[bool, Field(description="Thinking turned on for the local model")] = False,
) -> dict:
    """Compare running an open model on a computer you buy with paying a cloud model per call: the cost a month
    each way, the month the computer pays for itself, and whether it keeps up with the load. Use when the
    question is whether to buy hardware for a local model. Needs timed runs of the local model (log_run) and the
    computer's price; electricity comes from EIA or the user's own rate. Not for cloud-only comparisons
    (compare_models or estimate_cost)."""
    try:
        return tools.local_or_cloud(shelf(), local_model=local_model, cloud_models=cloud_models,
                                    input_tokens=input_tokens, output_tokens=output_tokens,
                                    calls_per_month=calls_per_month, hardware_price=hardware_price, watts=watts,
                                    electricity_price=electricity_price, state=state, months=months,
                                    cached_tokens=cached_tokens, local_way=local_way, thinking=thinking)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.tool(annotations=READ_ONLY)
def price_my_usage(
    export: Annotated[str | None, Field(description="Path of a token export on this computer: `ccusage daily --json > f.json`, `ccusage session --json > f.json`, or `codeburn export -f json -o f.json`")] = None,
    mix: Annotated[list[dict] | None, Field(description="Instead of a file: token mixes as {model, date, input, output, cache_read, cache_write, session?}", min_length=1, max_length=5000)] = None,
    task: Annotated[Task | None, Field(description="The kind of work the sessions were (default: codeburn's categories, else coding)")] = None,
    compare: Annotated[list[str] | None, Field(description="Two models to test against each other on the same sessions", min_length=2, max_length=2)] = None,
    limit: Annotated[int, Field(description="How many models to list in every_model (the cheapest first)", ge=1, le=200)] = 25,
) -> dict:
    """Price the user's own past coding agent usage, from a ccusage or codeburn export, on every rated model:
    each session at the price of its day, the models that keep the rating and cost less, a 95% range for the cost
    per session, and whether two models differ for real or the data cannot tell. Use when a usage export (or a
    list of token mixes) exists and the question is what the same work would have cost elsewhere. Not for a
    future workload (estimate_cost) or for a prompt (suggest_for_project). Reads token counts, names and dates
    only; nothing leaves the computer."""
    try:
        return tools.price_my_usage(shelf(), export=export, mix=mix, task=task, compare=compare, limit=limit)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.resource("llmledger://snapshot", mime_type="application/json")
def snapshot() -> dict:
    """What the plug-in knows today: data dates, how many models and rated tasks, and the sources."""
    return tools.snapshot(shelf())


@mcp.prompt
def pick_a_model(work: str) -> str:
    """Pick a model for a piece of work, with its cost and effort."""
    return ("Use the llmledger tools to pick an AI model for this work:\n\n" + work + "\n\n"
            "1. Call suggest_for_project with the work as the prompt.\n"
            "2. Call compare_models with its three picks and the task it returned.\n"
            "3. Answer in five lines or fewer: the pick, its cost per task, the effort level, the runner up and why, "
            "and the credits line.")


def main():
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
