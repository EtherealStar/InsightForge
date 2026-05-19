"""DocumentParser tests."""

import pytest

from core.exceptions import InfrastructureError
from infrastructure.parsers.document_parser import DocumentParser
from models.file_asset import DocumentBlob


def _blob(path, filename):
    return DocumentBlob(
        original_filename=filename,
        safe_filename=filename,
        content_type="",
        file_ext=path.suffix,
        size_bytes=path.stat().st_size,
        sha256="sha",
        storage_path=str(path),
    )


def test_document_parser_parses_markdown(tmp_path):
    path = tmp_path / "competitor.md"
    path.write_text("# Competitor\n\nLaunch notes", encoding="utf-8")
    parser = DocumentParser()

    parsed = parser.parse(_blob(path, "competitor.md"))

    assert parsed.title == "competitor"
    assert parsed.content.startswith("# Competitor")
    assert parsed.metadata["parser"] == "markdown"


def test_document_parser_parses_html_to_markdown(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(
        "<html><body><article><h1>Page</h1><p>Important update.</p></article></body></html>",
        encoding="utf-8",
    )
    parser = DocumentParser()

    parsed = parser.parse(_blob(path, "page.html"))

    assert parsed.content.startswith("# page")
    assert "Important update" in parsed.content
    assert parsed.metadata["parser"] == "html"
    assert "semantic_blocks" in parsed.metadata


def test_document_parser_parses_csv_to_markdown_table(tmp_path):
    path = tmp_path / "pricing.csv"
    path.write_text("Plan,Price\nPro,20\n", encoding="utf-8")
    parser = DocumentParser()

    parsed = parser.parse(_blob(path, "pricing.csv"))

    assert "| Plan | Price |" in parsed.content
    assert "| Pro | 20 |" in parsed.content


def test_document_parser_rejects_unsupported_pdf(tmp_path):
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF")
    parser = DocumentParser()

    with pytest.raises(InfrastructureError, match="PDF parser"):
        parser.parse(_blob(path, "paper.pdf"))
