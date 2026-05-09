"""共享 fixtures"""
import pytest
from datetime import datetime

from models.article import Article, Language


@pytest.fixture
def sample_articles():
    return [
        Article(
            title="AI breakthrough in 2026",
            url="https://example.com/1",
            content="Major AI research breakthrough announced today...",
            source="TestSource",
            language=Language.EN,
            published_at=datetime.now(),
        ),
        Article(
            title="测试新闻标题",
            url="https://example.com/2",
            content="这是一条测试新闻的内容...",
            source="测试来源",
            language=Language.ZH,
            published_at=datetime.now(),
        ),
    ]


@pytest.fixture
def test_dsn():
    import os
    return os.getenv("TEST_PG_DSN", "postgresql://postgres:postgres@localhost:5432/logos_test")


@pytest.fixture
def mock_embedding_client():
    class FakeEmbedding:
        def embed(self, texts):
            return [[0.1] * 1536 for _ in texts]

    return FakeEmbedding()


@pytest.fixture
def mock_llm_client():
    class FakeLLM:
        def generate(self, system_prompt, user_message):
            return "这是一个模拟的 LLM 回答。"

        def generate_stream(self, system_prompt, user_message):
            for word in "这是 一个 模拟的 流式 回答".split():
                yield word

    return FakeLLM()
