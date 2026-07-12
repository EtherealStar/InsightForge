"""固定输入、固定规则版本下可重放的正文清洗。"""
from __future__ import annotations

from hashlib import sha256
from html.parser import HTMLParser

from models.collection import (
    ContentBlock,
    FetchMethod,
    NormalizationOutcome,
    NormalizedDocument,
    NormalizerRules,
    RawFetchArtifact,
)


class _BlockParser(HTMLParser):
    BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre", "code"}
    IGNORED_TAGS = {"script", "style", "nav", "footer", "aside", "form", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.current_tag: str | None = None
        self.current_text: list[str] = []
        self.blocks: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        self.stack.append(tag)
        if tag in self.BLOCK_TAGS and not any(item in self.IGNORED_TAGS for item in self.stack):
            self.current_tag = tag
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_tag and not any(item in self.IGNORED_TAGS for item in self.stack):
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self.current_tag:
            text = " ".join("".join(self.current_text).split())
            if text:
                self.blocks.append((tag, text))
            self.current_tag = None
            self.current_text = []
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            self.stack.pop(index)


class DeterministicNormalizationService:
    SUPPORTED_MEDIA_TYPES = {"text/html", "application/xhtml+xml", "text/plain", "application/json", "application/pdf"}

    def normalize(self, artifact: RawFetchArtifact, body: bytes, rules: NormalizerRules) -> NormalizedDocument:
        media_type = (artifact.content_type or "").split(";", 1)[0].lower()
        if media_type not in self.SUPPORTED_MEDIA_TYPES:
            return self._result(artifact, rules, NormalizationOutcome.REJECTED, [], ["unsupported_media_type"])
        if media_type == "application/pdf":
            # PDF 必须由独立 OCR/解析队列产生逐字块，不能把二进制语法当正文。
            return self._result(artifact, rules, NormalizationOutcome.REVIEW_REQUIRED, [], ["pdf_requires_ocr"])

        text = self._decode(body)
        parser = _BlockParser()
        if media_type in {"text/html", "application/xhtml+xml"}:
            parser.feed(text)
            parsed = parser.blocks
        else:
            parsed = [("text", text.strip())] if text.strip() else []

        blocks = []
        for ordinal, (block_type, block_text) in enumerate(parsed):
            # block ID 只依赖 artifact、规则版本、顺序和逐字正文，重放时保持稳定。
            identity = f"{artifact.id}\0{rules.version}\0{ordinal}\0{block_text}"
            blocks.append(ContentBlock(sha256(identity.encode("utf-8")).hexdigest(), block_type, block_text, ordinal, f"block:{ordinal}"))

        length = sum(len(block.text) for block in blocks)
        if length < rules.minimum_text_length:
            # 浏览器结果绝不再次回到 browser 队列，避免静态/渲染循环。
            outcome = NormalizationOutcome.RETRY_RENDER if artifact.fetch_method is FetchMethod.HTTP else NormalizationOutcome.REVIEW_REQUIRED
            return self._result(artifact, rules, outcome, blocks, ["body_too_short"])
        return self._result(artifact, rules, NormalizationOutcome.ACCEPTED, blocks, [])

    @staticmethod
    def _decode(body: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
            try:
                return body.decode(encoding)
            except UnicodeDecodeError:
                continue
        return body.decode("utf-8", errors="replace")

    @staticmethod
    def _result(artifact, rules, outcome, blocks, reasons):
        title = next((block.text for block in blocks if block.block_type == "h1"), None)
        return NormalizedDocument(artifact.id, rules.version, outcome, blocks, reasons, title=title)
