"""NewsAPI 路由测试。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from delivery.api.newsapi_router import SaveArticleRequest, save_article
from models.article import Article, Language


def _build_request(published_at: str = "2026-01-02T03:04:05Z") -> SaveArticleRequest:
    return SaveArticleRequest(
        title="Title",
        url="https://example.com/news",
        content="content",
        source_name="source",
        language="en",
        published_at=published_at,
    )


def test_save_article_success_and_vectorized(monkeypatch):
    store = MagicMock()
    calls = []
    store.save_articles.return_value = 1
    store.get_articles.return_value = [
        Article(
            id=1,
            title="Title",
            url="https://example.com/news",
            content="content",
            source="source",
            language=Language.EN,
        )
    ]
    store.save_parent_chunks.side_effect = lambda parents: calls.append("parents") or len(parents)
    embedding_client = MagicMock()
    embedding_client.embed.side_effect = lambda texts: calls.append("embeddings") or [[0.1, 0.2]]
    vector_store = MagicMock()
    vector_store.add_chunks.side_effect = (
        lambda chunks, embeddings: calls.append("children") or len(chunks)
    )

    # Mock chunking service
    from models.chunk import Chunk, ParentChunk
    mock_child = Chunk(
        chunk_id="1_c0", article_id=1, parent_chunk_id="1_p0",
        content="content", token_count=10, doc_name="Title",
    )
    mock_parent = ParentChunk(
        parent_chunk_id="1_p0", article_id=1, content="content",
        token_count=10, child_chunk_ids=["1_c0"], doc_name="Title",
    )
    chunking_service = MagicMock()
    chunking_service.chunk_article.return_value = ([mock_child], [mock_parent])

    mgr = SimpleNamespace(
        article_store=store,
        embedding_client=embedding_client,
        vector_store=vector_store,
        chunking_service=chunking_service,
    )
    monkeypatch.setattr("core.config_manager.get_config_manager", lambda: mgr)

    result = save_article(_build_request())

    assert result["status"] == "ok"
    assert result["saved_count"] == 1
    assert result["vectorized"] is True
    assert calls == ["parents", "embeddings", "children"]
    store.mark_embedded.assert_called_once_with([1])


def test_save_article_invalid_date_fallback(monkeypatch):
    store = MagicMock()
    store.save_articles.return_value = 1
    store.get_articles.return_value = []
    mgr = SimpleNamespace(
        article_store=store,
        embedding_client=MagicMock(),
        vector_store=MagicMock(),
        chunking_service=MagicMock(),
    )
    monkeypatch.setattr("core.config_manager.get_config_manager", lambda: mgr)

    result = save_article(_build_request("invalid-date"))

    assert result["status"] == "ok"
    assert result["saved_count"] == 1


def test_save_article_duplicate(monkeypatch):
    store = MagicMock()
    store.save_articles.return_value = 0
    mgr = SimpleNamespace(
        article_store=store,
        embedding_client=MagicMock(),
        vector_store=MagicMock(),
        chunking_service=MagicMock(),
    )
    monkeypatch.setattr("core.config_manager.get_config_manager", lambda: mgr)

    result = save_article(_build_request())
    assert result == {"status": "ok", "message": "该文章已经存在"}
