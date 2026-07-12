import structlog
from datetime import datetime
from uuid import uuid4
from celery import shared_task

from core.config_manager import get_config_manager
from core.factory import (
    create_document_clustering_service,
    create_document_ingestion_service,
    create_source_governance_service,
    create_document_version_service,
    create_dedup_maintenance_service,
)
from core.source_config import load_feeds, load_sites
from infrastructure.collector import NewsCollector
from models.task_run import TaskStatus
from services.pipeline_service import PipelineService
from services.task_run_reporter import TaskRunReporter

logger = structlog.get_logger(__name__)


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
