"""Conservative file type detection for uploaded documents."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from models.file_asset import FileTypeDetection


class FileTypeDetector:
    """Detect file type from extension and optional content type."""

    SUPPORTED_EXTENSIONS = {
        ".txt": ("text/plain", "text"),
        ".md": ("text/markdown", "markdown"),
        ".markdown": ("text/markdown", "markdown"),
        ".html": ("text/html", "html"),
        ".htm": ("text/html", "html"),
        ".csv": ("text/csv", "csv"),
        ".tsv": ("text/tab-separated-values", "tsv"),
        ".zip": ("application/zip", "zip"),
    }
    KNOWN_UNSUPPORTED = {
        ".pdf": "PDF parser is not enabled in phase 1 step 7",
        ".docx": "DOCX parser is not enabled in phase 1 step 7",
        ".tar": "TAR extraction is not enabled in phase 1 step 6",
        ".gz": "Compressed TAR extraction is not enabled in phase 1 step 6",
        ".tgz": "Compressed TAR extraction is not enabled in phase 1 step 6",
    }
    EXECUTABLE_EXTENSIONS = {
        ".bat",
        ".cmd",
        ".com",
        ".dll",
        ".exe",
        ".js",
        ".msi",
        ".ps1",
        ".scr",
        ".sh",
        ".vbs",
    }

    def __init__(self, allowed_extensions: list[str] | None = None):
        if allowed_extensions is None:
            self.allowed_extensions = set(self.SUPPORTED_EXTENSIONS)
        else:
            self.allowed_extensions = {
                ext.lower() if ext.startswith(".") else f".{ext.lower()}"
                for ext in allowed_extensions
            }

    def detect(self, filename: str, content_type: str = "") -> FileTypeDetection:
        ext = Path(filename or "").suffix.lower()
        guessed_content_type = content_type or mimetypes.guess_type(filename)[0] or ""

        if ext in self.EXECUTABLE_EXTENSIONS:
            return FileTypeDetection(
                file_ext=ext,
                content_type=guessed_content_type,
                supported=False,
                reason="Executable files are rejected",
            )

        if ext in self.SUPPORTED_EXTENSIONS and ext in self.allowed_extensions:
            default_type, parser = self.SUPPORTED_EXTENSIONS[ext]
            return FileTypeDetection(
                file_ext=ext,
                content_type=guessed_content_type or default_type,
                supported=True,
                parser=parser,
            )

        if ext in self.KNOWN_UNSUPPORTED:
            return FileTypeDetection(
                file_ext=ext,
                content_type=guessed_content_type,
                supported=False,
                reason=self.KNOWN_UNSUPPORTED[ext],
            )

        return FileTypeDetection(
            file_ext=ext,
            content_type=guessed_content_type,
            supported=False,
            reason="Unsupported or unknown file type",
        )
