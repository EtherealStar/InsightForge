import structlog
import asyncio
from datetime import datetime
from uuid import uuid4
from celery import shared_task

from core.config_manager import get_config_manager
from core.factory import (
    create_browser_fetch_engine,
    create_collection_run_store,
    create_document_clustering_service,
    create_document_ingestion_service,
    create_source_governance_service,
    create_document_version_service,
    create_dedup_maintenance_service,
    create_fetch_artifact_store,
    create_fetch_blob_store,
    create_fetch_candidate_store,
    create_http_fetch_engine,
    create_normalization_service,
    create_normalized_document_store,
)
from core.source_config import load_feeds, load_sites
from infrastructure.collector import NewsCollector
from models.task_run import TaskStatus
from services.pipeline_service import PipelineService
from services.task_run_reporter import TaskRunReporter

logger = structlog.get_logger(__name__)


def _collection_execution_service(config):
    from services.collection_execution_service import CollectionExecutionService
    return CollectionExecutionService(
        create_fetch_candidate_store(config),
        create_fetch_artifact_store(config),
        create_fetch_blob_store(config),
        create_normalized_document_store(config),
        create_normalization_service(config),
    )


@shared_task
def start_collection_run_task():
    """按来源建任务；每条后续 Celery 消息只传数据库 ID。"""
    from services.collection_orchestrator import CollectionOrchestrator
    mgr = get_config_manager()
    profiles = mgr.source_profile_store.list_profiles() if mgr.source_profile_store else []
    store = create_collection_run_store(mgr.config)
    orchestrator = CollectionOrchestrator(store, lambda task_id: discover_source_task.delay(task_id))
    run = orchestrator.create_run([profile.id for profile in profiles])
    return {"collection_run_id": run.id, "source_tasks": len(profiles)}


@shared_task
def discover_source_task(source_task_id: str):
    """按 Source Profile 配置发现候选，不把正文放进 Celery 消息。"""
    mgr = get_config_manager()
    config = mgr.config
    store = create_collection_run_store(config)
    task = store.claim_task(source_task_id)
    profile = mgr.source_profile_store.get_profile(task.source_profile_id) if mgr.source_profile_store else None
    if profile is None or not profile.collection_config.get("connector"):
        store.advance_task(source_task_id, "paused", {"reason": "connector_not_configured"})
        return {"source_task_id": source_task_id, "status": "paused"}
    try:
        candidates = asyncio.run(_discover_candidates(profile, config))
        candidate_store = create_fetch_candidate_store(config)
        for candidate in candidates:
            saved = candidate_store.save_candidate(source_task_id, candidate)
            queue = fetch_browser_candidate_task if profile.collection_config.get("render_required") else fetch_http_candidate_task
            queue.delay(saved.id, source_task_id)
        store.advance_task(source_task_id, "succeeded")
        return {"source_task_id": source_task_id, "status": "succeeded", "candidates": len(candidates)}
    except Exception as exc:
        store.advance_task(source_task_id, "failed", {"message": str(exc)})
        raise


async def _discover_candidates(profile, config):
    from infrastructure.connectors import ApiConnector, ListingConnector, RssConnector, SearchConnector, SitemapConnector
    from models.collection import FetchCandidate, SourceFetchPolicy
    settings = profile.collection_config
    connector_name = settings["connector"]
    observed_at = datetime.now().astimezone()
    if connector_name == "search":
        connector = SearchConnector(settings.get("results", []), observed_at=observed_at)
    else:
        endpoint = settings.get("endpoint")
        if not endpoint:
            raise ValueError("collection_config.endpoint 不能为空")
        discovery_candidate = FetchCandidate(profile.id, endpoint, observed_at, settings.get("cursor", "discovery"))
        response = await create_http_fetch_engine(config).fetch(discovery_candidate, SourceFetchPolicy())
        if response.body is None or response.status.value != "fetched":
            raise RuntimeError(f"发现入口获取失败: {response.reason_code or response.status.value}")
        if connector_name == "rss":
            connector = RssConnector(response.body, observed_at=observed_at)
        elif connector_name == "sitemap":
            connector = SitemapConnector(response.body, observed_at=observed_at)
        elif connector_name == "listing":
            connector = ListingConnector(response.body.decode("utf-8", errors="replace"), observed_at=observed_at)
        elif connector_name == "api":
            connector = ApiConnector(
                response.body.decode("utf-8"), items_field=settings.get("items_field", "items"),
                url_field=settings.get("url_field", "url"), cursor_field=settings.get("cursor_field", "next"),
                observed_at=observed_at,
            )
        else:
            raise ValueError(f"不支持的 connector: {connector_name}")
    return connector.discover(profile, None).candidates


