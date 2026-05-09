"""Markdown 感知的父子分块服务

将 Markdown 格式的文章内容按章节结构拆分为子 chunk (≤512 token)，
再组装为父 chunk (~1024 token)，子 chunk 明确归属一个父 chunk。

分块策略：
1. 按标题行 (# ## ### ...) 分割文档为 sections
2. 每个 section 成为一个候选子 chunk，超长则按段落再分
3. 子 chunk 内容附带标题路径前缀 (doc_name > 一级标题 > 二级标题)
4. 贪心组合连续子 chunk 为 ~1024 token 的父 chunk
5. 父 chunk 之间通过共享尾部子 chunk 实现 overlap
6. 短文档 (≤1024 token) 同时视为子 chunk 和父 chunk
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

        total_tokens = self._count_tokens(article.content)

        # 短文档：同时视为子 chunk 和父 chunk
        if total_tokens <= self.target_parent_tokens:
            return self._handle_short_document(
                article.content, total_tokens, article_id, doc_name, source, url
            )

        # 标准流程
        sections = self._parse_sections(article.content, doc_name)
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
        self, markdown: str, doc_name: str
    ) -> list[dict]:
        """解析 Markdown 的章节结构。

        返回 list[dict]，每项：
            {
                "heading_level": int,       # 标题级别 1-6
                "heading_text": str,        # 标题文本
                "heading_path": list[str],  # 从文档名到当前标题的层级路径
                "content": str,             # 该 section 的内容（含标题行本身）
            }
        """
        # 找到所有标题行的位置
        heading_matches = list(_HEADING_RE.finditer(markdown))

        if not heading_matches:
            # 无标题结构，整篇作为一个 section
            return [
                {
                    "heading_level": 0,
                    "heading_text": doc_name,
                    "heading_path": [doc_name],
                    "content": markdown.strip(),
                }
            ]

        sections = []
        # 维护标题层级栈
        heading_stack: list[tuple[int, str]] = []  # [(level, text), ...]

        for i, match in enumerate(heading_matches):
            level = len(match.group(1))  # # = 1, ## = 2, ...
            heading_text = match.group(2).strip()

            # 确定 section 文本范围
            start = match.start()
            end = heading_matches[i + 1].start() if i + 1 < len(heading_matches) else len(markdown)
            section_content = markdown[start:end].strip()

            # 更新标题层级栈
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, heading_text))

            # 构建标题路径: doc_name + 栈中的标题链
            heading_path = [doc_name] + [h[1] for h in heading_stack]

            sections.append(
                {
                    "heading_level": level,
                    "heading_text": heading_text,
                    "heading_path": heading_path,
                    "content": section_content,
                }
            )

        # 如果标题前有内容（前言），作为第一个 section
        first_heading_start = heading_matches[0].start()
        preamble = markdown[:first_heading_start].strip()
        if preamble:
            sections.insert(
                0,
                {
                    "heading_level": 0,
                    "heading_text": doc_name,
                    "heading_path": [doc_name],
                    "content": preamble,
                },
            )

        return sections

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
        - 若 section 超过限制，按段落继续分割
        - 过小的 section（仅标题行无内容）合并到下一个 section
        """
        raw_chunks: list[dict] = []

        for section in sections:
            content = section["content"]
            tokens = self._count_tokens(content)

            if tokens <= self.max_child_tokens:
                raw_chunks.append(
                    {
                        "content": content,
                        "token_count": tokens,
                        "heading_path": section["heading_path"],
                    }
                )
            else:
                # 按段落分割
                sub_chunks = self._split_by_paragraphs(
                    content, section["heading_path"]
                )
                raw_chunks.extend(sub_chunks)

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

    def _split_by_paragraphs(
        self, text: str, heading_path: list[str]
    ) -> list[dict]:
        """将超长文本按段落切分为 ≤max_child_tokens 的片段。"""
        paragraphs = re.split(r"\n{2,}", text)
        chunks: list[dict] = []
        current_text = ""
        current_tokens = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_tokens = self._count_tokens(para)

            # 单段落就超限，强制按 token 截断
            if para_tokens > self.max_child_tokens:
                # 先把当前缓冲区提交
                if current_text:
                    chunks.append(
                        {
                            "content": current_text.strip(),
                            "token_count": current_tokens,
                            "heading_path": heading_path,
                        }
                    )
                    current_text = ""
                    current_tokens = 0

                # 强制截断长段落
                sub_parts = self._force_split_text(para, heading_path)
                chunks.extend(sub_parts)
                continue

            # 加入当前段落后是否超限
            if current_tokens + para_tokens > self.max_child_tokens:
                # 提交当前缓冲区
                if current_text:
                    chunks.append(
                        {
                            "content": current_text.strip(),
                            "token_count": current_tokens,
                            "heading_path": heading_path,
                        }
                    )
                current_text = para
                current_tokens = para_tokens
            else:
                current_text = (
                    f"{current_text}\n\n{para}" if current_text else para
                )
                current_tokens += para_tokens

        # 提交剩余内容
        if current_text.strip():
            chunks.append(
                {
                    "content": current_text.strip(),
                    "token_count": self._count_tokens(current_text.strip()),
                    "heading_path": heading_path,
                }
            )

        return chunks

    def _force_split_text(
        self, text: str, heading_path: list[str]
    ) -> list[dict]:
        """将超长文本按 token 限制强制截断。"""
        tokens = self._enc.encode(text)
        chunks = []
        for i in range(0, len(tokens), self.max_child_tokens):
            chunk_tokens = tokens[i: i + self.max_child_tokens]
            chunk_text = self._enc.decode(chunk_tokens)
            chunks.append(
                {
                    "content": chunk_text,
                    "token_count": len(chunk_tokens),
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
                and merged[-1]["token_count"] + chunk["token_count"]
                <= self.max_child_tokens
            ):
                # 合并到前一个
                merged[-1]["content"] += "\n\n" + chunk["content"]
                merged[-1]["token_count"] += chunk["token_count"]
                # 保留更长的 heading_path
                if len(chunk["heading_path"]) > len(merged[-1]["heading_path"]):
                    merged[-1]["heading_path"] = chunk["heading_path"]
            else:
                merged.append(dict(chunk))

        return merged

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

        child = Chunk(
            chunk_id=chunk_id,
            article_id=article_id,
            parent_chunk_id=parent_id,
            content=content,
            token_count=token_count,
            doc_name=doc_name,
            heading_path=heading_path,
            chunk_index=0,
            source=source,
            url=url,
        )

        parent = ParentChunk(
            parent_chunk_id=parent_id,
            article_id=article_id,
            content=content,
            token_count=token_count,
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
