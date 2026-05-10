import json
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
class ArticleEntity:
    """领域实体：一篇新闻文章

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


@dataclass
class ArticleDTO:
    """文章传输对象：用于数据库/API 边界的数据承载。

    DTO 不包含领域行为，避免持久化和序列化细节污染实体方法。
    """

    title: str
    url: str
    content: str = ""
    html_content: str = ""
    summary: str = ""
    source: str = ""
    author: str = ""
    language: str = Language.UNKNOWN.value
    published_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)
    id: int | None = None
    url_hash: str = ""
    status: str = ArticleStatus.RAW.value


class ArticleMapper:
    """Article entity/DTO 转换工具。"""

    @staticmethod
    def entity_to_dto(article: ArticleEntity) -> ArticleDTO:
        return ArticleDTO(
            id=article.id,
            url_hash=article.url_hash,
            title=article.title,
            url=article.url,
            content=article.content,
            html_content=article.html_content,
            summary=article.summary,
            source=article.source,
            author=article.author,
            language=article.language.value,
            published_at=article.published_at,
            created_at=article.created_at,
            tags=article.tags,
            status=article.status.value,
        )

    @staticmethod
    def dto_to_entity(dto: ArticleDTO) -> ArticleEntity:
        return ArticleEntity(
            id=dto.id,
            url_hash=dto.url_hash,
            title=dto.title,
            url=dto.url,
            content=dto.content,
            html_content=dto.html_content,
            summary=dto.summary,
            source=dto.source,
            author=dto.author,
            language=Language(dto.language) if dto.language else Language.UNKNOWN,
            published_at=dto.published_at,
            created_at=dto.created_at,
            tags=dto.tags,
            status=ArticleStatus(dto.status) if dto.status else ArticleStatus.STORED,
        )

    @staticmethod
    def row_to_dto(row) -> ArticleDTO:
        keys = row.keys()

        published_at = row["published_at"]
        if isinstance(published_at, str):
            try:
                published_at = datetime.fromisoformat(published_at)
            except (ValueError, TypeError):
                published_at = None

        created_at = row["created_at"] or datetime.now()
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except (ValueError, TypeError):
                created_at = datetime.now()

        tags = row.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []

        return ArticleDTO(
            id=row["id"],
            url_hash=row["url_hash"],
            title=row["title"],
            url=row["url"],
            content=row["content"] or "",
            html_content=row["html_content"] if "html_content" in keys and row["html_content"] else "",
            summary=row["summary"] or "",
            source=row["source"] or "",
            author=row["author"] if "author" in keys and row["author"] else "",
            language=row["language"] or Language.UNKNOWN.value,
            published_at=published_at,
            created_at=created_at,
            tags=tags,
            status=row["status"] or ArticleStatus.STORED.value,
        )

    @staticmethod
    def row_to_entity(row) -> ArticleEntity:
        return ArticleMapper.dto_to_entity(ArticleMapper.row_to_dto(row))


# Backward-compatible import surface for existing services/tests.
Article = ArticleEntity