@shared_task
def fetch_http_candidate_task(candidate_id: str, source_task_id: str):
    from models.collection import SourceFetchPolicy
    config = get_config_manager().config
    artifact = asyncio.run(_collection_execution_service(config).fetch_candidate(
        candidate_id, source_task_id, create_http_fetch_engine(config), SourceFetchPolicy()
    ))
    if artifact.status.value == "fetched":
        normalize_artifact_task.delay(artifact.id)
    return {"artifact_id": artifact.id, "status": artifact.status.value}


@shared_task
def fetch_browser_candidate_task(candidate_id: str, source_task_id: str):
    from models.collection import SourceFetchPolicy
    config = get_config_manager().config
    artifact = asyncio.run(_collection_execution_service(config).fetch_candidate(
        candidate_id, source_task_id, create_browser_fetch_engine(config), SourceFetchPolicy(render_required=True)
    ))
    if artifact.status.value == "fetched":
        normalize_artifact_task.delay(artifact.id)
    return {"artifact_id": artifact.id, "status": artifact.status.value}


@shared_task
def normalize_artifact_task(artifact_id: str):
    from models.collection import NormalizerRules
    mgr = get_config_manager()
    config = mgr.config
    artifact_store = create_fetch_artifact_store(config)
    # artifact ID 是消息中唯一业务载荷，正文始终从 Blob Store 回放。
    artifact = artifact_store.get_artifact(artifact_id)
    if artifact is None:
        raise KeyError(f"artifact 查询尚未找到: {artifact_id}")
    document = _collection_execution_service(config).normalize_artifact(artifact, NormalizerRules("v1"))
    candidate = create_fetch_candidate_store(config).get_candidate(artifact.candidate_id)
    profile = mgr.source_profile_store.get_profile(candidate.source_profile_id) if candidate and mgr.source_profile_store else None
    if document.outcome.value == "retry_render" and artifact.fetch_method.value == "http":
        fetch_browser_candidate_task.delay(artifact.candidate_id, artifact.source_task_id)
    elif _collection_execution_service(config).should_ingest(document, profile):
        ingest_normalized_document_task.delay(document.id)
    return {"normalized_document_id": document.id, "outcome": document.outcome.value}


@shared_task
def ingest_normalized_document_task(normalized_document_id: str):
    return {"normalized_document_id": normalized_document_id, "status": "accepted_for_ingest"}


@shared_task
def enrich_normalized_document_task(normalized_document_id: str):
    return {"normalized_document_id": normalized_document_id, "status": "queued_for_enrich"}


@shared_task
def ocr_artifact_task(artifact_id: str):
    return {"artifact_id": artifact_id, "status": "ocr_not_required"}


@shared_task
def rebuild_dedup_cache_task(batch_size=1000):
    """从 PostgreSQL 权威 occurrence 全量重建 Redis 热点索引。"""
    config = get_config_manager().config
    result = create_dedup_maintenance_service(config).rebuild_cache(batch_size=batch_size)
    logger.info("dedup_cache.rebuilt", **result)
    return result

