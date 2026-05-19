"""Document parser entrypoint for uploaded blobs."""
from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from core.exceptions import InfrastructureError
from infrastructure.files.type_detector import FileTypeDetector
from infrastructure.markdown_converter import NewsMarkdownConverter
from models.file_asset import DocumentBlob, FileTypeDetection, ParsedDocument


class DocumentParser:
    """Parse supported file blobs into normalized Markdown/text."""

    def __init__(self, detector: FileTypeDetector | None = None):
        self.detector = detector or FileTypeDetector()
        self.markdown_converter = NewsMarkdownConverter()

    def detect(self, blob: DocumentBlob) -> FileTypeDetection:
        return self.detector.detect(blob.original_filename, blob.content_type)

    def parse(self, blob: DocumentBlob) -> ParsedDocument:
        detected = self.detect(blob)
        if not detected.supported or detected.parser == "zip":
            reason = detected.reason or f"Unsupported parser: {detected.parser}"
            raise InfrastructureError(reason)

        path = Path(blob.storage_path)
        if not path.exists():
            raise InfrastructureError(f"Blob file does not exist: {blob.storage_path}")

        title = Path(blob.original_filename or blob.safe_filename or path.name).stem
        raw_text = self._read_text(path)
        if not raw_text.strip():
            raise InfrastructureError("Parsed document is empty")

        parser = detected.parser
        if parser == "html":
            markdown = self.markdown_converter._select_best_markdown(
                html=raw_text,
                title=title,
            )
            result = self.markdown_converter._build_semantic_result(markdown, title=title)
            return ParsedDocument(
                title=title,
                content=result.markdown,
                content_type=detected.content_type,
                metadata={
                    "parser": "html",
                    "semantic_blocks": [
                        {
                            "type": block.type,
                            "text": block.text,
                            "level": block.level,
                            "heading_text": block.heading_text,
                            "heading_path": block.heading_path,
                        }
                        for block in result.blocks
                    ],
                    "semantic_page_type": result.page_type,
                    "semantic_confidence": result.confidence,
                    "semantic_skip_indexing": result.skip_indexing,
                },
            )

        if parser in {"csv", "tsv"}:
            delimiter = "\t" if parser == "tsv" else ","
            return ParsedDocument(
                title=title,
                content=self._table_to_markdown(raw_text, delimiter, title),
                content_type=detected.content_type,
                metadata={"parser": parser},
            )

        if parser == "markdown":
            content = raw_text.strip()
        else:
            content = f"# {title}\n\n{raw_text.strip()}"

        return ParsedDocument(
            title=title,
            content=content,
            content_type=detected.content_type,
            metadata={"parser": parser},
        )

    @staticmethod
    def _read_text(path: Path) -> str:
        data = path.read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise InfrastructureError("Unable to decode file as text")

    @staticmethod
    def _table_to_markdown(text: str, delimiter: str, title: str) -> str:
        reader = csv.reader(StringIO(text), delimiter=delimiter)
        rows = [row for row in reader if any(cell.strip() for cell in row)]
        if not rows:
            raise InfrastructureError("Table file has no rows")
        max_columns = max(len(row) for row in rows)
        normalized = [row + [""] * (max_columns - len(row)) for row in rows]
        header = normalized[0]
        body = normalized[1:]
        lines = [f"# {title}", ""]
        lines.append("| " + " | ".join(cell.strip() for cell in header) + " |")
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for row in body:
            lines.append("| " + " | ".join(cell.strip() for cell in row) + " |")
        return "\n".join(lines).strip()
