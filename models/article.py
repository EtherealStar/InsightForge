"""情报条目数据模型

ArticleEntity 同时用作新闻文章和竞品情报的承载实体。
竞品分析场景下，intel_type / competitor_ids 等字段提供情报分类与关联能力。
"""
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
    EMBEDDED = "embedded"


class IntelType(str, Enum):
    """竞品情报类型分类"""
    PRICING = "pricing"            # 定价变动
    FEATURE = "feature"            # 功能发布/更新
    STRATEGY = "strategy"          # 战略动向
    PARTNERSHIP = "partnership"    # 合作/并购
    HIRING = "hiring"              # 招聘动向
    FUNDING = "funding"            # 融资信息
    MARKET = "market"              # 市场分析
    REVIEW = "review"              # 用户评价/口碑
    GENERAL = "general"            # 通用情报


@dataclass
class ArticleEntity:
    """领域实体：一条竞品情报 / 新闻文章

    content 字段存储 Markdown 格式的正文文本。
    html_content 仅在抓取阶段临时使用，存储到数据库时已清空。

    竞品分析扩展字段：
    - intel_type: 情报类型分类（AI 自动标注）
    - competitor_ids: 关联的竞品 ID 列表
    - product_ids: 关联的竞品产品 ID 列表
    - source_reliability: 来源可信度评分 (0.0~1.0)
    - analysis_notes: AI 分析批注
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
    semantic_markdown: str = ""
    semantic_blocks: list[dict] = field(default_factory=list)
    semantic_page_type: str = ""
    semantic_confidence: float = 0.0
    semantic_skip_indexing: bool = False

    # 数据库相关
    id: int | None = None
    url_hash: str = ""
    status: ArticleStatus = ArticleStatus.RAW

    # --- 竞品分析扩展字段 ---
    intel_type: IntelType = IntelType.GENERAL
    competitor_ids: list[int] = field(default_factory=list)
    product_ids: list[int] = field(default_factory=list)
    source_reliability: float = 0.0      # 来源可信度 0.0~1.0
    analysis_notes: str = ""              # AI 分析批注

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
            status=ArticleMapper._status_from_value(dto.status),
        )

    @staticmethod
    def _status_from_value(value: str | None) -> ArticleStatus:
        if not value:
            return ArticleStatus.STORED
        try:
            return ArticleStatus(value)
        except ValueError:
            return ArticleStatus.STORED

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
