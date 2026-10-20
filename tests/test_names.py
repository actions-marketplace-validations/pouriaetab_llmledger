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
    ("voyage/voyage-3-large", ("voyage", "voyage-3-large")),
    ("happyhorse/happyhorse-1.0", ("other", "happyhorse-1.0")),
])
def test_req_s18_naming_rules(key, expected):
    assert canonical(key) == expected


@pytest.mark.parametrize("key, expected", [
    ("databricks/databricks-claude-opus-4-1", ("anthropic", "claude-opus-4.1")),
    ("gradient_ai/openai-gpt-4o", ("openai", "gpt-4o")),
    ("azure_ai/Meta-Llama-3.1-70B-Instruct", ("meta", "llama-3.1-70b-instruct")),
    ("bedrock/us-east-1/deepseek.v3.2", ("deepseek", "v3.2")),
    ("azure_ai/FW-DeepSeek-V4-Flash", ("deepseek", "deepseek-v4-flash")),
    ("ft:gpt-4o-2024-08-06", ("openai", "gpt-4o")),
    ("bedrock/us-east-1/zai.glm-5", ("zhipu", "glm-5")),
    ("tencent/deepseek-v4-flash", ("deepseek", "deepseek-v4-flash")),
    ("snowflake/mistral-large2", ("mistral", "mistral-large2")),
    ("fireworks_ai/accounts/fireworks/models/code-llama-34b", ("meta", "code-llama-34b")),
    ("deepinfra/ByteDance/Seed-2.0-pro", ("bytedance", "seed-2.0-pro")),
    ("fal_ai/fal-ai/flux-pro/v1.1", ("black-forest-labs", "flux-pro/v1.1")),
])
def test_req_s18_a_vendor_in_the_name_is_not_the_model(key, expected):
    assert canonical(key) == expected


def test_req_s18_vertex_default_alias_is_the_same_model():
    assert canonical("vertex_ai/claude-sonnet-4-6@default") == canonical("claude-sonnet-4-6")


def test_req_s18_newer_makers_are_named():
    assert canonical("xiaomi_mimo/mimo-v2.6-pro")[0] == "xiaomi"
    assert canonical("meta/muse-spark-1.2")[0] == "meta"