@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def run_pipeline_task(self, manual=False, task_run_id=None):
    """
    执行情报采集 → SourceDocument 入库 → 分块向量化 → 事实抽取与关联。
    被 Beat 高频调用（每 5 分钟），内部通过 Redis 检查距离上次运行是否超过设定间隔。
    也可通过异步 API 直接触发（直接触发时将绕过频率检查，或至少会执行）。
    为了支持手动强制触发，我们通过 task 的 kwargs 判断。这里如果是由 beat 触发，会进行拦截；手动触发强制执行。
    """
    mgr = get_config_manager()
    mgr.reload()
    config = mgr.config

    reporter = TaskRunReporter(
        mgr.task_run_store,
        mgr.redis_state_store,
        run_id=task_run_id,
    )
    if task_run_id:
        reporter.start_run(task_run_id)
    else:
        run = reporter.create_run(
            "pipeline",
            {"manual": manual, "celery_task_id": self.request.id},
            idempotency_key=f"pipeline:{self.request.id}",
        )
        if run:
            reporter.start_run(run.id)

    redis_healthy = bool(mgr.redis_state_store and mgr.redis_state_store.healthcheck())
    lock_key = "logos:lock:pipeline"
    lock_owner = str(uuid4())
    lock_acquired = False
    try:
        if redis_healthy and mgr.redis_state_store:
            lock_acquired = mgr.redis_state_store.acquire_lock(
                lock_key,
                lock_owner,
                ttl_seconds=7200,
            )
            if not lock_acquired:
                result = {"status": "skipped", "reason": "pipeline_locked"}
                reporter.finish_run(TaskStatus.SKIPPED.value, result)
                logger.info("Pipeline skipped because lock is held")
                return result

        last_run_value = (
            mgr.redis_state_store.get_json("logos:last_pipeline_run")
            if redis_healthy and mgr.redis_state_store
            else None
        )
        last_run_str = None
        if isinstance(last_run_value, dict):
            last_run_str = last_run_value.get("at")
        elif isinstance(last_run_value, str):
            last_run_str = last_run_value

        if not manual and last_run_str:
            last_run = datetime.fromisoformat(last_run_str)
            elapsed_hours = (datetime.now() - last_run).total_seconds() / 3600.0
            if elapsed_hours < config.fetch_interval_hours:
                result = {
                    "status": "skipped",
                    "reason": "fetch_interval",
                    "elapsed_hours": elapsed_hours,
                    "fetch_interval_hours": config.fetch_interval_hours,
                }
                reporter.event("pipeline_skipped", result)
                reporter.finish_run(TaskStatus.SKIPPED.value, result)
                logger.info(
                    "Pipeline skipped",
                    elapsed_hours=elapsed_hours,
                    fetch_interval_hours=config.fetch_interval_hours,
                )
                return result

        logger.info("=== Pipeline 开始 ===")

        config.rss_feeds = load_feeds()
        collector = NewsCollector(config)

        crawl_sites = load_sites()
        web_crawler = None
        if crawl_sites:
            from infrastructure.web_crawler import WebCrawler
            web_crawler = WebCrawler()

        service = PipelineService(
            collector,
            mgr.document_store,
            mgr.vector_index,
            mgr.embedding_client,
            chunking_service=mgr.chunking_service,
            web_crawler=web_crawler,
            crawl_sites=crawl_sites,
            markdown_output_path=config.markdown_output_path,
            intel_service=mgr.intel_service,
            competitor_service=mgr.competitor_service,
            task_reporter=reporter,
            redis_state_store=mgr.redis_state_store,
            source_governance_service=create_source_governance_service(config),
            document_clustering_service=create_document_clustering_service(config),
            document_version_service=create_document_version_service(config),
            source_governance_enabled=config.source_governance_enabled,
        )
        result = service.run()

        if mgr.redis_state_store:
            mgr.redis_state_store.set_json(
                "logos:last_pipeline_run",
                {"at": datetime.now().isoformat()},
            )
        reporter.finish_run(TaskStatus.SUCCEEDED.value, result)
        logger.info(f"Pipeline 完成: {result}")
        return result
    except Exception as e:
        error = {"message": str(e)}
        reporter.event("pipeline_failed", error)
        reporter.finish_run(TaskStatus.FAILED.value, error=error)
        raise
    finally:
        if lock_acquired and mgr.redis_state_store:
            mgr.redis_state_store.release_lock(lock_key, lock_owner)


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def run_upload_batch_task(self, batch_id, context=None, task_run_id=None):
    """Parse and vectorize a stored upload batch."""
    mgr = get_config_manager()
    mgr.reload()
    context = context or {}
    reporter = TaskRunReporter(
        mgr.task_run_store,
        mgr.redis_state_store,
        run_id=task_run_id,
    )
    if task_run_id:
        reporter.start_run(task_run_id)
    else:
        run = reporter.create_run(
            "upload_batch_ingestion",
            {"batch_id": batch_id, "context": context, "celery_task_id": self.request.id},
            idempotency_key=f"upload_batch:{batch_id}",
        )
        if run:
            reporter.start_run(run.id)

    redis_healthy = bool(mgr.redis_state_store and mgr.redis_state_store.healthcheck())
    lock_key = f"logos:lock:upload:{batch_id}"
    lock_owner = str(uuid4())
    lock_acquired = False
    try:
        if redis_healthy and mgr.redis_state_store:
            lock_acquired = mgr.redis_state_store.acquire_lock(
                lock_key,
                lock_owner,
                ttl_seconds=7200,
            )
            if not lock_acquired:
                result = {"status": "skipped", "reason": "upload_batch_locked", "batch_id": batch_id}
                reporter.finish_run(TaskStatus.SKIPPED.value, result)
                return result

        service = create_document_ingestion_service(mgr)
        documents = service.ingest_batch(
            batch_id,
            context=context,
            task_reporter=reporter,
        )
        batch_result = getattr(service, "last_batch_result", {})
        batch_status = batch_result.get("batch_status", "succeeded")
        result = {
            "status": batch_status,
            "batch_id": batch_id,
            "documents": [document.document_id for document in documents],
            "errors": batch_result.get("errors", []),
        }
        run_status = (
            TaskStatus.SUCCEEDED.value
            if batch_status in {"succeeded", "partial_failed"}
            else TaskStatus.FAILED.value
        )
        reporter.finish_run(
            run_status,
            result,
            {"errors": result["errors"]} if run_status == TaskStatus.FAILED.value else None,
        )
        return result
    except Exception as e:
        error = {"message": str(e), "batch_id": batch_id}
        reporter.event("upload_batch_failed", error)
        reporter.finish_run(TaskStatus.FAILED.value, error=error)
        raise
    finally:
        if lock_acquired and mgr.redis_state_store:
            mgr.redis_state_store.release_lock(lock_key, lock_owner)
