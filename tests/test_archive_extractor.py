"""ArchiveExtractor tests."""

import zipfile

import pytest

from core.exceptions import InfrastructureError
from infrastructure.files.archive_extractor import ArchiveExtractor


def _zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def test_archive_extractor_extracts_zip_members(tmp_path):
    archive = tmp_path / "docs.zip"
    _zip(archive, {"a.md": "# A\n\nbody", "nested/b.txt": "hello"})
    extractor = ArchiveExtractor()

    files = extractor.extract(str(archive), str(tmp_path / "out"))

    assert [item.safe_filename for item in files] == ["a.md", "b.txt"]
    assert all(item.sha256 for item in files)
    assert all(item.size_bytes > 0 for item in files)


def test_archive_extractor_rejects_zip_slip(tmp_path):
    archive = tmp_path / "bad.zip"
    _zip(archive, {"../escape.txt": "bad"})
    extractor = ArchiveExtractor()

    with pytest.raises(InfrastructureError, match="Unsafe archive path"):
        extractor.extract(str(archive), str(tmp_path / "out"))


def test_archive_extractor_enforces_limits(tmp_path):
    archive = tmp_path / "too_many.zip"
    _zip(archive, {"a.txt": "1", "b.txt": "2"})
    extractor = ArchiveExtractor()

    with pytest.raises(InfrastructureError, match="file count"):
        extractor.extract(str(archive), str(tmp_path / "out"), {"max_files": 1})

    with pytest.raises(InfrastructureError, match="max size"):
        extractor.extract(
            str(archive),
            str(tmp_path / "out2"),
            {"max_file_size_bytes": 0},
        )
