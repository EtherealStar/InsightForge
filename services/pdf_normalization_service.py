"""PDF 文本层提取；扫描件保留 review_required 等待外部 OCR。"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO

from pypdf import PdfReader

from models.collection import ContentBlock, NormalizationOutcome, NormalizedDocument, NormalizerRules


class PdfTextNormalizationService:
    def normalize(self, artifact, body: bytes, rules: NormalizerRules) -> NormalizedDocument:
        try:
            reader = PdfReader(BytesIO(body))
        except Exception:
            return NormalizedDocument(
                artifact.id, rules.version, NormalizationOutcome.REJECTED, [], ["invalid_pdf"]
            )
        blocks = []
        for ordinal, page in enumerate(reader.pages):
            # pypdf 只读取 PDF 自带文本层，不进行生成式补写。
            text = "\n".join(line.rstrip() for line in (page.extract_text() or "").splitlines()).strip()
            if not text:
                continue
            identity = f"{artifact.id}\0{rules.version}\0{ordinal}\0{text}"
            blocks.append(
                ContentBlock(
                    sha256(identity.encode("utf-8")).hexdigest(),
                    "pdf_page",
                    text,
                    ordinal,
                    f"page:{ordinal + 1}",
                )
            )
        length = sum(len(block.text) for block in blocks)
        if length < rules.minimum_text_length:
            return NormalizedDocument(
                artifact.id,
                rules.version,
                NormalizationOutcome.REVIEW_REQUIRED,
                blocks,
                ["pdf_text_layer_missing"],
            )
        return NormalizedDocument(
            artifact.id, rules.version, NormalizationOutcome.ACCEPTED, blocks, []
        )
