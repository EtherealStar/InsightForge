"""混合检索服务：向量语义搜索 + 关键词全文搜索 + RRF 融合

编排向量检索（Qdrant）和关键词检索（PostgreSQL FTS）两路结果，
使用 Reciprocal Rank Fusion (RRF) 算法融合排名，
输出统一的排序结果。

RRF 公式：
    Score_RRF(d) = Σ w_r / (k + rank_r(d))
    其中 k=60 是平滑常数，w_r 是每路检索的权重。
"""

import structlog
from typing import TYPE_CHECKING

from models.chunk import ParentChunk
from models.search import HybridSearchResult

if TYPE_CHECKING:
    from core.protocols import (
        VectorStoreProtocol,
        EmbeddingClientProtocol,
        ArticleStoreProtocol,
    )
    from infrastructure.keyword_search_service import KeywordSearchService

logger = structlog.get_logger(__name__)


class HybridSearchService:
    """混合检索服务：向量语义搜索 + 关键词全文搜索 + RRF 融合。

    两路检索并行执行，结果通过 RRF 算法融合为统一排名。
    支持加权 RRF，可调节向量/关键词检索的相对权重。
    """

    def __init__(
        self,
        vector_store: "VectorStoreProtocol",
        embedding_client: "EmbeddingClientProtocol",
        article_store: "ArticleStoreProtocol",
        keyword_search_service: "KeywordSearchService",
        rrf_k: int = 60,
    ):
        self._vector_store = vector_store
        self._embedding_client = embedding_client
        self._article_store = article_store
        self._keyword_search = keyword_search_service
        self._rrf_k = rrf_k

    def search(
        self,
        query: str,
        top_k: int = 5,
        vector_weight: float = 1.0,
        keyword_weight: float = 1.0,
        vector_candidates: int | None = None,
        keyword_candidates: int | None = None,
    ) -> list[HybridSearchResult]:
        """执行混合检索。

        流程：
        1. 并行执行向量检索和关键词检索
        2. 将两路结果转换为 parent_chunk_id 级别的排名列表
        3. 使用 RRF 融合两路排名
        4. 从 PostgreSQL 获取融合后的父 chunk 内容
        5. 按 RRF 分数排序，返回 top_k

        Args:
            query: 用户查询文本。
            top_k: 最终返回的结果数量。
            vector_weight: 向量检索通道权重（默认 1.0）。
            keyword_weight: 关键词检索通道权重（默认 1.0）。
            vector_candidates: 向量检索候选数量（默认 top_k*3）。
            keyword_candidates: 关键词检索候选数量（默认 20）。

        Returns:
            [HybridSearchResult, ...] 按 RRF 分数降序。
        """
        v_candidates = vector_candidates or top_k * 3
        k_candidates = keyword_candidates or 20

        # ------------------------------------------------------------------
        # 1. 向量检索通道
        # ------------------------------------------------------------------
        semantic_parent_ranking: list[str] = []  # parent_chunk_id 排名列表
        semantic_parent_map: dict[str, int] = {}  # parent_chunk_id -> rank

        try:
            query_embeddings = self._embedding_client.embed([query])
            if query_embeddings:
                chunk_results = self._vector_store.search_chunks(
                    query_embedding=query_embeddings[0],
                    top_k=v_candidates,
                )

                # 子 chunk → 按 parent_chunk_id 去重，保留顺序
                seen: set[str] = set()
                for cr in chunk_results:
                    pid = cr.chunk.parent_chunk_id
                    if pid not in seen:
                        seen.add(pid)
                        rank = len(semantic_parent_ranking)
                        semantic_parent_ranking.append(pid)
                        semantic_parent_map[pid] = rank
        except Exception as e:
            logger.warning(f"向量检索通道失败，仅使用关键词检索: {e}")

        # ------------------------------------------------------------------
        # 2. 关键词检索通道
        # ------------------------------------------------------------------
        keyword_parent_ranking: list[str] = []
        keyword_parent_map: dict[str, int] = {}

        try:
            kw_results = self._keyword_search.search(
                query=query, top_k=k_candidates
            )
            for i, cr in enumerate(kw_results):
                pid = cr.chunk.parent_chunk_id
                if pid not in keyword_parent_map:
                    keyword_parent_ranking.append(pid)
                    keyword_parent_map[pid] = len(keyword_parent_ranking) - 1
        except Exception as e:
            logger.warning(f"关键词检索通道失败，仅使用向量检索: {e}")

        # ------------------------------------------------------------------
        # 3. RRF 融合
        # ------------------------------------------------------------------
        if not semantic_parent_ranking and not keyword_parent_ranking:
            return []

        fused = self._rrf_fuse(
            ranked_lists=[semantic_parent_ranking, keyword_parent_ranking],
            weights=[vector_weight, keyword_weight],
            k=self._rrf_k,
        )

        # 取 top_k 个融合结果
        top_fused = fused[: top_k]

        if not top_fused:
            return []

        # ------------------------------------------------------------------
        # 4. 获取父 chunk 内容
        # ------------------------------------------------------------------
        parent_ids = [pid for pid, _ in top_fused]
        parent_chunks = self._article_store.get_parent_chunks_by_ids(parent_ids)
        parent_map: dict[str, ParentChunk] = {
            pc.parent_chunk_id: pc for pc in parent_chunks
        }

        # ------------------------------------------------------------------
        # 5. 组装结果
        # ------------------------------------------------------------------
        results: list[HybridSearchResult] = []
        for pid, rrf_score in top_fused:
            pc = parent_map.get(pid)
            if not pc:
                continue

            match_sources = []
            s_rank = semantic_parent_map.get(pid)
            k_rank = keyword_parent_map.get(pid)

            if s_rank is not None:
                match_sources.append("semantic")
            if k_rank is not None:
                match_sources.append("keyword")

            results.append(
                HybridSearchResult(
                    parent_chunk=pc,
                    rrf_score=rrf_score,
                    match_sources=match_sources,
                    semantic_rank=s_rank + 1 if s_rank is not None else None,
                    keyword_rank=k_rank + 1 if k_rank is not None else None,
                )
            )

        logger.info(
            f"混合检索完成: query='{query[:50]}' | "
            f"向量通道={len(semantic_parent_ranking)}条 | "
            f"关键词通道={len(keyword_parent_ranking)}条 | "
            f"RRF融合={len(results)}条"
        )
        return results

    @staticmethod
    def _rrf_fuse(
        ranked_lists: list[list[str]],
        weights: list[float] | None = None,
        k: int = 60,
    ) -> list[tuple[str, float]]:
        """Reciprocal Rank Fusion 算法。

        对多路检索结果按 RRF 公式计算融合分数，
        输出统一排序的结果列表。

        公式：Score_RRF(d) = Σ w_r / (k + rank_r(d) + 1)
        其中 rank_r(d) 为 0-indexed 排名。

        Args:
            ranked_lists: 多个排名列表，每个列表包含 ID 按排名排序。
            weights: 每路检索的权重（可选），默认等权 1.0。
            k: 平滑常数，默认 60。

        Returns:
            [(id, rrf_score), ...] 按 RRF 分数降序排列。
        """
        if weights is None:
            weights = [1.0] * len(ranked_lists)

        fused_scores: dict[str, float] = {}

        for ranked_list, weight in zip(ranked_lists, weights):
            for rank, doc_id in enumerate(ranked_list):
                # RRF: weight / (k + rank + 1)
                rrf_score = weight / (k + rank + 1)

                if doc_id not in fused_scores:
                    fused_scores[doc_id] = 0.0
                fused_scores[doc_id] += rrf_score

        # 按 RRF 分数降序排序
        sorted_results = sorted(
            fused_scores.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_results
