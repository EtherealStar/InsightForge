"""PostgreSQL authoritative store for source documents and parent chunks."""
from __future__ import annotations

import json
from typing import Any

import jieba
import psycopg2
import structlog
from psycopg2.extras import DictCursor

from core.exceptions import StoreError
from models.document import ChildChunkPoint, ParentDocumentChunk, SourceDocument

logger = structlog.get_logger(__name__)


class PostgresDocumentStore:
    """Document-first PostgreSQL store.

    This store does not create DDL. Schema is managed by migrations.
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.healthcheck()

    def _get_conn(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=DictCursor)
        conn.autocommit = True
        return conn

    def healthcheck(self) -> bool:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return True
        except Exception as e:
            raise StoreError(f"PostgreSQL document store unavailable: {e}") from e

    def save_document(self, document: SourceDocument) -> SourceDocument:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_documents (
                        id, blob_id, url, canonical_url, source_type, document_type,
                        title, content, content_hash, language, metadata,
                        competitor_ids, product_ids, parse_status, published_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        blob_id = EXCLUDED.blob_id,
                        url = EXCLUDED.url,
                        canonical_url = EXCLUDED.canonical_url,
                        source_type = EXCLUDED.source_type,
                        document_type = EXCLUDED.document_type,
                        title = EXCLUDED.title,
                        content = EXCLUDED.content,
                        content_hash = EXCLUDED.content_hash,
                        language = EXCLUDED.language,
                        metadata = EXCLUDED.metadata,
                        competitor_ids = EXCLUDED.competitor_ids,
                        product_ids = EXCLUDED.product_ids,
                        parse_status = EXCLUDED.parse_status,
                        published_at = EXCLUDED.published_at,
                        updated_at = NOW()
                    """,
                    (
                        document.document_id,
                        document.blob_id,
                        document.url,
                        document.canonical_url,
                        document.source_type,
                        document.document_type,
                        document.title,
                        document.content,
                        document.content_hash,
                        document.language,
                        json.dumps(document.metadata, ensure_ascii=False),
                        json.dumps(document.competitor_ids, ensure_ascii=False),
                        json.dumps(document.product_ids, ensure_ascii=False),
                        document.parse_status,
                        document.published_at,
                    ),
                )
        return document

    def get_document(self, document_id: str) -> SourceDocument | None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM source_documents WHERE id = %s", (document_id,))
                row = cur.fetchone()
        return self._row_to_document(row) if row else None

    def list_documents(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SourceDocument]:
        filters = filters or {}
        conditions = []
        params: list[Any] = []
        for key in ("source_type", "document_type", "parse_status"):
            if key in filters and filters[key] is not None:
                conditions.append(f"{key} = %s")
                params.append(filters[key])
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.extend([limit, offset])
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT * FROM source_documents
                    {where}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
        return [self._row_to_document(row) for row in rows]

    def update_parse_status(
        self, document_id: str, status: str, error: dict[str, Any] | None = None
    ) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE source_documents
                    SET parse_status = %s, parse_error = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        status,
                        json.dumps(error or {}, ensure_ascii=False),
                        document_id,
                    ),
                )

    def save_parent_chunks(self, parent_chunks: list[ParentDocumentChunk]) -> int:
        if not parent_chunks:
            return 0
        count = 0
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for pc in parent_chunks:
                    segmented = self._segment_text(pc.content)
                    cur.execute(
                        """
                        INSERT INTO document_parent_chunks (
                            parent_chunk_id, document_id, content, token_count,
                            child_point_ids, heading_path, doc_name, source, url,
                            source_type, document_type, competitor_ids, product_ids,
                            language, published_at, metadata, search_vector
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                to_tsvector('simple', %s))
                        ON CONFLICT (parent_chunk_id) DO UPDATE SET
                            content = EXCLUDED.content,
                            token_count = EXCLUDED.token_count,
                            child_point_ids = EXCLUDED.child_point_ids,
                            heading_path = EXCLUDED.heading_path,
                            search_vector = EXCLUDED.search_vector,
                            updated_at = NOW()
                        """,
                        (
                            pc.parent_chunk_id,
                            pc.document_id,
                            pc.content,
                            pc.token_count,
                            json.dumps(pc.child_point_ids, ensure_ascii=False),
                            json.dumps(pc.heading_path, ensure_ascii=False),
                            pc.doc_name,
                            pc.source,
                            pc.url,
                            pc.source_type,
                            pc.document_type,
                            json.dumps(pc.competitor_ids, ensure_ascii=False),
                            json.dumps(pc.product_ids, ensure_ascii=False),
                            pc.language,
                            pc.published_at,
                            json.dumps(pc.metadata, ensure_ascii=False),
                            segmented,
                        ),
                    )
                    count += 1
        return count

    def get_parent_chunks_by_ids(
        self, parent_chunk_ids: list[str]
    ) -> list[ParentDocumentChunk]:
        if not parent_chunk_ids:
            return []
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM document_parent_chunks
                    WHERE parent_chunk_id = ANY(%s)
                    """,
                    (parent_chunk_ids,),
                )
                rows = cur.fetchall()
        parent_map = {row["parent_chunk_id"]: self._row_to_parent_chunk(row) for row in rows}
        return [parent_map[pid] for pid in parent_chunk_ids if pid in parent_map]

    def list_parent_chunks(self, document_id: str) -> list[ParentDocumentChunk]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM document_parent_chunks
                    WHERE document_id = %s
                    ORDER BY created_at ASC, parent_chunk_id ASC
                    """,
                    (document_id,),
                )
                rows = cur.fetchall()
        return [self._row_to_parent_chunk(row) for row in rows]

    def search_parent_chunks_by_keyword(
        self,
        query: str,
        top_k: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[ParentDocumentChunk, float]]:
        segmented = self._segment_text(query)
        terms = [t.strip() for t in segmented.split() if t.strip()]
        if not terms:
            return []
        tsquery = " | ".join(terms)
        where = ["pc.search_vector @@ query"]
        params: list[Any] = [tsquery]
        filters = filters or {}
        competitor_ids = filters.get("competitor_ids")
        if competitor_ids:
            where.append(
                """(
                    EXISTS (
                        SELECT 1 FROM jsonb_array_elements_text(pc.competitor_ids) AS cid(value)
                        WHERE cid.value = ANY(%s)
                    )
                    OR EXISTS (
                        SELECT 1 FROM jsonb_array_elements_text(sd.competitor_ids) AS cid(value)
                        WHERE cid.value = ANY(%s)
                    )
                )"""
            )
            competitor_values = [str(v) for v in competitor_ids]
            params.extend([competitor_values, competitor_values])
        document_type = filters.get("document_type")
        if document_type:
            where.append("sd.document_type = %s")
            params.append(document_type)
        date_from = filters.get("date_from")
        if date_from:
            where.append("COALESCE(sd.published_at, sd.created_at) >= %s::date")
            params.append(date_from)
        date_to = filters.get("date_to")
        if date_to:
            where.append("COALESCE(sd.published_at, sd.created_at) < (%s::date + INTERVAL '1 day')")
            params.append(date_to)
        params.append(top_k)
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        f"""
                        SELECT pc.*, ts_rank(pc.search_vector, query) AS rank
                        FROM document_parent_chunks pc
                        JOIN source_documents sd ON sd.id = pc.document_id,
                             to_tsquery('simple', %s) AS query
                        WHERE {" AND ".join(where)}
                        ORDER BY rank DESC
                        LIMIT %s
                        """,
                        params,
                    )
                    rows = cur.fetchall()
                except Exception as e:
                    logger.error("document.keyword_search_failed", error=str(e))
                    return []
        return [(self._row_to_parent_chunk(row), float(row["rank"])) for row in rows]

    def mark_points_vectorized(self, points: list[ChildChunkPoint]) -> None:
        if not points:
            return
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for point in points:
                    cur.execute(
                        """
                        INSERT INTO document_vector_points (
                            point_id, document_id, parent_chunk_id, chunk_index,
                            content_hash, token_count, vector_status
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, 'vectorized')
                        ON CONFLICT (point_id) DO UPDATE SET
                            parent_chunk_id = EXCLUDED.parent_chunk_id,
                            chunk_index = EXCLUDED.chunk_index,
                            content_hash = EXCLUDED.content_hash,
                            token_count = EXCLUDED.token_count,
                            vector_status = 'vectorized',
                            error = '{}'::jsonb,
                            updated_at = NOW()
                        """,
                        (
                            point.point_id,
                            point.document_id,
                            point.parent_chunk_id,
                            point.chunk_index,
                            point.content_hash,
                            point.token_count,
                        ),
                    )

    def mark_points_vector_failed(
        self, point_ids: list[str], error: dict[str, Any] | str
    ) -> None:
        if not point_ids:
            return
        err = error if isinstance(error, dict) else {"message": str(error)}
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE document_vector_points
                    SET vector_status = 'failed', error = %s, updated_at = NOW()
                    WHERE point_id = ANY(%s)
                    """,
                    (json.dumps(err, ensure_ascii=False), point_ids),
                )

    def delete_document(self, document_id: str) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM source_documents WHERE id = %s", (document_id,))

    @staticmethod
    def _segment_text(text: str) -> str:
        return " ".join(w.strip() for w in jieba.cut(text or "") if w.strip())

    @staticmethod
    def _json_value(value, default):
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return value

    @classmethod
    def _row_to_document(cls, row) -> SourceDocument:
        return SourceDocument(
            document_id=str(row["id"]),
            title=row["title"] or "",
            content=row["content"] or "",
            source_type=row["source_type"] or "web",
            document_type=row["document_type"] or "article",
            url=row["url"] or "",
            canonical_url=row["canonical_url"] or "",
            language=row["language"] or "",
            content_hash=row["content_hash"] or "",
            competitor_ids=cls._json_value(row["competitor_ids"], []),
            product_ids=cls._json_value(row["product_ids"], []),
            metadata=cls._json_value(row["metadata"], {}),
            published_at=row["published_at"],
            created_at=row["created_at"],
            blob_id=str(row["blob_id"]) if row["blob_id"] else None,
            parse_status=row["parse_status"] or "pending",
        )

    @classmethod
    def _row_to_parent_chunk(cls, row) -> ParentDocumentChunk:
        return ParentDocumentChunk(
            parent_chunk_id=row["parent_chunk_id"],
            document_id=str(row["document_id"]),
            content=row["content"] or "",
            token_count=row["token_count"] or 0,
            child_point_ids=cls._json_value(row["child_point_ids"], []),
            heading_path=cls._json_value(row["heading_path"], []),
            doc_name=row["doc_name"] or "",
            source=row["source"] or "",
            url=row["url"] or "",
            source_type=row["source_type"] or "web",
            document_type=row["document_type"] or "article",
            competitor_ids=cls._json_value(row["competitor_ids"], []),
            product_ids=cls._json_value(row["product_ids"], []),
            language=row["language"] or "",
            published_at=row["published_at"],
            created_at=row["created_at"],
            metadata=cls._json_value(row["metadata"], {}),
        )
