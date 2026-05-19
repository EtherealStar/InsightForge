"""Local file blob store for uploaded and extracted documents."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import BinaryIO

from core.exceptions import InfrastructureError
from infrastructure.files.type_detector import FileTypeDetector
from models.file_asset import StoredBlobResult

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(filename: str) -> str:
    """Return a filesystem-safe display filename."""
    name = Path(filename or "upload.bin").name.strip() or "upload.bin"
    name = _SAFE_NAME_RE.sub("_", name)
    return name[:180] or "upload.bin"


class LocalFileBlobStore:
    """Persist blobs under a local storage root using content hashes."""

    def __init__(
        self,
        root: str = "storage",
        max_file_size_bytes: int = 50 * 1024 * 1024,
        detector: FileTypeDetector | None = None,
    ):
        self.root = Path(root).resolve()
        self.max_file_size_bytes = max_file_size_bytes
        self.detector = detector or FileTypeDetector()
        self.original_dir = self.root / "uploads" / "original"
        self.extracted_dir = self.root / "uploads" / "extracted"
        self.quarantine_dir = self.root / "uploads" / "quarantine"
        self.parsed_dir = self.root / "parsed"
        for directory in (
            self.original_dir,
            self.extracted_dir,
            self.quarantine_dir,
            self.parsed_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def put(
        self, stream: BinaryIO, metadata: dict | None = None
    ) -> StoredBlobResult:
        metadata = metadata or {}
        original_filename = str(metadata.get("original_filename") or "upload.bin")
        content_type = str(metadata.get("content_type") or "")
        detected = self.detector.detect(original_filename, content_type)
        safe_name = safe_filename(original_filename)
        temp_path = self.original_dir / f".tmp-{os.getpid()}-{safe_name}"

        digest = hashlib.sha256()
        size = 0
        try:
            with temp_path.open("wb") as output:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.max_file_size_bytes:
                        raise InfrastructureError(
                            f"File exceeds max size: {self.max_file_size_bytes} bytes"
                        )
                    digest.update(chunk)
                    output.write(chunk)

            if size == 0:
                raise InfrastructureError("Empty files are rejected")

            sha256 = digest.hexdigest()
            ext = detected.file_ext or Path(safe_name).suffix.lower()
            final_dir = self.original_dir / sha256[:2] / sha256[2:4]
            final_dir.mkdir(parents=True, exist_ok=True)
            final_name = f"{sha256}{ext}" if ext else sha256
            final_path = final_dir / final_name
            if final_path.exists():
                temp_path.unlink(missing_ok=True)
            else:
                temp_path.replace(final_path)

            return StoredBlobResult(
                storage_path=str(final_path),
                sha256=sha256,
                size_bytes=size,
                safe_filename=safe_name,
                content_type=detected.content_type,
                file_ext=detected.file_ext,
            )
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def open(self, blob_path: str) -> BinaryIO:
        path = self._resolve_inside_root(blob_path)
        return path.open("rb")

    def delete(self, blob_path: str) -> bool:
        path = self._resolve_inside_root(blob_path)
        if not path.exists():
            return False
        path.unlink()
        return True

    def exists(self, blob_path: str) -> bool:
        try:
            return self._resolve_inside_root(blob_path).exists()
        except InfrastructureError:
            return False

    def quarantine(self, blob_path: str, reason: str) -> str:
        path = self._resolve_inside_root(blob_path)
        if not path.exists():
            raise InfrastructureError(f"Blob does not exist: {blob_path}")
        quarantine_name = f"{path.stem}-{hashlib.sha256(reason.encode()).hexdigest()[:8]}{path.suffix}"
        target = self.quarantine_dir / quarantine_name
        shutil.move(str(path), str(target))
        return str(target)

    def _resolve_inside_root(self, blob_path: str) -> Path:
        path = Path(blob_path)
        if not path.is_absolute():
            path = self.root / path
        resolved = path.resolve()
        if self.root not in (resolved, *resolved.parents):
            raise InfrastructureError(f"Path escapes blob storage root: {blob_path}")
        return resolved
