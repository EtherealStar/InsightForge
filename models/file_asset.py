"""File upload and document parsing models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


def new_upload_id() -> str:
    return str(uuid4())


def new_blob_id() -> str:
    return str(uuid4())


@dataclass
class UploadBatch:
    """A single upload operation that may contain many files."""

    id: str = field(default_factory=new_upload_id)
    source: str = "api"
    status: str = "received"
    file_count: int = 0
    expanded_file_count: int = 0
    total_size_bytes: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class DocumentBlob:
    """Metadata for an uploaded or extracted file object."""

    id: str = field(default_factory=new_blob_id)
    upload_batch_id: str | None = None
    parent_blob_id: str | None = None
    original_filename: str = ""
    safe_filename: str = ""
    content_type: str = ""
    file_ext: str = ""
    size_bytes: int = 0
    sha256: str = ""
    storage_path: str = ""
    status: str = "stored"
    error: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class StoredBlobResult:
    """Result returned by a blob store after bytes are persisted."""

    storage_path: str
    sha256: str
    size_bytes: int
    safe_filename: str
    content_type: str = ""
    file_ext: str = ""


@dataclass
class ExtractedFile:
    """A file safely extracted from an archive."""

    original_filename: str
    safe_filename: str
    storage_path: str
    size_bytes: int
    sha256: str
    content_type: str = ""
    file_ext: str = ""
    error: dict[str, Any] = field(default_factory=dict)


@dataclass
class FileTypeDetection:
    """Conservative file type detection result."""

    file_ext: str
    content_type: str
    supported: bool
    parser: str = ""
    reason: str = ""


@dataclass
class ParsedDocument:
    """Normalized parser output, ready to become a SourceDocument."""

    title: str
    content: str
    content_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
