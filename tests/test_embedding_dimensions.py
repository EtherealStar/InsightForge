"""Embedding dimensions configuration tests."""

from __future__ import annotations

import sys
import types


def test_embedding_client_sends_dimensions(monkeypatch):
    calls = []

    class FakeData:
        def __init__(self, index, embedding):
            self.index = index
            self.embedding = embedding

    class FakeEmbeddings:
        def create(self, **kwargs):
            calls.append(kwargs)
            return types.SimpleNamespace(
                data=[
                    FakeData(1, [0.2, 0.3]),
                    FakeData(0, [0.0, 0.1]),
                ]
            )

    class FakeOpenAI:
        def __init__(self, api_key, base_url):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setitem(
        sys.modules,
        "openai",
        types.SimpleNamespace(OpenAI=FakeOpenAI),
    )

    from infrastructure.embedding_client import OpenAICompatibleEmbeddingClient

    client = OpenAICompatibleEmbeddingClient(
        api_key="test",
        base_url="https://example.com/v1",
        model="embedding-model",
        dimensions=1024,
    )

    assert client.embed(["a", "b"]) == [[0.0, 0.1], [0.2, 0.3]]
    assert calls == [
        {
            "model": "embedding-model",
            "input": ["a", "b"],
            "dimensions": 1024,
        }
    ]


def test_eval_embeddings_uses_configured_dimensions(monkeypatch):
    captured = {}

    class FakeOpenAIEmbeddings:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class FakeWrapper:
        def __init__(self, embeddings):
            self.embeddings = embeddings

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        types.SimpleNamespace(OpenAIEmbeddings=FakeOpenAIEmbeddings),
    )
    monkeypatch.setitem(
        sys.modules,
        "ragas.embeddings",
        types.SimpleNamespace(LangchainEmbeddingsWrapper=FakeWrapper),
    )

    from evals.config import create_judge_embeddings

    wrapper = create_judge_embeddings(
        {
            "judge_embedding": {
                "model": "judge-embedding",
                "base_url": "https://example.com/v1",
                "api_key": "test",
                "dimensions": 768,
            }
        }
    )

    assert isinstance(wrapper, FakeWrapper)
    assert captured["dimensions"] == 768
    assert captured["model"] == "judge-embedding"
