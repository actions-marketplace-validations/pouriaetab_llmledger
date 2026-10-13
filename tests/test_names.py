import pytest

from llmledger.names import canonical


@pytest.mark.parametrize("key", [
    "anthropic.claude-3-5-sonnet-20240620-v1:0",
    "eu.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "vercel_ai_gateway/anthropic/claude-3.5-sonnet",
    "snowflake/claude-3-5-sonnet",
    "vertex_ai/claude-3-5-sonnet@20240620",
])
def test_req_s18_one_model_on_many_hosts_is_grouped(key):
    assert canonical(key) == ("anthropic", "claude-3.5-sonnet")


@pytest.mark.parametrize("key, expected", [
    ("azure/eu/gpt-4o-2024-08-06", ("openai", "gpt-4o")),
    ("gpt-3.5-turbo-0125", ("openai", "gpt-3.5-turbo")),
    ("anthropic.claude-v2:1", ("anthropic", "claude-v2:1")),
    ("meta.llama3-1-70b-instruct-v1:0", ("meta", "llama-3.1-70b-instruct")),
    ("fireworks_ai/glm-4p7", ("zhipu", "glm-4.7")),
    ("moonshot/moonshot-v1-8k", ("moonshot", "moonshot-v1-8k")),
    ("voyage/voyage-3-large", ("other", "voyage-3-large")),
])
def test_req_s18_naming_rules(key, expected):
    assert canonical(key) == expected
