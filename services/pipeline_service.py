"""编排 抓取 → 存储 → 向量化 的完整流水线"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.protocols import (
    ArticleStoreProtocol,
    VectorStoreProtocol,
    EmbeddingClientProtocol,
)
from infrastructure.collector import NewsCollector

if TYPE_CHECKING:
    from infrastructure.web_crawler import WebCrawler

logger = logging.getLogger(__name__)


class PipelineService:
    """编排 抓取 → 存储 → 向量化 的完整流水线"""

    def __init__(
        self,
        collector: NewsCollector,
        article_store: ArticleStoreProtocol,
        vector_store: VectorStoreProtocol,
        embedding_client: EmbeddingClientProtocol,
        web_crawler: WebCrawler | None = None,
        crawl_sites: list[dict] | None = None,
    ):
        self.collector = collector
        self.article_store = article_store
        self.vector_store = vector_store
        self.embedding_client = embedding_client
        self.web_crawler = web_crawler
        self.crawl_sites = crawl_sites or []

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
                web_articles = self.web_crawler.crawl_all(self.crawl_sites)
                articles.extend(web_articles)
                logger.info(f"[Collect] 网页爬取完成: {len(web_articles)} 篇")
            except Exception as e:
                msg = f"网页爬取阶段失败: {e}"
                logger.error(f"[Collect] {msg}")
                errors.append(msg)

        return articles, errors

    def run(self) -> dict:
        """
        执行完整 Pipeline：
        1. 抓取新闻（RSS + 网页爬取）
        2. 存储到数据库
        3. 获取未向量化文章
        4. 生成 Embedding
        5. 写入向量库
        6. 标记为已向量化

        每步独立 try/except，失败记日志但不终止后续步骤。
        返回 {"fetched": int, "new": int, "embedded": int, "errors": list[str]}
        """
        result = {"fetched": 0, "new": 0, "embedded": 0, "errors": []}

        # Step 1: 抓取（RSS + 网页爬取）
        articles, collect_errors = self._collect_all()
        result["fetched"] = len(articles)
        result["errors"].extend(collect_errors)

        # Step 2: 存储
        if articles:
            try:
                new_count = self.article_store.save_articles(articles)
                result["new"] = new_count
                logger.info(f"[Pipeline] 存储完成: {new_count} 篇新文章")
            except Exception as e:
                msg = f"存储阶段失败: {e}"
                logger.error(f"[Pipeline] {msg}")
                result["errors"].append(msg)

        # Step 3~6: 向量化
        try:
            pending = self.article_store.get_unembedded()
            if pending:
                logger.info(f"[Pipeline] 待向量化: {len(pending)} 篇")
                texts = [a.to_embedding_text() for a in pending]
                embeddings = self.embedding_client.embed(texts)
                embedded_count = self.vector_store.add_articles(
                    pending, embeddings
                )
                self.article_store.mark_embedded(
                    [a.id for a in pending if a.id is not None]
                )
                result["embedded"] = embedded_count
                logger.info(f"[Pipeline] 向量化完成: {embedded_count} 篇")
            else:
                logger.info("[Pipeline] 无待向量化文章")
        except Exception as e:
            msg = f"向量化阶段失败: {e}"
            logger.error(f"[Pipeline] {msg}")
            result["errors"].append(msg)

        logger.info(f"[Pipeline] 完成: {result}")
        return result

    def fetch_and_store(self) -> dict:
        """
        仅执行抓取与存储（RSS + 网页爬取），不进行 AI 向量化分析。
        用于系统启动时快速拉取最新新闻。
        返回 {"fetched": int, "new": int, "errors": list[str]}
        """
        result = {"fetched": 0, "new": 0, "errors": []}

        articles, collect_errors = self._collect_all()
        result["fetched"] = len(articles)
        result["errors"].extend(collect_errors)

        if not articles:
            return result

        try:
            new_count = self.article_store.save_articles(articles)
            result["new"] = new_count
            logger.info(f"[FetchOnly] 存储完成: {new_count} 篇新文章")
        except Exception as e:
            msg = f"存储阶段失败: {e}"
            logger.error(f"[FetchOnly] {msg}")
            result["errors"].append(msg)

        return result
