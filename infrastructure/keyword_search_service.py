"""基于 PostgreSQL 全文搜索的关键词检索服务

在 parent_chunks 表上执行全文搜索，返回匹配的父 chunks。
使用应用层 jieba 分词实现中文支持。
"""

import structlog
from typing import TYPE_CHECKING

from models.search import ChunkSearchResult
from models.chunk import Chunk

if TYPE_CHECKING:
    from core.protocols import ArticleStoreProtocol

logger = structlog.get_logger(__name__)


class KeywordSearchService:
    """基于 PostgreSQL 全文搜索的关键词检索服务。

    在 parent_chunks 表上执行全文搜索，返回匹配的父 chunks。
    配合 HybridSearchService 作为 RRF 融合的关键词检索通道。
    """

    def __init__(self, article_store: "ArticleStoreProtocol"):
        self._article_store = article_store

    def search(
        self, query: str, top_k: int = 20
    ) -> list[ChunkSearchResult]:
        """执行关键词搜索，返回 ChunkSearchResult 列表。

        调用 ArticleStore 的 search_parent_chunks_by_keyword 方法，
        将结果包装为 ChunkSearchResult（match_type="keyword"）。

        Args:
            query: 用户查询文本。
            top_k: 返回结果数量。

        Returns:
            [ChunkSearchResult, ...] 按 ts_rank 分数降序。
        """
        try:
            keyword_results = self._article_store.search_parent_chunks_by_keyword(
                query=query, top_k=top_k
            )
        except Exception as e:
            logger.error(f"关键词搜索失败: {e}")
            return []

        results: list[ChunkSearchResult] = []
        for parent_chunk, ts_rank_score in keyword_results:
            # 构造一个占位 Chunk 用于兼容 ChunkSearchResult 结构
            placeholder_chunk = Chunk(
                chunk_id=f"{parent_chunk.parent_chunk_id}_kw",
                article_id=parent_chunk.article_id,
                parent_chunk_id=parent_chunk.parent_chunk_id,
                content="",  # 关键词检索不需要子 chunk 内容
                token_count=0,
                doc_name=parent_chunk.doc_name,
                source=parent_chunk.source,
                url=parent_chunk.url,
            )

            results.append(
                ChunkSearchResult(
                    chunk=placeholder_chunk,
                    parent_chunk=parent_chunk,
                    relevance_score=ts_rank_score,
                    match_type="keyword",
                )
            )

        return results
