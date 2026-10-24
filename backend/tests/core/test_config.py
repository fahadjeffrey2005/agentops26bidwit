import pytest
from pydantic import ValidationError

from bidwit.core.config import load_settings


def test_defaults():
    s = load_settings({})
    assert s.llm == "on" and s.max_upload_mb == 20 and s.llm_chain.startswith("groq:openai/gpt-oss-120b")


def test_bad_backend_fails_fast():
    with pytest.raises(ValidationError):
        load_settings({"BIDWIT_LLM": "openai"})


def test_bad_upload_limit_fails_fast():
    with pytest.raises(ValidationError):
        load_settings({"BIDWIT_MAX_UPLOAD_MB": "5000"})


def test_no_secret_fields():
    assert not any("key" in f.lower() or "secret" in f.lower() for f in type(load_settings({})).model_fields)


@pytest.mark.parametrize("chain", ["openai:gpt-4", "groq:", "groq:model; rm -rf /", "gemini:x,,groq:y"])
def test_bad_provider_chain_fails_fast(chain):
    with pytest.raises(ValidationError):
        load_settings({"BIDWIT_LLM_CHAIN": chain})


def test_good_provider_chain():
    s = load_settings({"BIDWIT_LLM_CHAIN": "groq:qwen/qwen3.8-27b, gemini:gemini-3.6-flash", "BIDWIT_LLM_MAX_CALLS": "5"})
    assert s.llm_max_calls == 5
