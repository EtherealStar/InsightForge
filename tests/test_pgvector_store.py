"""PgVectorStore integration tests."""

import os

import pytest

from infrastructure.pgvector_store import PgVectorStore
from models.chunk import Chunk

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_PG_DSN"),
    reason="Requires PostgreSQL instance with pgvector extension",
)


def test_pgvector_add_search_delete(test_dsn):
    store = PgVectorStore(test_dsn, vector_size=1536)
    chunk = Chunk(
        chunk_id="test_pgvector_c1",
        article_id=999001,
        parent_chunk_id="test_pgvector_p1",
        content="人工智能新闻",
        token_count=10,
        doc_name="测试文档",
        heading_path=["科技"],
        chunk_index=0,
        source="test",
        url="https://example.com/vector",
    )

    try:
        embedding = [1.0] + [0.0] * 1535
        assert store.add_chunks([chunk], [embedding]) == 1
        results = store.search_chunks(embedding, top_k=1)

        assert len(results) == 1
        assert results[0].chunk.chunk_id == chunk.chunk_id
        assert results[0].chunk.parent_chunk_id == chunk.parent_chunk_id
        assert results[0].match_type == "semantic"
    finally:
        store.delete_by_article_ids([999001])


def test_pgvector_rejects_dimension_mismatch(test_dsn):
    store = PgVectorStore(test_dsn, vector_size=1536)
    chunk = Chunk(
        chunk_id="test_pgvector_bad_dim",
        article_id=999002,
        parent_chunk_id="test_pgvector_p2",
        content="bad dim",
        token_count=2,
        doc_name="测试文档",
    )

    assert store.add_chunks([chunk], [[1.0, 0.0]]) == 0
