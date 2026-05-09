from dataclasses import dataclass, field
from datetime import datetime

from models.article import Article, Language
from models.chunk import Chunk, ParentChunk


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


@dataclass
class ChunkSearchResult:
    """封装一条 chunk 级别的搜索结果

    检索流程：
    1. 向量搜索命中子 chunk → 填充 chunk 字段
    2. 根据 parent_chunk_id 查询 PostgreSQL → 填充 parent_chunk 字段
    3. 去重后返回给 LLM 使用 parent_chunk.content 作为上下文
    """

    chunk: Chunk
    parent_chunk: ParentChunk | None = None
    relevance_score: float = 0.0
    match_type: str = "semantic"


@dataclass
class HybridSearchResult:
    """混合检索结果，包含 RRF 融合信息。

    Attributes:
        parent_chunk: 父 chunk 对象
        rrf_score: RRF 融合分数
        match_sources: 匹配来源列表, 如 ["semantic", "keyword"]
        semantic_rank: 在向量检索中的排名 (None 表示未命中)
        keyword_rank: 在关键词检索中的排名 (None 表示未命中)
    """

    parent_chunk: ParentChunk
    rrf_score: float = 0.0
    match_sources: list[str] = field(default_factory=list)
    semantic_rank: int | None = None
    keyword_rank: int | None = None
