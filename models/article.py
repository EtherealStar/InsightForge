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
    EMBEDDED = "embedded"


@dataclass
class Article:
    """领域核心实体：一篇新闻文章"""

    title: str
    url: str
    content: str = ""
    html_content: str = ""
    summary: str = ""
    source: str = ""
    language: Language = Language.UNKNOWN
    published_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)

    # 数据库相关
    id: int | None = None
    url_hash: str = ""
    status: ArticleStatus = ArticleStatus.RAW

    def to_embedding_text(self, max_chars: int = 2000) -> str:
        """生成用于 Embedding 的文本（2000 字符 ≈ 500-700 中文 tokens）"""
        text = f"{self.title}\n{self.content}"
        return text[:max_chars]

    def to_context_str(self) -> str:
        """生成用于 LLM context 的格式化文本"""
        date_str = (
            self.published_at.strftime("%Y-%m-%d") if self.published_at else "未知"
        )
        return (
            f"[{self.source} | {date_str}] {self.title}\n"
            f"{self.summary or self.content[:300]}\n"
            f"{self.url}"
        )
