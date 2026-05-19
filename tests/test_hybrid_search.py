"""Hybrid search tests for Qdrant child points + PostgreSQL parent chunks."""

from unittest.mock import MagicMock

from infrastructure.hybrid_search_service import HybridSearchService
from infrastructure.keyword_search_service import KeywordSearchService
from models.document import (
    ChildChunkPoint,
    ChildChunkSearchResult,
    ParentDocumentChunk,
)


def _parent(pid: str, content: str = "") -> ParentDocumentChunk:
    return ParentDocumentChunk(
        parent_chunk_id=pid,
        document_id="doc",
        content=content or f"parent {pid}",
        token_count=10,
        child_point_ids=[f"{pid}:c:0"],
        doc_name="Doc",
    )


def _child_result(pid: str, score: float = 0.9) -> ChildChunkSearchResult:
    return ChildChunkSearchResult(
        chunk=ChildChunkPoint(
            point_id=f"{pid}:c:0",
            document_id="doc",
            parent_chunk_id=pid,
            content=f"child {pid}",
            token_count=5,
            chunk_index=0,
        ),
        relevance_score=score,
    )


def test_keyword_search_wraps_parent_results():
    document_store = MagicMock()
    document_store.search_parent_chunks_by_keyword.return_value = [(_parent("p1"), 0.7)]

    filters = {"competitor_ids": [1], "document_type": "article"}
    results = KeywordSearchService(document_store).search("query", top_k=3, filters=filters)

    assert len(results) == 1
    assert results[0].chunk.parent_chunk_id == "p1"
    assert results[0].match_type == "keyword"
    document_store.search_parent_chunks_by_keyword.assert_called_once_with(
        query="query",
        top_k=3,
        filters=filters,
    )


def test_hybrid_search_fuses_qdrant_and_keyword_results():
    vector_index = MagicMock()
    vector_index.search_child_chunks.return_value = [
        _child_result("p1"),
        _child_result("p2"),
    ]
    embedding_client = MagicMock()
    embedding_client.embed.return_value = [[0.1, 0.2, 0.3]]
    document_store = MagicMock()
    document_store.search_parent_chunks_by_keyword.return_value = [(_parent("p2"), 0.8)]
    document_store.get_parent_chunks_by_ids.return_value = [_parent("p1"), _parent("p2")]

    service = HybridSearchService(
        vector_index=vector_index,
        embedding_client=embedding_client,
        document_store=document_store,
        keyword_search_service=KeywordSearchService(document_store),
    )
    filters = {"competitor_ids": [1], "document_type": "article"}
    results = service.search("query", top_k=2, filters=filters)

    assert [r.parent_chunk.parent_chunk_id for r in results] == ["p2", "p1"]
    assert results[0].match_sources == ["semantic", "keyword"]
    vector_index.search_child_chunks.assert_called_once_with(
        query_embedding=[0.1, 0.2, 0.3],
        top_k=6,
        filters=filters,
    )
    document_store.search_parent_chunks_by_keyword.assert_called_once_with(
        query="query",
        top_k=20,
        filters=filters,
    )
    document_store.get_parent_chunks_by_ids.assert_called_once()


def test_hybrid_search_vector_only_fallback():
    vector_index = MagicMock()
    vector_index.search_child_chunks.return_value = [_child_result("p1")]
    embedding_client = MagicMock()
    embedding_client.embed.return_value = [[0.1, 0.2, 0.3]]
    document_store = MagicMock()
    document_store.search_parent_chunks_by_keyword.side_effect = RuntimeError("db")
    document_store.get_parent_chunks_by_ids.return_value = [_parent("p1")]

    service = HybridSearchService(
        vector_index=vector_index,
        embedding_client=embedding_client,
        document_store=document_store,
        keyword_search_service=KeywordSearchService(document_store),
    )

    results = service.search("query", top_k=1)

    assert len(results) == 1
    assert results[0].parent_chunk.parent_chunk_id == "p1"
    assert results[0].match_sources == ["semantic"]
