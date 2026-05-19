"""PostgreSQL upload batch and blob metadata store."""
from __future__ import annotations

import json
from typing import Any

import psycopg2
from psycopg2.extras import DictCursor

from core.exceptions import StoreError
from models.file_asset import DocumentBlob, UploadBatch


class PostgresUploadStore:
    """Store upload batch and document blob metadata.

    Schema is managed by migrations; this class only performs health checks and
    data access.
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
            raise StoreError(f"PostgreSQL upload store unavailable: {e}") from e

    def create_batch(self, batch: UploadBatch) -> UploadBatch:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO upload_batches (
                        id, source, status, file_count, expanded_file_count,
                        total_size_bytes, metadata, error
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        source = EXCLUDED.source,
                        status = EXCLUDED.status,
                        file_count = EXCLUDED.file_count,
                        expanded_file_count = EXCLUDED.expanded_file_count,
                        total_size_bytes = EXCLUDED.total_size_bytes,
                        metadata = EXCLUDED.metadata,
                        error = EXCLUDED.error,
                        updated_at = NOW()
                    RETURNING *
                    """,
                    (
                        batch.id,
                        batch.source,
                        batch.status,
                        batch.file_count,
                        batch.expanded_file_count,
                        batch.total_size_bytes,
                        json.dumps(batch.metadata, ensure_ascii=False),
                        json.dumps(batch.error, ensure_ascii=False),
                    ),
                )
                return self._row_to_batch(cur.fetchone())

    def finish_batch(
        self, batch_id: str, status: str, error: dict[str, Any] | None = None
    ) -> UploadBatch:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE upload_batches
                    SET status = %s, error = %s, updated_at = NOW(), finished_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (
                        status,
                        json.dumps(error or {}, ensure_ascii=False),
                        batch_id,
                    ),
                )
                row = cur.fetchone()
        if not row:
            raise StoreError(f"Upload batch not found: {batch_id}")
        return self._row_to_batch(row)

    def save_blob(self, blob: DocumentBlob) -> DocumentBlob:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO document_blobs (
                        id, upload_batch_id, parent_blob_id, original_filename,
                        safe_filename, content_type, file_ext, size_bytes, sha256,
                        storage_path, status, error
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        upload_batch_id = EXCLUDED.upload_batch_id,
                        parent_blob_id = EXCLUDED.parent_blob_id,
                        original_filename = EXCLUDED.original_filename,
                        safe_filename = EXCLUDED.safe_filename,
                        content_type = EXCLUDED.content_type,
                        file_ext = EXCLUDED.file_ext,
                        size_bytes = EXCLUDED.size_bytes,
                        sha256 = EXCLUDED.sha256,
                        storage_path = EXCLUDED.storage_path,
                        status = EXCLUDED.status,
                        error = EXCLUDED.error,
                        updated_at = NOW()
                    RETURNING *
                    """,
                    (
                        blob.id,
                        blob.upload_batch_id,
                        blob.parent_blob_id,
                        blob.original_filename,
                        blob.safe_filename,
                        blob.content_type,
                        blob.file_ext,
                        blob.size_bytes,
                        blob.sha256,
                        blob.storage_path,
                        blob.status,
                        json.dumps(blob.error, ensure_ascii=False),
                    ),
                )
                return self._row_to_blob(cur.fetchone())

    def get_blob(self, blob_id: str) -> DocumentBlob | None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM document_blobs WHERE id = %s", (blob_id,))
                row = cur.fetchone()
        return self._row_to_blob(row) if row else None

    def list_blobs(self, batch_id: str) -> list[DocumentBlob]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM document_blobs
                    WHERE upload_batch_id = %s
                    ORDER BY created_at, original_filename
                    """,
                    (batch_id,),
                )
                rows = cur.fetchall()
        return [self._row_to_blob(row) for row in rows]

    def find_blobs_by_sha256(self, sha256: str) -> list[DocumentBlob]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM document_blobs
                    WHERE sha256 = %s
                    ORDER BY created_at DESC
                    """,
                    (sha256,),
                )
                rows = cur.fetchall()
        return [self._row_to_blob(row) for row in rows]

    def update_blob_status(
        self, blob_id: str, status: str, error: dict[str, Any] | None = None
    ) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE document_blobs
                    SET status = %s, error = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        status,
                        json.dumps(error or {}, ensure_ascii=False),
                        blob_id,
                    ),
                )

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
    def _row_to_batch(cls, row) -> UploadBatch:
        return UploadBatch(
            id=str(row["id"]),
            source=row["source"] or "api",
            status=row["status"] or "received",
            file_count=row["file_count"] or 0,
            expanded_file_count=row["expanded_file_count"] or 0,
            total_size_bytes=row["total_size_bytes"] or 0,
            metadata=cls._json_value(row["metadata"], {}),
            error=cls._json_value(row["error"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            finished_at=row["finished_at"],
        )

    @classmethod
    def _row_to_blob(cls, row) -> DocumentBlob:
        return DocumentBlob(
            id=str(row["id"]),
            upload_batch_id=str(row["upload_batch_id"]) if row["upload_batch_id"] else None,
            parent_blob_id=str(row["parent_blob_id"]) if row["parent_blob_id"] else None,
            original_filename=row["original_filename"] or "",
            safe_filename=row["safe_filename"] or "",
            content_type=row["content_type"] or "",
            file_ext=row["file_ext"] or "",
            size_bytes=row["size_bytes"] or 0,
            sha256=row["sha256"] or "",
            storage_path=row["storage_path"] or "",
            status=row["status"] or "stored",
            error=cls._json_value(row["error"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
