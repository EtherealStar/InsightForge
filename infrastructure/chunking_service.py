"""Markdown 感知的父子分块服务

将 Markdown 格式的文章内容按章节结构拆分为子 chunk (≤512 token)，
再组装为父 chunk (~1024 token)，子 chunk 明确归属一个父 chunk。

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

import tiktoken

from models.article import Article
from models.chunk import Chunk, ParentChunk

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

    def chunk_article(
        self, article: Article
    ) -> tuple[list[Chunk], list[ParentChunk]]:
        """将一篇文章分块为子 chunks 和父 chunks。

        Args:
            article: 已转为 Markdown 格式的 Article (content 字段为 Markdown)。

        Returns:
            (children, parents) 元组。
        """
        if not article.content or not article.content.strip():
            return [], []

        article_id = article.id or 0
        doc_name = article.title or "Untitled"
        source = article.source or ""
        url = article.url or ""

        if getattr(article, "semantic_skip_indexing", False):
            logger.info(f"跳过非文章页面分块: '{doc_name[:50]}'")
            return [], []

        sections = self._parse_sections(
            article.content,
            doc_name,
            semantic_blocks=getattr(article, "semantic_blocks", None),
        )
        children = self._build_child_chunks(
            sections, article_id, doc_name, source, url
        )

        if not children:
            return [], []

        parents = self._build_parent_chunks(
            children, article_id, doc_name, source, url
        )

        # 回填 parent_chunk_id
        self._assign_parent_ids(children, parents)

        return children, parents

    def chunk_articles(
        self, articles: list[Article]
    ) -> tuple[list[Chunk], list[ParentChunk]]:
        """批量分块，单篇失败不影响整批。"""
        all_children: list[Chunk] = []
        all_parents: list[ParentChunk] = []

        for article in articles:
            try:
                children, parents = self.chunk_article(article)
                all_children.extend(children)
                all_parents.extend(parents)
            except Exception as e:
                logger.warning(
                    f"分块失败: '{article.title[:50]}' — {e}"
                )

        logger.info(
            f"分块完成: {len(articles)} 篇文章 → "
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
        article_id: int,
        doc_name: str,
        source: str,
        url: str,
    ) -> list[Chunk]:
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
            children.append(
                Chunk(
                    chunk_id=f"{article_id}_c{i}",
                    article_id=article_id,
                    parent_chunk_id="",  # 稍后回填
                    content=rc["content"],
                    token_count=rc["token_count"],
                    doc_name=doc_name,
                    heading_path=rc["heading_path"],
                    chunk_index=i,
                    source=source,
                    url=url,
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
        children: list[Chunk],
        article_id: int,
        doc_name: str,
        source: str,
        url: str,
    ) -> list[ParentChunk]:
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
                ParentChunk(
                    parent_chunk_id=f"{article_id}_p0",
                    article_id=article_id,
                    content=parent_content,
                    token_count=self._count_tokens(parent_content),
                    child_chunk_ids=[c.chunk_id for c in children],
                    doc_name=doc_name,
                    source=source,
                    url=url,
                )
            ]

        parents: list[ParentChunk] = []
        i = 0  # 子 chunk 游标
        parent_idx = 0

        while i < len(children):
            group: list[Chunk] = []
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
            parent = ParentChunk(
                parent_chunk_id=f"{article_id}_p{parent_idx}",
                article_id=article_id,
                content=parent_content,
                token_count=self._count_tokens(parent_content),
                child_chunk_ids=[c.chunk_id for c in group],
                doc_name=doc_name,
                source=source,
                url=url,
            )
            parents.append(parent)
            parent_idx += 1

            # 计算下一个父 chunk 的起始位置 (overlap)
            if j >= len(children):
                break

            # 尝试用最后一个子 chunk 做 overlap
            last_child = group[-1]
            if last_child.token_count <= self.overlap_tokens * 2:
                # 下一个父 chunk 从最后一个子 chunk 开始（overlap）
                i = j - 1
            else:
                # 最后一个子 chunk 太大，不 overlap
                i = j

        return parents

    def _assign_parent_ids(
        self, children: list[Chunk], parents: list[ParentChunk]
    ) -> None:
        """为每个子 chunk 分配 parent_chunk_id。

        由于 overlap，一个子 chunk 可能出现在多个父 chunk 中。
        规则：子 chunk 归属于**第一个**包含它的父 chunk。
        """
        assigned: set[str] = set()

        for parent in parents:
            remaining_child_ids = []
            for cid in parent.child_chunk_ids:
                if cid not in assigned:
                    assigned.add(cid)
                    remaining_child_ids.append(cid)
                    # 找到对应的子 chunk 并设置 parent_id
                    for child in children:
                        if child.chunk_id == cid:
                            child.parent_chunk_id = parent.parent_chunk_id
                            break
            # 更新父 chunk 的 child_chunk_ids 为实际归属的子 chunks
            # 注意：parent.content 保持不变（包含 overlap 内容）
            parent.child_chunk_ids = remaining_child_ids

    def _handle_short_document(
        self,
        content: str,
        token_count: int,
        article_id: int,
        doc_name: str,
        source: str,
        url: str,
    ) -> tuple[list[Chunk], list[ParentChunk]]:
        """处理短文档 (≤1024 token)：同时视为子 chunk 和父 chunk。"""
        chunk_id = f"{article_id}_c0"
        parent_id = f"{article_id}_p0"

        # 解析标题路径
        heading_path = [doc_name]
        first_heading = _HEADING_RE.search(content)
        if first_heading:
            heading_path.append(first_heading.group(2).strip())
        chunk_content = self._format_child_content(content, heading_path)
        chunk_tokens = self._count_tokens(chunk_content)

        child = Chunk(
            chunk_id=chunk_id,
            article_id=article_id,
            parent_chunk_id=parent_id,
            content=chunk_content,
            token_count=chunk_tokens,
            doc_name=doc_name,
            heading_path=heading_path,
            chunk_index=0,
            source=source,
            url=url,
        )

        parent = ParentChunk(
            parent_chunk_id=parent_id,
            article_id=article_id,
            content=chunk_content,
            token_count=chunk_tokens,
            child_chunk_ids=[chunk_id],
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
