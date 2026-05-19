"""编排 抓取 → Markdown转换 → 存储 → 分块 → 向量化 的完整流水线"""
from __future__ import annotations

import structlog
from typing import TYPE_CHECKING

from core.protocols import (
    ArticleStoreProtocol,
    VectorStoreProtocol,
    EmbeddingClientProtocol,
)
from infrastructure.collector import NewsCollector
from infrastructure.markdown_converter import NewsMarkdownConverter

if TYPE_CHECKING:
    from infrastructure.web_crawler import WebCrawler
    from infrastructure.chunking_service import ChunkingService
    from services.summary_service import SummaryService

logger = structlog.get_logger(__name__)


class PipelineService:
    """编排 抓取 → Markdown转换 → 存储 → 分块 → 向量化 的完整流水线"""

    def __init__(
        self,
        collector: NewsCollector,
        article_store: ArticleStoreProtocol,
        vector_store: VectorStoreProtocol,
        embedding_client: EmbeddingClientProtocol,
        chunking_service: "ChunkingService | None" = None,
        web_crawler: "WebCrawler | None" = None,
        crawl_sites: list[dict] | None = None,
        markdown_converter: NewsMarkdownConverter | None = None,
        markdown_output_path: str | None = None,
        summary_service: "SummaryService | None" = None,
    ):
        self.collector = collector
        self.article_store = article_store
        self.vector_store = vector_store
        self.embedding_client = embedding_client
        self.chunking_service = chunking_service
        self.web_crawler = web_crawler
        self.crawl_sites = crawl_sites or []
        self.md_converter = markdown_converter or NewsMarkdownConverter()
        self.markdown_output_path = markdown_output_path
        self.summary_service = summary_service

    def _collect_all(self) -> tuple[list, list[str]]:
        """从所有数据源（RSS + 网页爬取）汇总文章"""
        articles = []
        errors = []

        # RSS 抓取
        try:
            rss_articles = self.collector.fetch_all()
            articles.extend(rss_articles)
            logger.info(f"[Collect] RSS 抓取完成: {len(rss_articles)} 篇")
        except Exception as e:
            msg = f"RSS 抓取阶段失败: {e}"
            logger.error(f"[Collect] {msg}")
            errors.append(msg)

        # 网页爬取
        if self.web_crawler and self.crawl_sites:
            try:
                web_articles, web_errors = self.web_crawler.crawl_all(self.crawl_sites)
                articles.extend(web_articles)
                if web_errors:
                    errors.extend(web_errors)
                logger.info(f"[Collect] 网页爬取完成: {len(web_articles)} 篇")
            except Exception as e:
                msg = f"网页爬取阶段总控失败: {e}"
                logger.error(f"[Collect] {msg}")
                errors.append(msg)

        return articles, errors

    def run(self) -> dict:
        """
        执行完整 Pipeline：
        1. 抓取新闻（RSS + 网页爬取）
        2. HTML → Markdown 转换 + 元数据提取
        3. 存储到数据库（content 为 Markdown 格式）
        4. 可选：保存 Markdown 文件到磁盘
        5. AI 摘要 + 打标签（新增）
        6. 获取已摘要未向量化文章
        7. 分块：按 Markdown 章节切分为父子 chunks
        8. 生成子 chunk Embedding
        9. 子 chunk 向量 + 父 chunk 写入 PostgreSQL
        10. 标记为已向量化

        每步独立 try/except，失败记日志但不终止后续步骤。
        返回 {"fetched": int, "new": int, "summarized": int, "summary_failed": int,
               "chunks": int, "parent_chunks": int, "embedded": int, "errors": list[str]}
        """
        result = {
            "fetched": 0, "new": 0, "summarized": 0, "summary_failed": 0,
            "chunks": 0, "parent_chunks": 0, "embedded": 0, "errors": [],
        }

        # Step 1: 抓取（RSS + 网页爬取）
        articles, collect_errors = self._collect_all()
        result["fetched"] = len(articles)
        result["errors"].extend(collect_errors)

        # Step 2: Markdown 转换
        if articles:
            try:
                articles = self.md_converter.convert_batch(articles)
                logger.info(f"[Pipeline] Markdown 转换完成: {len(articles)} 篇")
            except Exception as e:
                msg = f"Markdown 转换阶段失败: {e}"
                logger.error(f"[Pipeline] {msg}")
                result["errors"].append(msg)

        # Step 3: 存储
        if articles:
            try:
                new_count = self.article_store.save_articles(articles)
                result["new"] = new_count
                logger.info(f"[Pipeline] 存储完成: {new_count} 篇新文章")
            except Exception as e:
                msg = f"存储阶段失败: {e}"
                logger.error(f"[Pipeline] {msg}")
                result["errors"].append(msg)

        # Step 4: 可选 — 保存 Markdown 文件到磁盘
        if articles and self.markdown_output_path:
            try:
                paths = self.md_converter.save_batch_as_files(
                    articles, self.markdown_output_path
                )
                logger.info(
                    f"[Pipeline] Markdown 文件保存: {len(paths)} 篇"
                )
            except Exception as e:
                msg = f"Markdown 文件保存失败: {e}"
                logger.error(f"[Pipeline] {msg}")
                result["errors"].append(msg)

        # Step 5: AI 摘要 + 打标签
        # 临时跳过AI摘要
        if False and self.summary_service:
            try:
                summary_result = self.summary_service.summarize_pending()
                result["summarized"] = summary_result.get("success", 0)
                result["summary_failed"] = summary_result.get("failed", 0)
                logger.info(
                    f"[Pipeline] AI 摘要完成: 成功 {result['summarized']}，"
                    f"失败 {result['summary_failed']}"
                )
            except Exception as e:
                msg = f"AI 摘要阶段失败: {e}"
                logger.error(f"[Pipeline] {msg}")
                result["errors"].append(msg)
        else:
            # 无摘要服务时，直接将 pending_summary 标记为 summarized
            try:
                pending = self.article_store.get_pending_summary()
                if pending:
                    ids = [a.id for a in pending if a.id is not None]
                    self.article_store.mark_summarized(ids)
                    logger.info(f"[Pipeline] 无摘要服务，直接标记 {len(ids)} 篇为 summarized")
            except Exception as e:
                msg = f"标记 summarized 失败: {e}"
                logger.error(f"[Pipeline] {msg}")
                result["errors"].append(msg)

        # Step 6~10: 分块 + 向量化
        try:
            pending = self.article_store.get_unembedded()
            if pending:
                logger.info(f"[Pipeline] 待向量化: {len(pending)} 篇")

                if self.chunking_service:
                    # 新版：分块 → 向量化
                    embedded_count = self._embed_with_chunks(pending, result)
                else:
                    # 回退：无分块服务时整篇向量化（兼容）
                    logger.warning("[Pipeline] 未配置分块服务，跳过向量化")
                    embedded_count = 0

                self.article_store.mark_embedded(
                    [a.id for a in pending if a.id is not None]
                )
                result["embedded"] = embedded_count
                logger.info(f"[Pipeline] 向量化完成: {embedded_count} 个子 chunks")
            else:
                logger.info("[Pipeline] 无待向量化文章")
        except Exception as e:
            msg = f"向量化阶段失败: {e}"
            logger.error(f"[Pipeline] {msg}")
            result["errors"].append(msg)

        logger.info(f"[Pipeline] 完成: {result}")
        return result

    def _embed_with_chunks(self, articles: list, result: dict) -> int:
        """分块 → Embedding → 写入 PostgreSQL。

        Args:
            articles: 待向量化的文章列表。
            result: Pipeline 结果字典（用于回填 chunks/parent_chunks 计数）。

        Returns:
            写入的子 chunk 数量。
        """
        # 1. 分块
        all_children, all_parents = self.chunking_service.chunk_articles(articles)
        result["chunks"] = len(all_children)
        result["parent_chunks"] = len(all_parents)

        if not all_children:
            logger.warning("[Pipeline] 分块后无子 chunks")
            return 0

        # 2. 生成子 chunk embedding
        child_texts = [c.content for c in all_children]
        embeddings = self.embedding_client.embed(child_texts)

        # 3. 子 chunk 向量写入 PostgreSQL/pgvector
        embedded_count = self.vector_store.add_chunks(all_children, embeddings)

        # 4. 父 chunk 写入 PostgreSQL
        if all_parents:
            self.article_store.save_parent_chunks(all_parents)

        return embedded_count

    def fetch_and_store(self) -> dict:
        """
        仅执行抓取 → Markdown转换 → 存储，不进行 AI 向量化分析。
        用于系统启动时快速拉取最新新闻。
        返回 {"fetched": int, "new": int, "errors": list[str]}
        """
        result = {"fetched": 0, "new": 0, "errors": []}

        articles, collect_errors = self._collect_all()
        result["fetched"] = len(articles)
        result["errors"].extend(collect_errors)

        if not articles:
            return result

        # Markdown 转换
        try:
            articles = self.md_converter.convert_batch(articles)
            logger.info(f"[FetchOnly] Markdown 转换完成: {len(articles)} 篇")
        except Exception as e:
            msg = f"Markdown 转换阶段失败: {e}"
            logger.error(f"[FetchOnly] {msg}")
            result["errors"].append(msg)

        # 存储
        try:
            new_count = self.article_store.save_articles(articles)
            result["new"] = new_count
            logger.info(f"[FetchOnly] 存储完成: {new_count} 篇新文章")
        except Exception as e:
            msg = f"存储阶段失败: {e}"
            logger.error(f"[FetchOnly] {msg}")
            result["errors"].append(msg)

        # 可选：保存 Markdown 文件
        if self.markdown_output_path:
            try:
                paths = self.md_converter.save_batch_as_files(
                    articles, self.markdown_output_path
                )
                logger.info(
                    f"[FetchOnly] Markdown 文件保存: {len(paths)} 篇"
                )
            except Exception as e:
                msg = f"Markdown 文件保存失败: {e}"
                logger.error(f"[FetchOnly] {msg}")
                result["errors"].append(msg)

        return result
