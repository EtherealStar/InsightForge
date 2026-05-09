"""内置工具：查询本地新闻知识库（混合检索 + 父子分块 + 支持 Rerank 精排）

支持三种检索模式：
- hybrid（默认）：向量语义检索 + PostgreSQL 关键词检索 + RRF 融合
- semantic：仅向量语义检索（原有行为）
- keyword：仅关键词全文搜索

可选使用 Rerank 大模型对候选结果进行精排以提升结果质量。
"""

import structlog
from typing import Any

from agent.tools.base import BaseTool, ToolParameter
from core.protocols import (
    VectorStoreProtocol,
    EmbeddingClientProtocol,
    ArticleStoreProtocol,
    RerankClientProtocol,
)

logger = structlog.get_logger(__name__)


class QueryKnowledgeBaseTool(BaseTool):
    """查询本地新闻向量知识库，支持混合检索 + 父子分块召回 + 可选 Rerank 精排。

    工作流程（hybrid 模式）：
    1. 并行执行向量检索和关键词检索
    2. 使用 RRF 融合两路结果
    3. 从 PostgreSQL 获取融合后的父 chunks
    4. （可选）使用 Rerank 大模型精排
    5. 返回最终 top_k 父 chunks 给 LLM
    """

    def __init__(
        self,
        embedding_client: EmbeddingClientProtocol,
        vector_store: VectorStoreProtocol,
        article_store: ArticleStoreProtocol,
        rerank_client: "RerankClientProtocol | None" = None,
        rerank_enabled: bool = False,
        rerank_top_k_multiplier: int = 3,
        hybrid_search_service: Any = None,
        hybrid_search_enabled: bool = True,
    ):
        self._embedding_client = embedding_client
        self._vector_store = vector_store
        self._article_store = article_store
        self._rerank_client = rerank_client
        self._rerank_enabled = rerank_enabled
        self._rerank_top_k_multiplier = rerank_top_k_multiplier
        self._hybrid_search = hybrid_search_service
        self._hybrid_search_enabled = hybrid_search_enabled

    @property
    def name(self) -> str:
        return "query_knowledge_base"

    @property
    def description(self) -> str:
        return (
            "查询本地新闻向量知识库，基于混合检索（语义+关键词+RRF融合）检索相关文章。"
            "支持使用 Rerank 大模型对检索结果精排以提升准确性。"
            "适用于用户询问特定话题、事件或领域的新闻时使用。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="搜索查询文本，描述要查找的新闻内容",
            ),
            ToolParameter(
                name="top_k",
                type="integer",
                description="返回结果数量（父 chunk 级别）",
                required=False,
                default=5,
            ),
            ToolParameter(
                name="use_rerank",
                type="boolean",
                description="是否使用 Rerank 模型精排结果（需要已配置 Rerank 服务）",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="search_mode",
                type="string",
                description="检索模式: hybrid(混合检索), semantic(仅语义), keyword(仅关键词)",
                required=False,
                default="hybrid",
            ),
        ]

    def _run(
        self,
        query: str,
        top_k: int = 5,
        use_rerank: bool = True,
        search_mode: str = "hybrid",
        **kwargs: Any,
    ) -> str:
        """执行知识库查询。

        search_mode:
        - "hybrid" (默认): 向量检索 + 关键词检索 + RRF 融合
        - "semantic": 仅向量语义检索
        - "keyword": 仅关键词全文搜索
        """
        # 判断是否实际启用 rerank
        do_rerank = (
            use_rerank
            and self._rerank_enabled
            and self._rerank_client is not None
        )

        # 路由到不同的检索模式
        if (
            search_mode == "hybrid"
            and self._hybrid_search_enabled
            and self._hybrid_search is not None
        ):
            return self._run_hybrid(query, top_k, do_rerank)
        elif search_mode == "keyword":
            return self._run_keyword_only(query, top_k)
        else:
            return self._run_semantic_only(query, top_k, do_rerank)

    # ------------------------------------------------------------------
    # 混合检索路径 (新)
    # ------------------------------------------------------------------

    def _run_hybrid(self, query: str, top_k: int, do_rerank: bool) -> str:
        """混合检索：向量 + 关键词 + RRF 融合。"""
        # 多召回以便 rerank
        fetch_k = top_k * 2 if do_rerank else top_k

        hybrid_results = self._hybrid_search.search(
            query=query,
            top_k=fetch_k,
        )

        if not hybrid_results:
            # 回退到纯关键词搜索
            logger.warning("混合检索无结果，尝试关键词回退")
            articles = self._article_store.search_by_keyword(query, top_k)
            if not articles:
                return "未找到相关新闻文章。"
            return self._format_keyword_article_results(articles)

        parent_chunks = [r.parent_chunk for r in hybrid_results]
        match_info = {
            r.parent_chunk.parent_chunk_id: r.match_sources
            for r in hybrid_results
        }

        # 可选 Rerank 精排
        if do_rerank and len(parent_chunks) > 1:
            parent_chunks = self._apply_parent_rerank(query, parent_chunks)

        # 取最终 top_k
        final_chunks = parent_chunks[:top_k]

        # 格式化输出
        return self._format_hybrid_results(final_chunks, match_info)

    # ------------------------------------------------------------------
    # 纯语义检索路径 (原有)
    # ------------------------------------------------------------------

    def _run_semantic_only(
        self, query: str, top_k: int, do_rerank: bool
    ) -> str:
        """仅向量语义检索（原有逻辑）。"""
        # 1. 生成查询向量
        query_embeddings = self._embedding_client.embed([query])

        if not query_embeddings:
            logger.warning("查询向量生成失败，回退到关键词搜索")
            articles = self._article_store.search_by_keyword(query, top_k)
            if not articles:
                return "未找到相关新闻文章。"
            return self._format_keyword_article_results(articles)

        # 2. 搜索子 chunks
        child_k = (
            top_k * self._rerank_top_k_multiplier if do_rerank else top_k * 2
        )
        child_k = max(child_k, top_k * 2)

        chunk_results = self._vector_store.search_chunks(
            query_embedding=query_embeddings[0],
            top_k=child_k,
        )

        if not chunk_results:
            return "未找到相关新闻文章。"

        # 3. 可选 Rerank 精排
        if do_rerank and len(chunk_results) > 1:
            chunk_results = self._apply_chunk_rerank(query, chunk_results)

        # 4. 按 parent_chunk_id 去重
        seen_parent_ids: set[str] = set()
        unique_parent_ids: list[str] = []
        parent_scores: dict[str, float] = {}

        for cr in chunk_results:
            pid = cr.chunk.parent_chunk_id
            if pid not in seen_parent_ids:
                seen_parent_ids.add(pid)
                unique_parent_ids.append(pid)
                parent_scores[pid] = cr.relevance_score
                if len(unique_parent_ids) >= top_k:
                    break

        if not unique_parent_ids:
            return "未找到相关新闻文章。"

        # 5. 获取父 chunk 内容
        parent_chunks = self._article_store.get_parent_chunks_by_ids(
            unique_parent_ids
        )

        if not parent_chunks:
            logger.warning("无法获取父 chunks，回退使用子 chunk 内容")
            return self._format_child_results(chunk_results[:top_k])

        # 6. 格式化输出
        method = "Rerank 精排" if do_rerank else "语义搜索"
        return self._format_parent_results(
            parent_chunks, parent_scores, method
        )

    # ------------------------------------------------------------------
    # 纯关键词检索路径 (新)
    # ------------------------------------------------------------------

    def _run_keyword_only(self, query: str, top_k: int) -> str:
        """仅关键词全文搜索。"""
        if self._hybrid_search is None:
            # 无混合检索服务时，回退到文章级关键词搜索
            articles = self._article_store.search_by_keyword(query, top_k)
            if not articles:
                return "未找到相关新闻文章。"
            return self._format_keyword_article_results(articles)

        # 使用关键词检索服务
        try:
            results = self._article_store.search_parent_chunks_by_keyword(
                query=query, top_k=top_k
            )
        except Exception as e:
            logger.error(f"关键词检索失败: {e}")
            return "关键词检索出错，请稍后重试。"

        if not results:
            return "未找到相关新闻文章。"

        parent_chunks = [pc for pc, _ in results]
        parent_scores = {pc.parent_chunk_id: score for pc, score in results}
        return self._format_parent_results(
            parent_chunks, parent_scores, "关键词搜索"
        )

    # ------------------------------------------------------------------
    # Rerank 方法
    # ------------------------------------------------------------------

    def _apply_chunk_rerank(self, query: str, candidates: list) -> list:
        """使用 Rerank 模型对候选子 chunks 精排。"""
        try:
            documents = [cr.chunk.content for cr in candidates]

            reranked = self._rerank_client.rerank(
                query=query,
                documents=documents,
                top_n=len(candidates),
            )

            if not reranked:
                logger.warning("Rerank 返回空结果，回退到向量检索排序")
                return candidates

            reranked_results = []
            for item in reranked:
                idx = item["index"]
                if 0 <= idx < len(candidates):
                    result = candidates[idx]
                    result.relevance_score = item["relevance_score"]
                    reranked_results.append(result)

            logger.info(
                f"Rerank 精排完成: {len(candidates)} 候选 → "
                f"{len(reranked_results)} 条结果"
            )
            return reranked_results

        except Exception as e:
            logger.error(f"Rerank 失败，回退到向量检索排序: {e}")
            return candidates

    def _apply_parent_rerank(
        self, query: str, parent_chunks: list
    ) -> list:
        """使用 Rerank 模型对父 chunks 精排。"""
        try:
            documents = [pc.content for pc in parent_chunks]

            reranked = self._rerank_client.rerank(
                query=query,
                documents=documents,
                top_n=len(parent_chunks),
            )

            if not reranked:
                logger.warning("Rerank 返回空结果，保持 RRF 排序")
                return parent_chunks

            reranked_chunks = []
            for item in reranked:
                idx = item["index"]
                if 0 <= idx < len(parent_chunks):
                    reranked_chunks.append(parent_chunks[idx])

            logger.info(
                f"父 chunk Rerank 精排: {len(parent_chunks)} → "
                f"{len(reranked_chunks)} 条"
            )
            return reranked_chunks

        except Exception as e:
            logger.error(f"父 chunk Rerank 失败: {e}")
            return parent_chunks

    # ------------------------------------------------------------------
    # 格式化方法
    # ------------------------------------------------------------------

    @staticmethod
    def _format_hybrid_results(
        parent_chunks: list, match_info: dict
    ) -> str:
        """格式化混合检索结果。"""
        parts = []
        for i, pc in enumerate(parent_chunks, 1):
            sources = match_info.get(pc.parent_chunk_id, [])
            source_tag = "+".join(sources) if sources else "unknown"
            heading_info = f"  来源: {pc.source}" if pc.source else ""
            parts.append(
                f"{i}. 【{pc.doc_name}】（匹配: {source_tag}）\n"
                f"   {heading_info}\n"
                f"   URL: {pc.url}\n"
                f"   ---\n"
                f"   {pc.content[:1500]}"
            )
        return (
            f"混合检索找到 {len(parent_chunks)} 条相关内容：\n\n"
            + "\n\n".join(parts)
        )

    @staticmethod
    def _format_parent_results(
        parent_chunks: list, parent_scores: dict, method: str
    ) -> str:
        """格式化父 chunk 搜索结果为文本。"""
        parts = []
        for i, pc in enumerate(parent_chunks, 1):
            score = parent_scores.get(pc.parent_chunk_id, 0.0)
            heading_info = f"  来源: {pc.source}" if pc.source else ""
            parts.append(
                f"{i}. 【{pc.doc_name}】（相关度: {score:.2f}）\n"
                f"   {heading_info}\n"
                f"   URL: {pc.url}\n"
                f"   ---\n"
                f"   {pc.content[:1500]}"
            )
        return (
            f"{method}找到 {len(parent_chunks)} 条相关内容：\n\n"
            + "\n\n".join(parts)
        )

    @staticmethod
    def _format_child_results(chunk_results: list) -> str:
        """回退：格式化子 chunk 搜索结果。"""
        parts = []
        for i, cr in enumerate(chunk_results, 1):
            chunk = cr.chunk
            path_str = (
                " > ".join(chunk.heading_path)
                if chunk.heading_path
                else chunk.doc_name
            )
            parts.append(
                f"{i}. 【{path_str}】（相关度: {cr.relevance_score:.2f}）\n"
                f"   来源: {chunk.source}\n"
                f"   ---\n"
                f"   {chunk.content[:800]}"
            )
        return (
            f"语义搜索找到 {len(chunk_results)} 条相关内容：\n\n"
            + "\n\n".join(parts)
        )

    @staticmethod
    def _format_keyword_article_results(articles: list) -> str:
        """格式化文章级关键词搜索结果。"""
        parts = []
        for i, article in enumerate(articles, 1):
            parts.append(
                f"{i}. 【{article.source}】{article.title}\n"
                f"   ID: {article.id}\n"
                f"   发布时间: {article.published_at}\n"
                f"   摘要: {article.summary or '无摘要'}\n"
                f"   URL: {article.url}"
            )
        return (
            f"关键词搜索找到 {len(articles)} 条结果：\n\n"
            + "\n\n".join(parts)
        )
