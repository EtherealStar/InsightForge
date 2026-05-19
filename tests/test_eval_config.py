"""Tests for evals/config.py."""

from __future__ import annotations

import sys
import types
import warnings


def _install_fake_eval_modules(monkeypatch, captured: dict):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class FakeWrapper:
        def __init__(self, llm, **kwargs):
            self.llm = llm
            self.kwargs = kwargs

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI),
    )
    monkeypatch.setitem(
        sys.modules,
        "ragas.llms",
        types.SimpleNamespace(LangchainLLMWrapper=FakeWrapper),
    )
    monkeypatch.delitem(sys.modules, "evals.llm_compat", raising=False)


def _install_fake_rerank_module(monkeypatch, captured: dict):
    class FakeRerankClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "infrastructure.rerank_client",
        types.SimpleNamespace(OpenAICompatibleRerankClient=FakeRerankClient),
    )


def test_create_judge_llm_uses_config_only(monkeypatch):
    captured = {}
    _install_fake_eval_modules(monkeypatch, captured)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")
    monkeypatch.setenv("LLM_API_KEY", "from-env-llm")

    from evals import config as eval_config

    wrapper = eval_config.create_judge_llm(
        {
            "judge_llm": {
                "model": "judge-model",
                "base_url": "https://example.com/v1",
                "api_key": "from-config",
            }
        }
    )

    assert wrapper.llm is not None
    assert captured["api_key"] == "from-config"
    assert captured["model"] == "judge-model"
    assert captured["base_url"] == "https://example.com/v1"
    assert wrapper.kwargs["bypass_n"] is True


def test_create_judge_llm_reads_api_key_env(monkeypatch):
    captured = {}
    _install_fake_eval_modules(monkeypatch, captured)

    monkeypatch.setenv("INLINE_KEY_IN_CONFIG", "from-env-key")

    from evals import config as eval_config

    wrapper = eval_config.create_judge_llm(
        {
            "judge_llm": {
                "model": "judge-model",
                "base_url": "https://example.com/v1",
                "api_key_env": "INLINE_KEY_IN_CONFIG",
            }
        }
    )

    assert wrapper.llm is not None
    assert captured["api_key"] == "from-env-key"
    assert wrapper.kwargs["bypass_n"] is True


def test_create_judge_llm_accepts_inline_key_in_api_key_env(monkeypatch):
    captured = {}
    _install_fake_eval_modules(monkeypatch, captured)

    from evals import config as eval_config

    wrapper = eval_config.create_judge_llm(
        {
            "judge_llm": {
                "model": "judge-model",
                "base_url": "https://example.com/v1",
                "api_key_env": "sk-inline-key-in-config",
            }
        }
    )

    assert wrapper.llm is not None
    assert captured["api_key"] == "sk-inline-key-in-config"
    assert wrapper.kwargs["bypass_n"] is True


def test_create_judge_llm_raises_for_missing_env_key(monkeypatch):
    _install_fake_eval_modules(monkeypatch, {})

    from evals import config as eval_config

    try:
        eval_config.create_judge_llm(
            {
                "judge_llm": {
                    "model": "judge-model",
                    "base_url": "https://example.com/v1",
                    "api_key_env": "MISSING_JUDGE_KEY",
                }
            }
        )
    except ValueError as exc:
        assert "MISSING_JUDGE_KEY" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_compatible_chat_openai_sanitizes_nested_token_usage(monkeypatch):
    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def _combine_llm_outputs(self, llm_outputs):
            return {"token_usage": llm_outputs[0]["token_usage"]}

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI),
    )
    monkeypatch.delitem(sys.modules, "evals.llm_compat", raising=False)

    from evals.llm_compat import CompatibleChatOpenAI

    llm = object.__new__(CompatibleChatOpenAI)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        combined = llm._combine_llm_outputs(
            [
                {
                    "token_usage": {
                        "prompt_tokens": 5,
                        "completion_tokens_details": {
                            "reasoning_tokens": None,
                            "accepted_prediction_tokens": 2,
                        },
                        "cached_tokens": None,
                    }
                }
            ]
        )

    assert caught == []
    assert combined == {
        "token_usage": {
            "prompt_tokens": 5,
            "completion_tokens_details": {
                "accepted_prediction_tokens": 2,
            },
        }
    }


def test_create_eval_rerank_client_uses_inline_api_key(monkeypatch):
    captured = {}
    _install_fake_rerank_module(monkeypatch, captured)

    monkeypatch.setenv("RERANK_API_KEY", "from-env")

    from evals import config as eval_config

    client = eval_config.create_eval_rerank_client(
        {
            "reranker": {
                "enabled": True,
                "model": "rerank-model",
                "base_url": "https://example.com/v1",
                "api_key": "from-config",
            }
        }
    )

    assert client is not None
    assert captured["api_key"] == "from-config"
    assert captured["model"] == "rerank-model"
    assert captured["base_url"] == "https://example.com/v1"


def test_create_eval_rerank_client_rejects_api_key_env(monkeypatch):
    _install_fake_rerank_module(monkeypatch, {})

    from evals import config as eval_config

    try:
        eval_config.create_eval_rerank_client(
            {
                "reranker": {
                    "enabled": True,
                    "model": "rerank-model",
                    "base_url": "https://example.com/v1",
                    "api_key_env": "RERANK_API_KEY",
                }
            }
        )
    except ValueError as exc:
        assert "reranker 不支持 api_key_env" in str(exc)
    else:
        raise AssertionError("expected ValueError")
