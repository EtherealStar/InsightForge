"""LocalFileBlobStore tests."""

from io import BytesIO

import pytest

from core.exceptions import InfrastructureError
from infrastructure.files.blob_store import LocalFileBlobStore


def test_blob_store_saves_by_hash_and_reuses_duplicate(tmp_path):
    store = LocalFileBlobStore(root=str(tmp_path), max_file_size_bytes=1024)
    payload = b"hello document"

    first = store.put(BytesIO(payload), {"original_filename": "hello.md"})
    second = store.put(BytesIO(payload), {"original_filename": "hello.md"})

    assert first.sha256 == second.sha256
    assert first.storage_path == second.storage_path
    assert first.size_bytes == len(payload)
    assert store.exists(first.storage_path)


def test_blob_store_rejects_empty_and_oversized_files(tmp_path):
    store = LocalFileBlobStore(root=str(tmp_path), max_file_size_bytes=4)

    with pytest.raises(InfrastructureError, match="Empty"):
        store.put(BytesIO(b""), {"original_filename": "empty.txt"})

    with pytest.raises(InfrastructureError, match="max size"):
        store.put(BytesIO(b"too large"), {"original_filename": "large.txt"})


def test_blob_store_prevents_path_escape(tmp_path):
    store = LocalFileBlobStore(root=str(tmp_path))

    assert store.exists(str(tmp_path / "missing.txt")) is False
    with pytest.raises(InfrastructureError, match="escapes"):
        store.open(str(tmp_path.parent / "outside.txt"))


def test_blob_store_quarantines_existing_file(tmp_path):
    store = LocalFileBlobStore(root=str(tmp_path))
    result = store.put(BytesIO(b"unsafe"), {"original_filename": "unsafe.txt"})

    quarantine_path = store.quarantine(result.storage_path, "test reason")

    assert "quarantine" in quarantine_path
    assert store.exists(quarantine_path)
    assert not store.exists(result.storage_path)
