"""Safe archive extraction utilities."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from core.exceptions import InfrastructureError
from infrastructure.files.blob_store import safe_filename
from infrastructure.files.type_detector import FileTypeDetector
from models.file_asset import ExtractedFile


class ArchiveExtractor:
    """Safely extract supported archives into a controlled directory."""

    DEFAULT_LIMITS = {
        "max_files": 200,
        "max_file_size_bytes": 50 * 1024 * 1024,
        "max_total_size_bytes": 500 * 1024 * 1024,
    }

    def __init__(self, detector: FileTypeDetector | None = None):
        self.detector = detector or FileTypeDetector()

    def can_extract(self, filename: str, content_type: str = "") -> bool:
        detected = self.detector.detect(filename, content_type)
        return detected.parser == "zip"

    def extract(
        self,
        archive_path: str,
        output_dir: str,
        limits: dict | None = None,
    ) -> list[ExtractedFile]:
        limits = {**self.DEFAULT_LIMITS, **(limits or {})}
        archive = Path(archive_path).resolve()
        target_root = Path(output_dir).resolve()
        target_root.mkdir(parents=True, exist_ok=True)

        if not zipfile.is_zipfile(archive):
            raise InfrastructureError(f"Unsupported or invalid archive: {archive}")

        extracted: list[ExtractedFile] = []
        total_size = 0
        with zipfile.ZipFile(archive) as zf:
            members = [member for member in zf.infolist() if not member.is_dir()]
            if len(members) > int(limits["max_files"]):
                raise InfrastructureError("Archive exceeds max file count")

            for member in members:
                member_name = member.filename.replace("\\", "/")
                self._validate_member_path(member_name, target_root)
                if member.file_size <= 0:
                    raise InfrastructureError(f"Archive contains empty file: {member.filename}")
                if member.file_size > int(limits["max_file_size_bytes"]):
                    raise InfrastructureError(f"Archive member exceeds max size: {member.filename}")
                total_size += member.file_size
                if total_size > int(limits["max_total_size_bytes"]):
                    raise InfrastructureError("Archive exceeds max unpacked size")

            for member in members:
                safe_name = safe_filename(member.filename)
                target = self._unique_target(target_root / safe_name)
                digest = hashlib.sha256()
                size = 0
                with zf.open(member, "r") as source, target.open("wb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        digest.update(chunk)
                        output.write(chunk)

                detected = self.detector.detect(safe_name)
                extracted.append(
                    ExtractedFile(
                        original_filename=member.filename,
                        safe_filename=safe_name,
                        storage_path=str(target),
                        size_bytes=size,
                        sha256=digest.hexdigest(),
                        content_type=detected.content_type,
                        file_ext=detected.file_ext,
                    )
                )

        return extracted

    @staticmethod
    def _validate_member_path(member_name: str, target_root: Path) -> None:
        path = Path(member_name)
        if path.is_absolute() or ".." in path.parts:
            raise InfrastructureError(f"Unsafe archive path: {member_name}")
        resolved = (target_root / member_name).resolve()
        if target_root not in (resolved, *resolved.parents):
            raise InfrastructureError(f"Archive path escapes output directory: {member_name}")

    @staticmethod
    def _unique_target(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        i = 1
        while True:
            candidate = parent / f"{stem}-{i}{suffix}"
            if not candidate.exists():
                return candidate
            i += 1
