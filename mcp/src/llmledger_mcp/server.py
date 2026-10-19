"""llmledger as a plug-in (an MCP server) for Claude and other AI apps.

Five tools answer "which model, and what will it cost?" from the same data as the llmledger
page: LiteLLM's price catalogue (MIT), Arena's ratings (CC BY 4.0), and every price change
since 2023 with how likely a price is to change next. Runs on the user's own computer over
stdio; reads the day's data.json, cached for a day. The answers themselves are in tools.py,
which the Agent Skill (skills/llmledger) runs too.
"""
import time
from typing import Annotated, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from llmledger_mcp import __version__, data, logic, tools

Task = Literal[tuple(logic.TASKS)]
Pay = Literal[tools.PAYS]
Need = Literal[tools.NEEDS]
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)

mcp = FastMCP(
    "llmledger",
    instructions=(
        "Which AI model to use, and what it costs. Prices come from LiteLLM's public catalogue, quality from "
        "Arena's votes, and each price's full history from llmledger. Use suggest_for_project for 'which model "
        "for this', compare_models to put 2 to 6 models side by side, estimate_cost for a budget, find_models to "
        "browse, and price_history for one model. Costs and ratings are estimates; pass on the credits line."),
    version=__version__,
)

_SHELF = None


def shelf():
    """The data, loaded once and refreshed after a day."""
    global _SHELF
    if _SHELF is None or time.time() - _SHELF.loaded > data.MAX_AGE:
        _SHELF = data.Shelf(*data.load())
    return _SHELF


@mcp.tool(annotations=READ_ONLY)
def find_models(
    task: Annotated[Task, Field(description="The kind of work, as Arena rates it")] = "overall",
    max_output_price: Annotated[float | None, Field(description="Highest answer price, dollars per 1M tokens", ge=0)] = None,
    min_context: Annotated[int | None, Field(description="Smallest prompt size the model must take, in tokens", ge=0)] = None,
    needs: Annotated[list[Need], Field(description="What the model must be able to do")] = [],
    maker: Annotated[str | None, Field(description="Only this maker, for example anthropic or openai")] = None,
    limit: Annotated[int, Field(ge=1, le=20)] = 5,
) -> dict:
    """The highest rated models for a kind of work that meet the limits, each at its cheapest listing,
    with prices per 1M tokens, Arena rating and prompt size. Unrated models follow, cheapest first."""
    try:
        return tools.find_models(shelf(), task=task, max_output_price=max_output_price, min_context=min_context,
                                 needs=needs, maker=maker, limit=limit)
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
    """Two to six models side by side for a kind of work: rating, prices, cost per task (or plan use), and
    which to pick, with the break-even share of answer tokens for each against the pick."""
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
) -> dict:
    """What a workload costs on each model at its cheapest listing: per call, per day and per 30 days."""
    try:
        return tools.estimate_cost(shelf(), models=models, input_tokens=input_tokens, output_tokens=output_tokens,
                                   cached_tokens=cached_tokens, calls_per_day=calls_per_day)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.tool(annotations=READ_ONLY)
def price_history(
    model: Annotated[str, Field(description="A model name, for example claude-opus-5.5, or one listing such as bedrock/anthropic.claude-opus-5-5")],
) -> dict:
    """Every change to a model's listings since 2023 (prices, retirement dates), and for listings that have not
    changed yet, the chance of a price change, a retirement date or removal in the next 90 days and year."""
    try:
        return tools.price_history(shelf(), model=model)
    except tools.NotFound as error:
        raise ToolError(str(error)) from None


@mcp.tool(annotations=READ_ONLY)
def suggest_for_project(
    prompt: Annotated[str, Field(description="The project's starting prompt, or a description of the work")],
    pay: Annotated[Pay, Field(description="api: dollars; claude or chatgpt: compare within that plan")] = "api",
    answer: Annotated[Literal["short", "medium", "long", "very_long"], Field(description="Typical answer length")] = "medium",
) -> dict:
    """Reads a prompt, guesses its kind of work, and suggests a model and effort level: the best value (the
    cheapest whose rating the votes cannot tell apart from the top), the top rated and the cheapest rated."""
    try:
        return tools.suggest_for_project(shelf(), prompt=prompt, pay=pay, answer=answer)
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
