"""Qdrant vector index for child chunk points."""
from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from core.exceptions import InfrastructureError
from models.document import ChildChunkPoint, ChildChunkSearchResult


class QdrantVectorIndex:
    """Qdrant-backed child chunk vector index."""

    def __init__(
        self,
        url: str,
        api_key: str = "",
        collection_name: str = "insightforge_documents_v1",
        vector_size: int = 1536,
        distance: str = "Cosine",
    ):
        try:
            from qdrant_client import QdrantClient
        except Exception as e:
            raise InfrastructureError(f"qdrant-client is not installed: {e}") from e

        self.collection_name = collection_name
        self.vector_size = vector_size
        self.distance = distance
        try:
            self.client = QdrantClient(
                url=url,
                api_key=api_key or None,
                trust_env=False,
            )
        except Exception as e:
            raise InfrastructureError(f"Qdrant client initialization failed: {e}") from e

    def healthcheck(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            raise InfrastructureError(f"Qdrant healthcheck failed: {e}") from e

    def ensure_collection(self) -> None:
        try:
            existing = {
                c.name for c in self.client.get_collections().collections
            }
            if self.collection_name in existing:
                return
            self._create_collection()
        except InfrastructureError:
            raise
        except Exception as e:
            raise InfrastructureError(f"Qdrant ensure collection failed: {e}") from e

    def recreate_collection(self) -> None:
        try:
            self.client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=self._vector_params(),
            )
        except Exception as e:
            raise InfrastructureError(f"Qdrant recreate collection failed: {e}") from e

    def upsert_child_chunks(
        self, chunks: list[ChildChunkPoint], embeddings: list[list[float]]
    ) -> int:
        if len(chunks) != len(embeddings):
            raise InfrastructureError(
                f"Qdrant upsert count mismatch: {len(chunks)}/{len(embeddings)}"
            )
        for embedding in embeddings:
            if len(embedding) != self.vector_size:
                raise InfrastructureError(
                    f"Qdrant vector dimension mismatch: {len(embedding)} != {self.vector_size}"
                )

        try:
            from qdrant_client.models import PointStruct

            points = [
                PointStruct(
                    id=chunk.point_id,
                    vector=embedding,
                    payload=self._payload(chunk),
                )
                for chunk, embedding in zip(chunks, embeddings)
            ]
            if points:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points,
                    wait=True,
                )
            return len(points)
        except Exception as e:
            raise InfrastructureError(f"Qdrant child chunk upsert failed: {e}") from e

    def search_child_chunks(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[ChildChunkSearchResult]:
        if len(query_embedding) != self.vector_size:
            raise InfrastructureError(
                f"Qdrant query dimension mismatch: {len(query_embedding)} != {self.vector_size}"
            )
        try:
            q_filter = self._build_filter(filters or {})
            if hasattr(self.client, "search"):
                hits = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_embedding,
                    query_filter=q_filter,
                    limit=top_k,
                    with_payload=True,
                )
            else:
                response = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_embedding,
                    query_filter=q_filter,
                    limit=top_k,
                    with_payload=True,
                )
                hits = response.points
            return [
                ChildChunkSearchResult(
                    chunk=self._point_from_payload(str(hit.id), hit.payload or {}),
                    relevance_score=float(hit.score),
                )
                for hit in hits
            ]
        except Exception as e:
            raise InfrastructureError(f"Qdrant child chunk search failed: {e}") from e

    def delete_by_document_ids(self, document_ids: list[str]) -> None:
        if not document_ids:
            return
        self._delete_by_filter({"document_id": document_ids})

    def delete_by_point_ids(self, point_ids: list[str]) -> None:
        if not point_ids:
            return
        try:
            from qdrant_client.models import PointIdsList

            self.client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=point_ids),
                wait=True,
            )
        except Exception as e:
            raise InfrastructureError(f"Qdrant delete by point ids failed: {e}") from e

    def _create_collection(self) -> None:
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=self._vector_params(),
        )

    def _vector_params(self):
        from qdrant_client.models import Distance, VectorParams

        distance = getattr(Distance, self.distance.upper(), Distance.COSINE)
        return VectorParams(size=self.vector_size, distance=distance)

    def _delete_by_filter(self, filters: dict[str, Any]) -> None:
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=self._build_filter(filters),
                wait=True,
            )
        except Exception as e:
            raise InfrastructureError(f"Qdrant delete by filter failed: {e}") from e

    @staticmethod
    def _payload(chunk: ChildChunkPoint) -> dict[str, Any]:
        return {
            "document_id": chunk.document_id,
            "parent_chunk_id": chunk.parent_chunk_id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "content_hash": chunk.content_hash,
            "token_count": chunk.token_count,
            "heading_path": chunk.heading_path,
            "doc_name": chunk.doc_name,
            "source": chunk.source,
            "url": chunk.url,
            "source_type": chunk.source_type,
            "document_type": chunk.document_type,
            "competitor_ids": chunk.competitor_ids,
            "product_ids": chunk.product_ids,
            "language": chunk.language,
            "published_at": chunk.published_at.isoformat() if chunk.published_at else None,
            "created_at": chunk.created_at.isoformat() if chunk.created_at else datetime.now(UTC).isoformat(),
            "metadata": chunk.metadata,
        }

    @staticmethod
    def _point_from_payload(point_id: str, payload: dict[str, Any]) -> ChildChunkPoint:
        return ChildChunkPoint(
            point_id=point_id,
            document_id=payload.get("document_id", ""),
            parent_chunk_id=payload.get("parent_chunk_id", ""),
            content=payload.get("content", ""),
            token_count=int(payload.get("token_count") or 0),
            chunk_index=int(payload.get("chunk_index") or 0),
            heading_path=list(payload.get("heading_path") or []),
            doc_name=payload.get("doc_name", ""),
            source=payload.get("source", ""),
            url=payload.get("url", ""),
            source_type=payload.get("source_type", "web"),
            document_type=payload.get("document_type", "article"),
            competitor_ids=list(payload.get("competitor_ids") or []),
            product_ids=list(payload.get("product_ids") or []),
            language=payload.get("language", ""),
            content_hash=payload.get("content_hash", ""),
            metadata=payload.get("metadata") or {},
        )

    @staticmethod
    def _build_filter(filters: dict[str, Any]):
        if not filters:
            return None
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue
        try:
            from qdrant_client.models import DatetimeRange as RangeType
        except Exception:
            from qdrant_client.models import Range as RangeType

        must = []
        should = []
        for key, value in filters.items():
            if value is None:
                continue
            if key in {"date_from", "date_to"}:
                continue
            if isinstance(value, (list, tuple, set)):
                if not value:
                    continue
                must.append(
                    FieldCondition(
                        key=key,
                        match=MatchAny(any=list(value)),
                    )
                )
            else:
                must.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value),
                    )
                )

        if filters.get("date_from") or filters.get("date_to"):
            range_kwargs: dict[str, Any] = {}
            if filters.get("date_from"):
                range_kwargs["gte"] = filters["date_from"]
            if filters.get("date_to"):
                range_kwargs["lte"] = filters["date_to"]
            range_value = RangeType(**range_kwargs)
            should.extend(
                [
                    FieldCondition(key="published_at", range=range_value),
                    FieldCondition(key="created_at", range=range_value),
                ]
            )

        return Filter(must=must, should=should) if must or should else None
