"""Intelligence ingestion pipeline.

RSS/web collection -> Markdown -> SourceDocument -> parent/child chunks ->
Qdrant vectorization -> structured intel facts -> fact links.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

import structlog

from core.protocols import (
    DocumentStoreProtocol,
    EmbeddingClientProtocol,
    RedisStateStoreProtocol,
    VectorIndexProtocol,
)
from models.document_governance import DedupDecision
from infrastructure.collector import NewsCollector
from infrastructure.markdown_converter import NewsMarkdownConverter
from services.document_fingerprint_service import fingerprint

if TYPE_CHECKING:
    from infrastructure.chunking_service import ChunkingService
    from infrastructure.web_crawler import WebCrawler
    from models.document import SourceDocument
    from services.document_clustering_service import DocumentClusteringService
    from services.task_run_reporter import TaskRunReporter

logger = structlog.get_logger(__name__)


class PipelineService:
    """Run the Phase 2 ingestion and structured fact extraction flow."""

    def __init__(
        self,
        collector: NewsCollector,
        document_store: DocumentStoreProtocol,
        vector_index: VectorIndexProtocol,
        embedding_client: EmbeddingClientProtocol,
        chunking_service: "ChunkingService | None" = None,
        web_crawler: "WebCrawler | None" = None,
        crawl_sites: list[dict] | None = None,
        markdown_converter: NewsMarkdownConverter | None = None,
        markdown_output_path: str | None = None,
        intel_service: Any | None = None,
        competitor_service: Any | None = None,
        task_reporter: "TaskRunReporter | None" = None,
        redis_state_store: RedisStateStoreProtocol | None = None,
        source_governance_service: Any | None = None,
        document_clustering_service: "DocumentClusteringService | None" = None,
        source_governance_enabled: bool = False,
    ):
        self.collector = collector
        self.document_store = document_store
        self.vector_index = vector_index
        self.embedding_client = embedding_client
        self.chunking_service = chunking_service
        self.web_crawler = web_crawler
        self.crawl_sites = crawl_sites or []
        self.md_converter = markdown_converter or NewsMarkdownConverter()
        self.markdown_output_path = markdown_output_path
        self.intel_service = intel_service
        self.competitor_service = competitor_service
        self.task_reporter = task_reporter
        self.redis_state_store = redis_state_store
        self.source_governance_service = source_governance_service
        self.document_clustering_service = document_clustering_service
        self.source_governance_enabled = source_governance_enabled

    def run(self) -> dict:
        result = {
            "fetched": 0,
            "new": 0,
            "documents": 0,
            "chunks": 0,
            "parent_chunks": 0,
            "embedded": 0,
            "facts_created": 0,
            "facts_updated": 0,
            "facts_skipped": 0,
            "fact_extract_failed": 0,
            "intel_linked": 0,
            "skipped_non_articles": 0,
            "errors": [],
            "quarantined": 0,
            "pending_review": 0,
            "duplicates": 0,
            "duplicate_candidates": 0,
        }

        stage = self._start_stage("collect")
        articles, collect_errors = self._collect_all()
        result["fetched"] = len(articles)
        result["errors"].extend(collect_errors)
        self._finish_stage(
            stage,
            "succeeded" if not collect_errors else "failed",
            {"fetched": len(articles), "errors": collect_errors},
        )

        if articles:
            stage = self._start_stage("markdown", {"articles": len(articles)})
            try:
                articles = self.md_converter.convert_batch(articles)
                articles, skipped = self._filter_indexable_articles(articles)
                articles = self._apply_source_admission(articles, result)
                result["skipped_non_articles"] += skipped
                self._finish_stage(
                    stage,
                    "succeeded",
                    {"articles": len(articles), "skipped_non_articles": skipped},
                )
            except Exception as exc:
                msg = f"Markdown 转换阶段失败: {exc}"
                logger.error("[Pipeline] %s", msg)
                result["errors"].append(msg)
                self._finish_stage(stage, "failed", error={"message": msg})
                articles = []

        documents: list[SourceDocument] = []
        if articles:
            stage = self._start_stage("store_source_documents", {"articles": len(articles)})
            try:
                documents = self._prepare_documents(articles, result)
                for document in documents:
                    self.document_store.save_document(document)
                result["new"] = len(documents)
                result["documents"] = len(documents)
                self._finish_stage(
                    stage,
                    "succeeded",
                    {"documents": len(documents), "new": result["new"]},
                )
            except Exception as exc:
                msg = f"SourceDocument 入库阶段失败: {exc}"
                logger.error("[Pipeline] %s", msg)
                result["errors"].append(msg)
                self._finish_stage(stage, "failed", error={"message": msg})
                documents = []

        vectorized_document_ids: list[str] = []
        stage = self._start_stage("chunk_and_vectorize", {"documents": len(documents)})
        try:
            if documents and self.chunking_service:
                embedded_count = self._embed_documents(documents, result)
                result["embedded"] = embedded_count
                vectorized_document_ids = result.pop("_vectorized_document_ids", [])
            elif documents:
                msg = "未配置分块服务，跳过向量化"
                logger.warning("[Pipeline] %s", msg)
                result["errors"].append(msg)
            self._finish_stage(
                stage,
                "succeeded",
                {
                    "chunks": result["chunks"],
                    "parent_chunks": result["parent_chunks"],
                    "embedded": result["embedded"],
                    "documents": len(vectorized_document_ids),
                },
            )
        except Exception as exc:
            msg = f"分块向量化阶段失败: {exc}"
            logger.error("[Pipeline] %s", msg)
            result["errors"].append(msg)
            self._finish_stage(stage, "failed", error={"message": msg})

        stage = self._start_stage(
            "extract_intel_facts", {"documents": len(vectorized_document_ids)}
        )
        extract_result = self._extract_intel_facts(vectorized_document_ids, result)
        self._finish_stage(
            stage,
            "succeeded" if extract_result["failed"] == 0 else "failed",
            extract_result,
            error=None if extract_result["failed"] == 0 else {"failed": extract_result["failed"]},
        )

        stage = self._start_stage("link_facts", {"documents": len(vectorized_document_ids)})
        try:
            if self.competitor_service and vectorized_document_ids:
                link_result = self.competitor_service.auto_link_facts(
                    document_ids=vectorized_document_ids
                )
                result["intel_linked"] = link_result.get("linked", 0)
            else:
                link_result = {
                    "linked": 0,
                    "facts_processed": 0,
                    "reason": "missing_service_or_documents",
                }
            self._finish_stage(stage, "succeeded", link_result)
        except Exception as exc:
            msg = f"fact 竞品关联失败: {exc}"
            logger.error("[Pipeline] %s", msg)
            result["errors"].append(msg)
            self._finish_stage(stage, "failed", error={"message": msg})

        logger.info("[Pipeline] 完成: %s", result)
        return result

    def _collect_all(self) -> tuple[list, list[str]]:
        articles = []
        errors = []
        try:
            rss_articles = self.collector.fetch_all()
            articles.extend(rss_articles)
            logger.info("[Collect] RSS 抓取完成: %s 篇", len(rss_articles))
        except Exception as exc:
            msg = f"RSS 抓取阶段失败: {exc}"
            logger.error("[Collect] %s", msg)
            errors.append(msg)

        if self.web_crawler and self.crawl_sites:
            try:
                web_articles, web_errors = self.web_crawler.crawl_all(self.crawl_sites)
                articles.extend(web_articles)
                errors.extend(web_errors or [])
                logger.info("[Collect] 网页爬取完成: %s 篇", len(web_articles))
            except Exception as exc:
                msg = f"网页爬取阶段总控失败: {exc}"
                logger.error("[Collect] %s", msg)
                errors.append(msg)
        return articles, errors

    def _embed_documents(self, documents: list["SourceDocument"], result: dict) -> int:
        lock_owner = str(
            uuid5(
                NAMESPACE_URL,
                "pipeline-vectorize:" + ",".join(d.document_id for d in documents),
            )
        )
        lock_keys: list[str] = []
        redis_healthy = bool(
            self.redis_state_store and self.redis_state_store.healthcheck()
        )
        try:
            if redis_healthy and self.redis_state_store:
                for document in documents:
                    lock_key = f"logos:lock:vectorize:{document.document_id}"
                    if not self.redis_state_store.acquire_lock(
                        lock_key,
                        lock_owner,
                        ttl_seconds=3600,
                    ):
                        raise RuntimeError(f"文档正在向量化: {document.document_id}")
                    lock_keys.append(lock_key)

            all_children, all_parents = self.chunking_service.chunk_documents(documents)
            self._event(
                "chunk",
                {
                    "documents": len(documents),
                    "children": len(all_children),
                    "parents": len(all_parents),
                },
            )
            result["chunks"] = len(all_children)
            result["parent_chunks"] = len(all_parents)

            if not all_children:
                logger.warning("[Pipeline] 分块后无子 chunks")
                return 0

            if all_parents:
                saved_parents = self.document_store.save_parent_chunks(all_parents)
                if isinstance(saved_parents, int) and saved_parents < len(all_parents):
                    raise RuntimeError(
                        f"父 chunk 写入不完整: {saved_parents}/{len(all_parents)}"
                    )

            embeddings = self.embedding_client.embed([child.content for child in all_children])
            self._event(
                "embed",
                {"children": len(all_children), "embeddings": len(embeddings)},
            )
            if len(embeddings) != len(all_children):
                raise RuntimeError(
                    f"Embedding 数量不匹配: {len(embeddings)}/{len(all_children)}"
                )

            embedded_count = self.vector_index.upsert_child_chunks(all_children, embeddings)
            self._event("qdrant_upsert", {"points": embedded_count})
            if embedded_count != len(all_children):
                raise RuntimeError(
                    f"子 chunk 写入不完整: {embedded_count}/{len(all_children)}"
                )
            self.document_store.mark_points_vectorized(all_children)
            self._event("mark_vectorized", {"points": len(all_children)})

            document_ids = sorted({document.document_id for document in documents})
            for document_id in document_ids:
                self.document_store.update_parse_status(document_id, "vectorized")
            result["_vectorized_document_ids"] = document_ids
            return embedded_count
        except Exception as exc:
            if "all_children" in locals() and all_children:
                self.document_store.mark_points_vector_failed(
                    [child.point_id for child in all_children],
                    {"message": str(exc)},
                )
            for document in documents:
                try:
                    self.document_store.update_parse_status(
                        document.document_id,
                        "failed",
                        {"message": str(exc)},
                    )
                except Exception:
                    logger.exception("document status update failed")
            raise
        finally:
            if self.redis_state_store:
                for lock_key in lock_keys:
                    self.redis_state_store.release_lock(lock_key, lock_owner)

    def _extract_intel_facts(self, document_ids: list[str], result: dict) -> dict:
        if not document_ids:
            return {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
        if not self.intel_service:
            return {
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "failed": len(document_ids),
                "reason": "intel_service_missing",
            }
        created = updated = skipped = failed = 0
        for document_id in document_ids:
            try:
                item = self.intel_service.extract_facts_from_document(document_id)
                created += item.get("created", 0)
                updated += item.get("updated", 0)
                skipped += item.get("skipped", 0)
            except Exception as exc:
                failed += 1
                msg = f"事实抽取失败({document_id}): {exc}"
                logger.error("[Pipeline] %s", msg)
                result["errors"].append(msg)
        result["facts_created"] = created
        result["facts_updated"] = updated
        result["facts_skipped"] = skipped
        result["fact_extract_failed"] = failed
        return {"created": created, "updated": updated, "skipped": skipped, "failed": failed}

    def _prepare_documents(self, articles: list, result: dict) -> list["SourceDocument"]:
        if not self.document_clustering_service:
            raise RuntimeError("DocumentClusteringService 未配置，禁止回退到 URL 文档身份")

        documents = []
        for article in articles:
            occurrence = self._article_to_occurrence(article)
            # 只有 PostgreSQL 已提交的权威结果可以决定是否启动昂贵的派生数据构建。
            committed = self.document_clustering_service.commit(occurrence)
            if committed.requires_build or committed.decision is DedupDecision.NEW_CLUSTER:
                documents.append(
                    self._article_to_document(
                        article,
                        document_id=committed.occurrence.document_id,
                    )
                )
            elif committed.decision in {DedupDecision.DUPLICATE, DedupDecision.UNCHANGED}:
                result["duplicates"] += 1
            elif committed.decision is DedupDecision.REVIEW_REQUIRED:
                result["duplicate_candidates"] += 1
            elif committed.decision is DedupDecision.QUARANTINED:
                result["quarantined"] += 1
            elif committed.decision is DedupDecision.CANONICAL_PROMOTED:
                raise RuntimeError("canonical_promoted 必须交由 DocumentVersionService 构建")
            else:
                raise ValueError(f"未支持的去重决定: {committed.decision}")
        return documents

    def _article_to_occurrence(self, article):
        from models.document_governance import SourceOccurrence

        content_hash, simhash, _ = fingerprint(article.content or "")
        admission = getattr(article, "_source_admission", None)
        profile = admission.profile if admission else None
        return SourceOccurrence(
            document_id="",
            url=article.url or "",
            normalized_url=self._normalize_url(article.url or ""),
            title=article.title or "Untitled",
            content_hash=content_hash,
            simhash=simhash,
            source_profile_revision_id=getattr(profile, "revision_id", None),
            source_tier=getattr(getattr(profile, "tier", None), "value", "unknown"),
            source_kind=getattr(getattr(profile, "source_kind", None), "value", "other"),
        )

    @staticmethod
    def _normalize_url(url: str) -> str:
        parts = urlsplit(url.strip())
        query = urlencode(
            sorted(
                (key, value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
                if not key.lower().startswith("utm_")
            )
        )
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))

    @staticmethod
    def _article_to_document(article, document_id: str):
        from models.document import SourceDocument

        content = article.content or ""
        return SourceDocument(
            document_id=document_id,
            title=article.title or "Untitled",
            content=content,
            source_type="rss" if article.source else "web",
            document_type="article",
            url=article.url or "",
            canonical_url=article.url or "",
            language=getattr(article.language, "value", article.language) or "",
            content_hash=fingerprint(content)[0],
            metadata={
                "source": article.source or "",
                "author": article.author or "",
                "tags": article.tags or [],
                "semantic_blocks": getattr(article, "semantic_blocks", None),
                "semantic_skip_indexing": getattr(
                    article, "semantic_skip_indexing", False
                ),
            },
            published_at=article.published_at,
            parse_status="parsed",
        )

    def _apply_source_admission(self, articles: list, result: dict) -> list:
        if not self.source_governance_enabled:
            return articles
        if not self.source_governance_service:
            raise RuntimeError("已启用来源治理，但 SourceGovernanceService 未配置")
        admitted = []
        for article in articles:
            outcome = self.source_governance_service.admit(article.url or "")
            if outcome.decision == "admit":
                # 准入时快照随 occurrence 固化，后续来源重新评级不能改写历史。
                article._source_admission = outcome
                admitted.append(article)
            elif outcome.decision == "quarantine":
                result["quarantined"] += 1
            else:
                result["pending_review"] += 1
        return admitted

    @staticmethod
    def _filter_indexable_articles(articles: list) -> tuple[list, int]:
        indexable = [
            article
            for article in articles
            if not getattr(article, "semantic_skip_indexing", False)
        ]
        skipped = len(articles) - len(indexable)
        if skipped:
            logger.info("[Pipeline] 跳过 %s 篇非文章/低质量页面", skipped)
        return indexable, skipped

    def _start_stage(self, name: str, payload: dict | None = None):
        return self.task_reporter.start_stage(name, payload) if self.task_reporter else None

    def _finish_stage(
        self,
        stage,
        status: str,
        result: dict | None = None,
        error: dict | None = None,
    ) -> None:
        if self.task_reporter:
            self.task_reporter.finish_stage(stage, status, result=result, error=error)

    def _event(self, event_type: str, payload: dict | None = None) -> None:
        if self.task_reporter:
            self.task_reporter.event(event_type, payload)

    def fetch_and_store(self) -> dict:
        result = {
            "fetched": 0,
            "new": 0,
            "skipped_non_articles": 0,
            "quarantined": 0,
            "pending_review": 0,
            "duplicates": 0,
            "duplicate_candidates": 0,
            "errors": [],
        }
        articles, collect_errors = self._collect_all()
        result["fetched"] = len(articles)
        result["errors"].extend(collect_errors)
        if not articles:
            return result
        try:
            articles = self.md_converter.convert_batch(articles)
            articles, skipped = self._filter_indexable_articles(articles)
            articles = self._apply_source_admission(articles, result)
            result["skipped_non_articles"] += skipped
        except Exception as exc:
            msg = f"Markdown 转换阶段失败: {exc}"
            logger.error("[FetchOnly] %s", msg)
            result["errors"].append(msg)
        try:
            documents = self._prepare_documents(articles, result)
            for document in documents:
                self.document_store.save_document(document)
            result["new"] = len(documents)
        except Exception as exc:
            msg = f"存储阶段失败: {exc}"
            logger.error("[FetchOnly] %s", msg)
            result["errors"].append(msg)
        if self.markdown_output_path:
            try:
                self.md_converter.save_batch_as_files(articles, self.markdown_output_path)
            except Exception as exc:
                msg = f"Markdown 文件保存失败: {exc}"
                logger.error("[FetchOnly] %s", msg)
                result["errors"].append(msg)
        return result
