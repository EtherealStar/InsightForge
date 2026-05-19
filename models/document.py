"""Document-first knowledge models for parent-child RAG.

PostgreSQL owns source documents, parent chunks, keyword indexes, and Qdrant
point status. Qdrant owns child chunk vectors and child chunk payloads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


def new_document_id() -> str:
    return str(uuid4())


@dataclass
class SourceDocument:
    """Unified source document for RSS, web, upload, manual, and API inputs."""

    document_id: str
    title: str
    content: str
    source_type: str = "web"
    document_type: str = "article"
    url: str = ""
    canonical_url: str = ""
    language: str = ""
    content_hash: str = ""
    competitor_ids: list[int] = field(default_factory=list)
    product_ids: list[int] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    published_at: datetime | None = None
    created_at: datetime | None = None
    blob_id: str | None = None
    parse_status: str = "pending"


@dataclass
class ChildChunkPoint:
    """Child chunk payload stored in Qdrant with its embedding vector."""

    point_id: str
    document_id: str
    parent_chunk_id: str
    content: str
    token_count: int
    chunk_index: int
    heading_path: list[str] = field(default_factory=list)
    doc_name: str = ""
    source: str = ""
    url: str = ""
    source_type: str = "web"
    document_type: str = "article"
    competitor_ids: list[int] = field(default_factory=list)
    product_ids: list[int] = field(default_factory=list)
    language: str = ""
    content_hash: str = ""
    published_at: datetime | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParentDocumentChunk:
    """Parent chunk stored in PostgreSQL and used as LLM context."""

    parent_chunk_id: str
    document_id: str
    content: str
    token_count: int
    child_point_ids: list[str] = field(default_factory=list)
    heading_path: list[str] = field(default_factory=list)
    doc_name: str = ""
    source: str = ""
    url: str = ""
    source_type: str = "web"
    document_type: str = "article"
    competitor_ids: list[int] = field(default_factory=list)
    product_ids: list[int] = field(default_factory=list)
    language: str = ""
    published_at: datetime | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChildChunkSearchResult:
    """Vector search result for a child chunk point from Qdrant."""

    chunk: ChildChunkPoint
    parent_chunk: ParentDocumentChunk | None = None
    relevance_score: float = 0.0
    match_type: str = "semantic"


@dataclass
class HybridDocumentSearchResult:
    """Hybrid search result after RRF and parent chunk recall."""

    parent_chunk: ParentDocumentChunk
    rrf_score: float = 0.0
    match_sources: list[str] = field(default_factory=list)
    semantic_rank: int | None = None
    keyword_rank: int | None = None
