"""基于 PostgreSQL 全文搜索的关键词检索服务

在 document_parent_chunks 表上执行全文搜索，返回匹配的父 chunks。
使用应用层 jieba 分词实现中文支持。
"""

import structlog
from typing import TYPE_CHECKING

from models.search import ChunkSearchResult
from models.document import ChildChunkPoint

if TYPE_CHECKING:
    from core.protocols import DocumentStoreProtocol

logger = structlog.get_logger(__name__)


class KeywordSearchService:
    """基于 PostgreSQL 全文搜索的关键词检索服务。

    在 document_parent_chunks 表上执行全文搜索，返回匹配的父 chunks。
    配合 HybridSearchService 作为 RRF 融合的关键词检索通道。
    """

    def __init__(self, document_store: "DocumentStoreProtocol"):
        self._document_store = document_store

    def search(
        self,
        query: str,
        top_k: int = 20,
        filters: dict | None = None,
    ) -> list[ChunkSearchResult]:
        """执行关键词搜索，返回 ChunkSearchResult 列表。

        调用 DocumentStore 的 search_parent_chunks_by_keyword 方法，
        将结果包装为 ChunkSearchResult（match_type="keyword"）。

        Args:
            query: 用户查询文本。
            top_k: 返回结果数量。

        Returns:
            [ChunkSearchResult, ...] 按 ts_rank 分数降序。
        """
        try:
            keyword_results = self._document_store.search_parent_chunks_by_keyword(
                query=query,
                top_k=top_k,
                filters=filters,
            )
        except Exception as e:
            logger.error(f"关键词搜索失败: {e}")
            return []

        results: list[ChunkSearchResult] = []
        for parent_chunk, ts_rank_score in keyword_results:
            placeholder_chunk = ChildChunkPoint(
                point_id=f"{parent_chunk.parent_chunk_id}:kw",
                document_id=parent_chunk.document_id,
                parent_chunk_id=parent_chunk.parent_chunk_id,
                content="",  # 关键词检索不需要子 chunk 内容
                token_count=0,
                chunk_index=0,
                doc_name=parent_chunk.doc_name,
                source=parent_chunk.source,
                url=parent_chunk.url,
                source_type=parent_chunk.source_type,
                document_type=parent_chunk.document_type,
                competitor_ids=list(parent_chunk.competitor_ids),
                product_ids=list(parent_chunk.product_ids),
                language=parent_chunk.language,
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
