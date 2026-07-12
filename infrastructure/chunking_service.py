"""Markdown 感知的父子分块服务

将 Markdown 格式的 SourceDocument 按章节结构拆分为 Qdrant 子 chunk point
(≤512 token)，再组装为 PostgreSQL 父 chunk (~1024 token)，子 chunk
明确归属一个主父 chunk。

分块策略：
1. 先解析 Markdown block（标题、段落、列表、引用、表格、代码块）
2. 以标题章节作为优先边界，章节过长则按 block 聚合
3. 单个 block 过长时优先按句子切割，token 截断只做兜底
4. 子 chunk 文本前置文档/章节上下文，便于 embedding 感知语义
5. 贪心组合连续子 chunk 为 ~1024 token 的父 chunk
6. 父 chunk 之间通过共享尾部子 chunk 实现 overlap
"""
from __future__ import annotations

import structlog
import re
import hashlib
from uuid import NAMESPACE_URL, uuid5

import tiktoken

from models.document import ChildChunkPoint, ParentDocumentChunk, SourceDocument

logger = structlog.get_logger(__name__)

# 匹配 Markdown 标题行（# ~ ######）
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s+|(?<=[。！？.!?])")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")


class ChunkingService:
    """Markdown 感知的父子分块服务"""

    def __init__(
        self,
        max_child_tokens: int = 512,
        target_parent_tokens: int = 1024,
        overlap_tokens: int = 100,
    ):
        self.max_child_tokens = max_child_tokens
        self.target_parent_tokens = target_parent_tokens
        self.overlap_tokens = overlap_tokens
        # 使用 cl100k_base 编码（GPT-4 / text-embedding-3 系列通用）
        self._enc = tiktoken.get_encoding("cl100k_base")

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def chunk_document(
        self, document: SourceDocument
    ) -> tuple[list[ChildChunkPoint], list[ParentDocumentChunk]]:
        """将一篇文档分块为 Qdrant 子 points 和 PostgreSQL 父 chunks。

        Args:
            document: 已标准化为 Markdown/text 的 SourceDocument。

        Returns:
            (children, parents) 元组。
        """
        if not document.content or not document.content.strip():
            return [], []

        document_id = document.document_id
        doc_name = document.title or "Untitled"
        source = document.source_type or ""
        url = document.url or ""

        if document.metadata.get("semantic_skip_indexing"):
            logger.info(f"跳过非文章页面分块: '{doc_name[:50]}'")
            return [], []

        sections = self._parse_sections(
            document.content,
            doc_name,
            semantic_blocks=document.metadata.get("semantic_blocks"),
        )
        children = self._build_child_chunks(
            sections, document, doc_name, source, url
        )

        if not children:
            return [], []

        parents = self._build_parent_chunks(
            children, document, doc_name, source, url
        )

        # 回填 parent_chunk_id
        self._assign_parent_ids(children, parents)

        return children, parents

    def chunk_documents(
        self, documents: list[SourceDocument]
    ) -> tuple[list[ChildChunkPoint], list[ParentDocumentChunk]]:
        """批量分块，单篇失败不影响整批。"""
        all_children: list[ChildChunkPoint] = []
        all_parents: list[ParentDocumentChunk] = []

        for document in documents:
            try:
                children, parents = self.chunk_document(document)
                all_children.extend(children)
                all_parents.extend(parents)
            except Exception as e:
                logger.warning(
                    f"分块失败: '{document.title[:50]}' — {e}"
                )

        logger.info(
            f"分块完成: {len(documents)} 篇文档 → "
            f"{len(all_children)} 子 chunks + {len(all_parents)} 父 chunks"
        )
        return all_children, all_parents

    # ------------------------------------------------------------------
    # 内部方法：解析 & 构建
    # ------------------------------------------------------------------

    def _parse_sections(
        self,
        markdown: str,
        doc_name: str,
        semantic_blocks: list | None = None,
    ) -> list[dict]:
        """解析 Markdown 的章节结构和 block 边界。

        返回 list[dict]，每项：
            {
                "heading_level": int,       # 标题级别 1-6
                "heading_text": str,        # 标题文本
                "heading_path": list[str],  # 从文档名到当前标题的层级路径
                "blocks": list[dict],       # 该 section 下的 Markdown blocks
                "content": str,             # 该 section 的内容（含标题行本身）
            }
        """
        if semantic_blocks:
            sections = self._parse_sections_from_semantic_blocks(
                semantic_blocks,
                doc_name,
            )
            if sections:
                return sections

        blocks = self._parse_markdown_blocks(markdown)
        if not blocks:
            return []

        sections: list[dict] = []
        heading_stack: list[tuple[int, str]] = []
        current = self._new_section(doc_name)

        for block in blocks:
            if block["type"] == "heading":
                if current["blocks"]:
                    self._finalize_section(sections, current)

                level = block["level"]
                heading_text = block["heading_text"]

                # Converter 会把文章标题放在唯一 H1；该 H1 只作为根标题，不重复进入路径。
                if level == 1 and _normalize_path_text(heading_text) == _normalize_path_text(doc_name):
                    heading_stack = []
                    current = self._new_section(doc_name)
                    continue

                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, heading_text))

                current = {
                    "heading_level": level,
                    "heading_text": heading_text,
                    "heading_path": _dedupe_heading_path(
                        [doc_name] + [h[1] for h in heading_stack]
                    ),
                    "blocks": [],
                    "content": "",
                }
                continue

            current["blocks"].append(block)

        if current["blocks"]:
            self._finalize_section(sections, current)

        if sections:
            return sections

        return [
            {
                "heading_level": 0,
                "heading_text": doc_name,
                "heading_path": [doc_name],
                "blocks": [{"type": "paragraph", "text": markdown.strip()}],
                "content": markdown.strip(),
            }
        ]

    @staticmethod
    def _parse_sections_from_semantic_blocks(
        semantic_blocks: list,
        doc_name: str,
    ) -> list[dict]:
        """从 NewsMarkdownConverter 提供的语义块还原章节。"""
        sections: list[dict] = []
        current: dict | None = None
        current_path: list[str] | None = None

        def flush_current() -> None:
            nonlocal current
            if current and current["blocks"]:
                ChunkingService._finalize_section(sections, current)
            current = None

        for block in semantic_blocks:
            if hasattr(block, "__dict__"):
                block_data = block.__dict__
            elif isinstance(block, dict):
                block_data = block
            else:
                continue

            text = (block_data.get("text") or "").strip()
            if not text:
                continue

            path = block_data.get("heading_path") or [doc_name]
            path = _dedupe_heading_path([str(item) for item in path])
            if not path:
                path = [doc_name]

            if current_path != path:
                flush_current()
                current_path = path
                current = {
                    "heading_level": max(0, len(path) - 1),
                    "heading_text": path[-1] if path else doc_name,
                    "heading_path": path,
                    "blocks": [],
                    "content": "",
                }

            if current is None:
                current = ChunkingService._new_section(doc_name)

            # 标题只用于章节路径，正文块通过前缀携带标题上下文。
            if block_data.get("type") == "heading":
                continue

            current["blocks"].append(
                {
                    "type": block_data.get("type") or "paragraph",
                    "text": text,
                }
            )

        flush_current()
        return sections

    @staticmethod
    def _new_section(doc_name: str) -> dict:
        return {
            "heading_level": 0,
            "heading_text": doc_name,
            "heading_path": [doc_name],
            "blocks": [],
            "content": "",
        }

    @staticmethod
    def _finalize_section(sections: list[dict], section: dict) -> None:
        content = "\n\n".join(
            block["text"].strip()
            for block in section["blocks"]
            if block.get("text", "").strip()
        ).strip()
        if not content:
            return
        section = dict(section)
        section["content"] = content
        sections.append(section)

    @staticmethod
    def _parse_markdown_blocks(markdown: str) -> list[dict]:
        """把 Markdown 粗解析为 block，保留代码块、表格和列表边界。"""
        blocks: list[dict] = []
        lines = markdown.splitlines()
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                i += 1
                continue

            if stripped.startswith("```"):
                start = i
                i += 1
                while i < len(lines):
                    if lines[i].strip().startswith("```"):
                        i += 1
                        break
                    i += 1
                blocks.append(
                    {"type": "code", "text": "\n".join(lines[start:i]).strip()}
                )
                continue

            heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", stripped)
            if heading:
                blocks.append(
                    {
                        "type": "heading",
                        "text": stripped,
                        "level": len(heading.group(1)),
                        "heading_text": heading.group(2).strip(),
                    }
                )
                i += 1
                continue

            if _TABLE_ROW_RE.match(line):
                start = i
                i += 1
                while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
                    i += 1
                blocks.append(
                    {"type": "table", "text": "\n".join(lines[start:i]).strip()}
                )
                continue

            if _LIST_ITEM_RE.match(line):
                start = i
                i += 1
                while i < len(lines):
                    next_line = lines[i]
                    if not next_line.strip():
                        i += 1
                        break
                    if (
                        re.match(r"^(#{1,6})\s+", next_line.strip())
                        or _TABLE_ROW_RE.match(next_line)
                    ):
                        break
                    if _LIST_ITEM_RE.match(next_line) or next_line.startswith((" ", "\t")):
                        i += 1
                        continue
                    break
                blocks.append(
                    {"type": "list", "text": "\n".join(lines[start:i]).strip()}
                )
                continue

            if stripped.startswith(">"):
                start = i
                i += 1
                while i < len(lines) and lines[i].strip().startswith(">"):
                    i += 1
                blocks.append(
                    {"type": "quote", "text": "\n".join(lines[start:i]).strip()}
                )
                continue

            start = i
            i += 1
            while i < len(lines):
                next_line = lines[i]
                next_stripped = next_line.strip()
                if not next_stripped:
                    break
                if (
                    next_stripped.startswith("```")
                    or re.match(r"^(#{1,6})\s+", next_stripped)
                    or _TABLE_ROW_RE.match(next_line)
                    or _LIST_ITEM_RE.match(next_line)
                    or next_stripped.startswith(">")
                ):
                    break
                i += 1
            blocks.append(
                {"type": "paragraph", "text": "\n".join(lines[start:i]).strip()}
            )

        return blocks

    def _build_child_chunks(
        self,
        sections: list[dict],
        document: SourceDocument,
        doc_name: str,
        source: str,
        url: str,
    ) -> list[ChildChunkPoint]:
        """从 sections 构建子 chunks (≤max_child_tokens)。

        - 若 section 不超过限制，直接成为一个子 chunk
        - 若 section 超过限制，按 Markdown block 继续分割
        - 单个 block 超限时先按句子切，token 截断仅兜底
        """
        raw_chunks: list[dict] = []

        for section in sections:
            raw_chunks.extend(self._chunk_section(section))

        # 合并过小的 chunks（< 50 token 的合并到下一个）
        merged = self._merge_tiny_chunks(raw_chunks)

        # 转为 Chunk 对象
        children = []
        for i, rc in enumerate(merged):
            content = rc["content"]
            children.append(
                ChildChunkPoint(
                    point_id=self._point_id(self._derivation_key(document), i),
                    document_id=document.document_id,
                    parent_chunk_id="",  # 稍后回填
                    content=content,
                    token_count=rc["token_count"],
                    doc_name=doc_name,
                    heading_path=rc["heading_path"],
                    chunk_index=i,
                    source=source,
                    url=url,
                    source_type=document.source_type,
                    document_type=document.document_type,
                    competitor_ids=list(document.competitor_ids),
                    product_ids=list(document.product_ids),
                    language=document.language,
                    content_hash=self._hash_text(content),
                    published_at=document.published_at,
                    created_at=document.created_at,
                    metadata=dict(document.metadata),
                )
            )

        return children

    def _chunk_section(self, section: dict) -> list[dict]:
        """按 block 聚合一个章节，生成带标题上下文的子 chunk。"""
        blocks = section.get("blocks") or []
        heading_path = section["heading_path"]
        if not blocks:
            return []

        soft_limit = max(64, int(self.max_child_tokens * 0.8))
        chunks: list[dict] = []
        current: list[str] = []

        def flush_current() -> None:
            if not current:
                return
            body = "\n\n".join(current).strip()
            chunk = self._make_raw_chunk(body, heading_path)
            if chunk:
                chunks.append(chunk)
            current.clear()

        for block in blocks:
            block_text = (block.get("text") or "").strip()
            if not block_text:
                continue

            candidate_body = "\n\n".join([*current, block_text]).strip()
            candidate_text = self._format_child_content(candidate_body, heading_path)
            candidate_tokens = self._count_tokens(candidate_text)

            if candidate_tokens <= self.max_child_tokens and (
                candidate_tokens <= soft_limit or not current
            ):
                current.append(block_text)
                continue

            block_text_with_prefix = self._format_child_content(block_text, heading_path)
            block_tokens = self._count_tokens(block_text_with_prefix)

            if block_tokens > self.max_child_tokens:
                flush_current()
                chunks.extend(self._split_oversized_block(block, heading_path))
                continue

            flush_current()
            current.append(block_text)

        flush_current()
        return chunks

    def _make_raw_chunk(self, body: str, heading_path: list[str]) -> dict | None:
        content = self._format_child_content(body, heading_path)
        if not content.strip():
            return None
        token_count = self._count_tokens(content)
        if token_count <= self.max_child_tokens:
            return {
                "content": content,
                "token_count": token_count,
                "heading_path": heading_path,
            }
        parts = self._force_split_text(body, heading_path)
        return parts[0] if parts else None

    def _split_oversized_block(
        self, block: dict, heading_path: list[str]
    ) -> list[dict]:
        """单个 block 超限时，优先按句子/行切割，再兜底 token 切割。"""
        text = (block.get("text") or "").strip()
        block_type = block.get("type")

        if block_type in {"table", "list", "code"}:
            units = [line for line in text.splitlines() if line.strip()]
        else:
            units = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
            if len(units) <= 1:
                units = [line.strip() for line in text.splitlines() if line.strip()]

        chunks: list[dict] = []
        current: list[str] = []

        def flush_current() -> None:
            if not current:
                return
            separator = "\n" if block_type in {"table", "list", "code"} else ""
            body = separator.join(current).strip()
            chunk = self._make_raw_chunk(body, heading_path)
            if chunk:
                chunks.append(chunk)
            current.clear()

        for unit in units:
            candidate = ("\n" if block_type in {"table", "list", "code"} else "").join(
                [*current, unit]
            ).strip()
            candidate_text = self._format_child_content(candidate, heading_path)
            if self._count_tokens(candidate_text) <= self.max_child_tokens:
                current.append(unit)
                continue

            flush_current()
            unit_text = self._format_child_content(unit, heading_path)
            if self._count_tokens(unit_text) > self.max_child_tokens:
                chunks.extend(self._force_split_text(unit, heading_path))
            else:
                current.append(unit)

        flush_current()
        return chunks

    def _force_split_text(
        self, text: str, heading_path: list[str]
    ) -> list[dict]:
        """将超长文本按 token 限制强制截断，预留标题上下文 token。"""
        prefix = self._format_child_prefix(heading_path)
        prefix_tokens = self._count_tokens(prefix + "\n\n") if prefix else 0
        budget = max(32, self.max_child_tokens - prefix_tokens)
        tokens = self._enc.encode(text)
        chunks = []
        for i in range(0, len(tokens), budget):
            chunk_tokens = tokens[i: i + budget]
            chunk_body = self._enc.decode(chunk_tokens)
            chunk_text = self._format_child_content(chunk_body, heading_path)
            chunks.append(
                {
                    "content": chunk_text,
                    "token_count": self._count_tokens(chunk_text),
                    "heading_path": heading_path,
                }
            )
        return chunks

    def _merge_tiny_chunks(
        self, chunks: list[dict], min_tokens: int = 50
    ) -> list[dict]:
        """合并过小的 chunks 到相邻 chunk。"""
        if not chunks:
            return []

        merged: list[dict] = []
        for chunk in chunks:
            if (
                merged
                and chunk["token_count"] < min_tokens
                and chunk["heading_path"] == merged[-1]["heading_path"]
                and merged[-1]["token_count"] + chunk["token_count"]
                <= self.max_child_tokens
            ):
                # 合并到前一个
                merged[-1]["content"] += "\n\n" + chunk["content"]
                merged[-1]["token_count"] = self._count_tokens(merged[-1]["content"])
            else:
                merged.append(dict(chunk))

        return merged

    @staticmethod
    def _format_child_prefix(heading_path: list[str]) -> str:
        clean_path = _dedupe_heading_path(heading_path)
        doc_name = clean_path[0] if clean_path else ""
        section_path = clean_path[1:]

        lines = []
        if doc_name:
            lines.append(f"文档: {doc_name}")
        if section_path:
            lines.append("章节: " + " > ".join(section_path))
        return "\n".join(lines)

    def _format_child_content(self, body: str, heading_path: list[str]) -> str:
        body = (body or "").strip()
        prefix = self._format_child_prefix(heading_path)
        if prefix and body:
            return f"{prefix}\n\n{body}".strip()
        if prefix:
            return prefix
        return body

    def _build_parent_chunks(
        self,
        children: list[ChildChunkPoint],
        document: SourceDocument,
        doc_name: str,
        source: str,
        url: str,
    ) -> list[ParentDocumentChunk]:
        """从子 chunks 组装父 chunks (~target_parent_tokens)。

        算法：
        1. 贪心累加子 chunk 直到接近 target_parent_tokens
        2. 提交当前父 chunk
        3. 为实现 overlap: 下一个父 chunk 从当前父 chunk 的最后一个子 chunk 开始
           (前提是该子 chunk 的 token 数 ≤ overlap_tokens 的 2 倍)
        4. 子 chunk 最终只归属一个父 chunk (最终分配时取消 overlap 中的双重归属)
        """
        if not children:
            return []

        total_tokens = sum(child.token_count for child in children)
        soft_parent_limit = int(self.target_parent_tokens * 1.2)
        if total_tokens <= soft_parent_limit:
            parent_content = "\n\n".join(c.content for c in children)
            return [
                ParentDocumentChunk(
                    parent_chunk_id=f"{self._derivation_key(document)}:p0",
                    document_id=document.document_id,
                    content=parent_content,
                    token_count=self._count_tokens(parent_content),
                    child_point_ids=[c.point_id for c in children],
                    heading_path=list(children[0].heading_path if children else []),
                    doc_name=doc_name,
                    source=source,
                    url=url,
                    source_type=document.source_type,
                    document_type=document.document_type,
                    competitor_ids=list(document.competitor_ids),
                    product_ids=list(document.product_ids),
                    language=document.language,
                    published_at=document.published_at,
                    created_at=document.created_at,
                    metadata=dict(document.metadata),
                )
            ]

        parents: list[ParentDocumentChunk] = []
        i = 0  # 子 chunk 游标
        parent_idx = 0

        while i < len(children):
            group: list[ChildChunkPoint] = []
            group_tokens = 0

            # 贪心累加
            j = i
            while j < len(children):
                child = children[j]
                if group and group_tokens + child.token_count > self.target_parent_tokens:
                    break
                group.append(child)
                group_tokens += child.token_count
                j += 1

            # 组装父 chunk
            parent_content = "\n\n".join(c.content for c in group)
            parent = ParentDocumentChunk(
                parent_chunk_id=f"{self._derivation_key(document)}:p{parent_idx}",
                document_id=document.document_id,
                content=parent_content,
                token_count=self._count_tokens(parent_content),
                child_point_ids=[c.point_id for c in group],
                heading_path=list(group[0].heading_path if group else []),
                doc_name=doc_name,
                source=source,
                url=url,
                source_type=document.source_type,
                document_type=document.document_type,
                competitor_ids=list(document.competitor_ids),
                product_ids=list(document.product_ids),
                language=document.language,
                published_at=document.published_at,
                created_at=document.created_at,
                metadata=dict(document.metadata),
            )
            parents.append(parent)
            parent_idx += 1

            # 计算下一个父 chunk 的起始位置 (overlap)
            if j >= len(children):
                break

            # 尝试用最后一个子 chunk 做 overlap
            last_child = group[-1]
            if len(group) > 1 and last_child.token_count <= self.overlap_tokens * 2:
                # 下一个父 chunk 从最后一个子 chunk 开始（overlap）
                i = j - 1
            else:
                # 最后一个子 chunk 太大，不 overlap
                i = j

        return parents

    def _assign_parent_ids(
        self,
        children: list[ChildChunkPoint],
        parents: list[ParentDocumentChunk],
    ) -> None:
        """为每个子 chunk 分配 parent_chunk_id。

        由于 overlap，一个子 chunk 可能出现在多个父 chunk 中。
        规则：子 chunk 归属于**第一个**包含它的父 chunk。
        """
        assigned: set[str] = set()

        for parent in parents:
            retained_point_ids = []
            for cid in parent.child_point_ids:
                if cid not in assigned:
                    assigned.add(cid)
                    retained_point_ids.append(cid)
                    # 找到对应的子 chunk 并设置 parent_id
                    for child in children:
                        if child.point_id == cid:
                            child.parent_chunk_id = parent.parent_chunk_id
                            break
            # child_point_ids 保留完整父块内容关系，包括 overlap 共享子块；
            # 子 point 的 parent_chunk_id 只指向第一个包含它的主父块。
            if retained_point_ids:
                parent.metadata = dict(parent.metadata)
                parent.metadata["owned_child_point_ids"] = retained_point_ids

    def _handle_short_document(
        self,
        content: str,
        token_count: int,
        document_id: str,
        doc_name: str,
        source: str,
        url: str,
    ) -> tuple[list[ChildChunkPoint], list[ParentDocumentChunk]]:
        """处理短文档 (≤1024 token)：同时视为子 chunk 和父 chunk。"""
        chunk_id = self._point_id(document_id, 0)
        parent_id = f"{document_id}:p0"

        # 解析标题路径
        heading_path = [doc_name]
        first_heading = _HEADING_RE.search(content)
        if first_heading:
            heading_path.append(first_heading.group(2).strip())
        chunk_content = self._format_child_content(content, heading_path)
        chunk_tokens = self._count_tokens(chunk_content)

        child = ChildChunkPoint(
            point_id=chunk_id,
            document_id=document_id,
            parent_chunk_id=parent_id,
            content=chunk_content,
            token_count=chunk_tokens,
            doc_name=doc_name,
            heading_path=heading_path,
            chunk_index=0,
            source=source,
            url=url,
        )

        parent = ParentDocumentChunk(
            parent_chunk_id=parent_id,
            document_id=document_id,
            content=chunk_content,
            token_count=chunk_tokens,
            child_point_ids=[chunk_id],
            doc_name=doc_name,
            source=source,
            url=url,
        )

        return [child], [parent]

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _count_tokens(self, text: str) -> int:
        """使用 tiktoken 计算 token 数。"""
        if not text:
            return 0
        return len(self._enc.encode(text))

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _point_id(document_id: str, chunk_index: int) -> str:
        """Return a stable Qdrant-compatible UUID point id."""
        return str(uuid5(NAMESPACE_URL, f"{document_id}:c:{chunk_index}"))

    @staticmethod
    def _derivation_key(document: SourceDocument) -> str:
        # 派生对象必须绑定具体版本；否则 Canonical 晋升会覆盖仍在服务的 active 数据。
        version_id = document.metadata.get("document_version_id")
        return f"{document.document_id}:v:{version_id}" if version_id else document.document_id


def _normalize_path_text(text: str) -> str:
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text or "")
    text = re.sub(r"[*_`#>\[\]（）()\s:：|｜,，。.!！?？\"'“”‘’、-]+", "", text)
    return text.lower()


def _dedupe_heading_path(path: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in path:
        item = (item or "").strip()
        if not item:
            continue
        key = _normalize_path_text(item)
        if key and key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
