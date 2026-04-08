from dataclasses import dataclass
from datetime import datetime

from models.article import Article, Language


@dataclass
class SearchQuery:
    """封装一次搜索请求"""

    text: str
    top_k: int = 10
    sources: list[str] | None = None
    language: Language | None = None
    date_from: datetime | None = None


@dataclass
class SearchResult:
    """封装一条搜索结果"""

    article: Article
    relevance_score: float = 0.0
    match_type: str = "semantic"  # "semantic" | "keyword" | "hybrid"
