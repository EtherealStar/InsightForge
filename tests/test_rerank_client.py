"""Rerank 客户端测试。"""

from unittest.mock import MagicMock

import pytest
import requests

from core.exceptions import RerankError
from infrastructure.rerank_client import OpenAICompatibleRerankClient


def test_rerank_success(monkeypatch):
    client = OpenAICompatibleRerankClient(
        api_key="k",
        base_url="https://api.example.com/v1",
        model="rerank-v1",
    )

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "results": [
            {"index": 1, "relevance_score": 0.3},
            {"index": 0, "relevance_score": 0.9},
        ]
    }
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: response)

    results = client.rerank("ai", ["doc1", "doc2"])
    assert [item["index"] for item in results] == [0, 1]


def test_rerank_raises_core_rerank_error(monkeypatch):
    client = OpenAICompatibleRerankClient(
        api_key="k",
        base_url="https://api.example.com/v1",
        model="rerank-v1",
    )
    monkeypatch.setattr("core.retry.time.sleep", lambda _: None)

    def _raise(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "post", _raise)

    with pytest.raises(RerankError):
        client.rerank("ai", ["doc1"])
