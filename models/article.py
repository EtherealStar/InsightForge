from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Language(str, Enum):
    EN = "en"
    ZH = "zh"
    UNKNOWN = "unknown"


class ArticleStatus(str, Enum):
    RAW = "raw"
    STORED = "stored"
    PENDING_SUMMARY = "pending_summary"  # 等待 AI 摘要
    SUMMARIZED = "summarized"            # AI 摘要完成，等待向量化
    EMBEDDED = "embedded"


@dataclass
class Article:
    """领域核心实体：一篇新闻文章

    content 字段存储 Markdown 格式的正文文本。
    html_content 仅在抓取阶段临时使用，存储到数据库时已清空。
    """

    title: str
    url: str
    content: str = ""
    html_content: str = ""
    summary: str = ""
    source: str = ""
    author: str = ""
    language: Language = Language.UNKNOWN
    published_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)

    # 数据库相关
    id: int | None = None
    url_hash: str = ""
    status: ArticleStatus = ArticleStatus.RAW

    def to_embedding_text(self, max_chars: int = 2000) -> str:
        """生成用于 Embedding 的文本（2000 字符 ≈ 500-700 中文 tokens）

        使用 Markdown 格式的 content，包含结构化标题层级等语义信息。
        """
        parts = [self.title]
        if self.author:
            parts.append(f"作者: {self.author}")
        parts.append(self.content)
        text = "\n".join(parts)
        return text[:max_chars]

    def to_context_str(self) -> str:
        """生成用于 LLM context 的格式化文本"""
        date_str = (
            self.published_at.strftime("%Y-%m-%d") if self.published_at else "未知"
        )
        author_str = f" | {self.author}" if self.author else ""
        return (
            f"[{self.source} | {date_str}{author_str}] {self.title}\n"
            f"{self.summary or self.content[:300]}\n"
            f"{self.url}"
        )
