"""PostgresUploadStore tests."""

import os

import pytest

from infrastructure.upload_store import PostgresUploadStore
from models.file_asset import DocumentBlob, UploadBatch


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_PG_DSN"),
    reason="Requires PostgreSQL instance with infrastructure migrations applied",
)


def test_upload_store_persists_batch_and_blobs(test_dsn):
    store = PostgresUploadStore(test_dsn)
    batch = store.create_batch(
        UploadBatch(
            source="api",
            file_count=1,
            total_size_bytes=12,
            metadata={"document_type": "competitor_doc"},
        )
    )

    blob = store.save_blob(
        DocumentBlob(
            upload_batch_id=batch.id,
            original_filename="doc.md",
            safe_filename="doc.md",
            content_type="text/markdown",
            file_ext=".md",
            size_bytes=12,
            sha256="abc123",
            storage_path="storage/uploads/original/ab/abc123.md",
        )
    )

    loaded = store.get_blob(blob.id)
    assert loaded is not None
    assert loaded.upload_batch_id == batch.id
    assert store.list_blobs(batch.id)[0].id == blob.id
    assert store.find_blobs_by_sha256("abc123")[0].id == blob.id

    store.update_blob_status(blob.id, "parsed")
    assert store.get_blob(blob.id).status == "parsed"

    finished = store.finish_batch(batch.id, "succeeded")
    assert finished.status == "succeeded"
