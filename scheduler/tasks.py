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
    create_normalized_ingestion_service,
    create_normalized_document_store,
    create_source_rate_limiter,
    create_source_cursor_store,
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


def _finish_source_task_if_terminal(source_task_id: str, config) -> None:
    candidates = create_fetch_candidate_store(config)
    if not candidates.task_candidates_terminal(source_task_id):
        return
    runs = create_collection_run_store(config)
    task = runs.get_task(source_task_id)
    if task is None:
        return
    runs.advance_task(source_task_id, "succeeded")
    runs.reconcile(task.collection_run_id)


@shared_task
def start_collection_run_task():
    """按来源建任务；每条后续 Celery 消息只传数据库 ID。"""
    from services.collection_orchestrator import CollectionOrchestrator
    mgr = get_config_manager()
    profiles = mgr.source_profile_store.list_profiles() if mgr.source_profile_store else []
    from services.source_schedule_service import SourceScheduleService
    schedule = SourceScheduleService(create_source_cursor_store(mgr.config))
    profiles = [profile for profile in profiles if schedule.is_due(profile)]
    store = create_collection_run_store(mgr.config)
    orchestrator = CollectionOrchestrator(store, lambda task_id: discover_source_task.delay(task_id))
    run = orchestrator.create_run([profile.id for profile in profiles])
    return {"collection_run_id": run.id, "source_tasks": len(profiles)}


@shared_task
def reconcile_collection_runs_task():
    """只依据 PostgreSQL 状态补发消息，Redis 丢失不改变最终结论。"""
    from services.collection_orchestrator import CollectionOrchestrator
    config = get_config_manager().config
    store = create_collection_run_store(config)
    orchestrator = CollectionOrchestrator(store, lambda task_id: discover_source_task.delay(task_id))
    run_ids = store.list_active_run_ids()
    results = [orchestrator.reconcile(run_id).status.value for run_id in run_ids]
    return {"runs": len(run_ids), "statuses": results}


@shared_task
def cleanup_fetch_artifacts_task(dry_run: bool = False):
    """清理超过 24 小时且未晋升的 body，永远保留 artifact 审计元数据。"""
    from datetime import UTC, timedelta
    config = get_config_manager().config
    artifacts = create_fetch_artifact_store(config)
    blobs = create_fetch_blob_store(config)
    before = datetime.now(UTC)
    paths = artifacts.list_expired_blob_paths(before)
    if dry_run:
        return {"dry_run": True, "bodies": len(paths), "metadata_expired": 0}
    deleted = sum(1 for path in paths if blobs.delete(path))
    expired = artifacts.expire_unretained(before)
    return {"dry_run": False, "bodies": deleted, "metadata_expired": expired}


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
        from services.source_schedule_service import SourceScheduleService
        cursor_store = create_source_cursor_store(config)
        schedule = SourceScheduleService(cursor_store)
        discovery = asyncio.run(_discover_candidates(profile, config, cursor_store.get_cursor(profile.id)))
        candidate_store = create_fetch_candidate_store(config)
        new_candidates = []
        for candidate in discovery.candidates:
            if candidate_store.find_by_idempotency_key(candidate.idempotency_key) is not None:
                continue
            saved = candidate_store.save_candidate(source_task_id, candidate)
            new_candidates.append(saved)
            queue = fetch_browser_candidate_task if profile.collection_config.get("render_required") else fetch_http_candidate_task
            queue.delay(saved.id, source_task_id)
        next_cursor = discovery.next_cursor.value if discovery.next_cursor else ""
        schedule.record_success(
            profile,
            next_cursor,
            changed=bool(new_candidates),
            etag=discovery.response_headers.get("etag"),
            last_modified=discovery.response_headers.get("last-modified"),
        )
        if not new_candidates:
            store.advance_task(source_task_id, "succeeded")
            store.reconcile(task.collection_run_id)
        return {"source_task_id": source_task_id, "status": "succeeded", "candidates": len(new_candidates)}
    except Exception as exc:
        from services.source_schedule_service import SourceScheduleService
        SourceScheduleService(create_source_cursor_store(config)).record_failure(profile)
        store.advance_task(source_task_id, "failed", {"message": str(exc)})
        raise


async def _discover_candidates(profile, config, cursor=None):
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
        response = await create_http_fetch_engine(config).fetch(
            discovery_candidate,
            SourceFetchPolicy(
                etag=cursor.etag if cursor else None,
                last_modified=cursor.last_modified if cursor else None,
            ),
        )
        if response.status.value == "not_modified":
            from models.collection import DiscoveryResult, SourceCursor
            return DiscoveryResult(
                [],
                SourceCursor(profile.id, cursor.value if cursor else ""),
                response.headers,
            )
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
    result = connector.discover(profile, cursor)
    result.response_headers = response.headers if connector_name != "search" else {}
    return result


def _candidate_fetch_context(candidate_id: str, *, browser: bool):
    from models.collection import SourceFetchPolicy
    from urllib.parse import urlsplit
    mgr = get_config_manager()
    candidate = create_fetch_candidate_store(mgr.config).get_candidate(candidate_id)
    if candidate is None:
        raise KeyError(f"fetch candidate 不存在: {candidate_id}")
    profile = mgr.source_profile_store.get_profile(candidate.source_profile_id) if mgr.source_profile_store else None
    settings = profile.collection_config if profile else {}
    policy = SourceFetchPolicy(
        render_required=browser,
        strict_rate_limit=bool(settings.get("strict_rate_limit", False)),
        requests_per_minute=int(settings.get("requests_per_minute", 30)),
        domain_concurrency=int(settings.get("domain_concurrency", 2)),
        max_response_bytes=int(settings.get("max_response_bytes", 20 * 1024 * 1024)),
        max_decompression_ratio=float(settings.get("max_decompression_ratio", 100.0)),
        timeout_seconds=float(settings.get("timeout_seconds", 30.0)),
        etag=settings.get("etag"),
        last_modified=settings.get("last_modified"),
    )
    previous = create_fetch_artifact_store(mgr.config).latest_for_url(candidate.normalized_url)
    if previous:
        policy.etag = previous.headers.get("etag") or policy.etag
        policy.last_modified = previous.headers.get("last-modified") or policy.last_modified
    return mgr, candidate, profile, policy, urlsplit(candidate.normalized_url).hostname or ""


@shared_task(autoretry_for=(RuntimeError,), retry_backoff=True, retry_jitter=True, max_retries=5)
def fetch_http_candidate_task(candidate_id: str, source_task_id: str):
    mgr, candidate, profile, policy, domain = _candidate_fetch_context(candidate_id, browser=False)
    limiter = create_source_rate_limiter(mgr.config, mgr.redis_state_store)
    if not limiter.acquire(candidate.source_profile_id, domain, policy):
        raise RuntimeError("来源限速中，等待重试")
    try:
        create_fetch_candidate_store(mgr.config).advance_candidate(candidate_id, "fetching")
        artifact = asyncio.run(_collection_execution_service(mgr.config).fetch_candidate(
            candidate_id, source_task_id, create_http_fetch_engine(mgr.config), policy
        ))
        if artifact.status.value == "blocked":
            limiter.cool_down(candidate.source_profile_id, 300, artifact.reason_code or "blocked")
        if artifact.status.value == "fetched":
            create_fetch_candidate_store(mgr.config).advance_candidate(candidate_id, "fetched")
            normalize_artifact_task.delay(artifact.id)
        elif artifact.status.value == "not_modified":
            create_fetch_candidate_store(mgr.config).advance_candidate(candidate_id, "unchanged")
            _finish_source_task_if_terminal(source_task_id, mgr.config)
        else:
            create_fetch_candidate_store(mgr.config).advance_candidate(candidate_id, "failed")
            _finish_source_task_if_terminal(source_task_id, mgr.config)
        return {"artifact_id": artifact.id, "status": artifact.status.value}
    finally:
        limiter.release(candidate.source_profile_id, domain)


@shared_task(autoretry_for=(RuntimeError,), retry_backoff=True, retry_jitter=True, max_retries=3)
def fetch_browser_candidate_task(candidate_id: str, source_task_id: str):
    mgr, candidate, profile, policy, domain = _candidate_fetch_context(candidate_id, browser=True)
    limiter = create_source_rate_limiter(mgr.config, mgr.redis_state_store)
    if not limiter.acquire(candidate.source_profile_id, domain, policy):
        raise RuntimeError("browser 来源限速或 Redis 不可用，等待重试")
    try:
        create_fetch_candidate_store(mgr.config).advance_candidate(candidate_id, "fetching")
        artifact = asyncio.run(_collection_execution_service(mgr.config).fetch_candidate(
            candidate_id, source_task_id, create_browser_fetch_engine(mgr.config), policy
        ))
        if artifact.status.value == "blocked":
            limiter.cool_down(candidate.source_profile_id, 600, artifact.reason_code or "blocked")
        if artifact.status.value == "fetched":
            create_fetch_candidate_store(mgr.config).advance_candidate(candidate_id, "fetched")
            normalize_artifact_task.delay(artifact.id)
        else:
            create_fetch_candidate_store(mgr.config).advance_candidate(candidate_id, "failed")
            _finish_source_task_if_terminal(source_task_id, mgr.config)
        return {"artifact_id": artifact.id, "status": artifact.status.value}
    finally:
        limiter.release(candidate.source_profile_id, domain)


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
    # PDF 可能同时携带质量告警；只要明确要求 OCR，就优先进入专用队列。
    if "pdf_requires_ocr" in document.reason_codes:
        ocr_artifact_task.delay(artifact.id)
    elif document.outcome.value == "retry_render" and artifact.fetch_method.value == "http":
        fetch_browser_candidate_task.delay(artifact.candidate_id, artifact.source_task_id)
    elif _collection_execution_service(config).should_ingest(document, profile):
        create_fetch_candidate_store(config).advance_candidate(artifact.candidate_id, "accepted")
        ingest_normalized_document_task.delay(document.id)
        _finish_source_task_if_terminal(artifact.source_task_id, config)
    else:
        candidate_status = "review_required" if document.outcome.value == "review_required" else "rejected"
        create_fetch_candidate_store(config).advance_candidate(artifact.candidate_id, candidate_status)
        _finish_source_task_if_terminal(artifact.source_task_id, config)
    return {"normalized_document_id": document.id, "outcome": document.outcome.value}


@shared_task
def ingest_normalized_document_task(normalized_document_id: str):
    mgr = get_config_manager()
    result = create_normalized_ingestion_service(mgr.config, mgr).ingest(normalized_document_id)
    if result.status == "vectorized":
        enrich_normalized_document_task.delay(normalized_document_id, result.document_id)
    return {
        "normalized_document_id": result.normalized_document_id,
        "document_id": result.document_id,
        "document_version_id": result.document_version_id,
        "points": result.points,
        "status": result.status,
    }


@shared_task
def enrich_normalized_document_task(normalized_document_id: str, document_id: str):
    mgr = get_config_manager()
    facts = mgr.intel_service.extract_facts_from_document(document_id) if mgr.intel_service else {
        "created": 0, "updated": 0, "skipped": 0, "reason": "intel_service_missing"
    }
    links = mgr.competitor_service.auto_link_facts(document_ids=[document_id]) if mgr.competitor_service else {
        "linked": 0, "reason": "competitor_service_missing"
    }
    return {
        "normalized_document_id": normalized_document_id,
        "document_id": document_id,
        "status": "enriched",
        "facts": facts,
        "links": links,
    }


@shared_task
def ocr_artifact_task(artifact_id: str):
    from models.collection import NormalizerRules
    from services.pdf_normalization_service import PdfTextNormalizationService
    mgr = get_config_manager()
    artifacts = create_fetch_artifact_store(mgr.config)
    artifact = artifacts.get_artifact(artifact_id)
    if artifact is None or not artifact.blob_path:
        raise KeyError(f"PDF artifact 不存在或 body 已清理: {artifact_id}")
    normalized_store = create_normalized_document_store(mgr.config)
    existing = normalized_store.find_version(artifact.id, "pdf-text-v1")
    document = existing or PdfTextNormalizationService().normalize(
        artifact,
        create_fetch_blob_store(mgr.config).get(artifact.blob_path),
        NormalizerRules("pdf-text-v1"),
    )
    if existing is None:
        document = normalized_store.save_document(document)
    candidate = create_fetch_candidate_store(mgr.config).get_candidate(artifact.candidate_id)
    profile = mgr.source_profile_store.get_profile(candidate.source_profile_id) if candidate and mgr.source_profile_store else None
    if _collection_execution_service(mgr.config).should_ingest(document, profile):
        create_fetch_candidate_store(mgr.config).advance_candidate(artifact.candidate_id, "accepted")
        ingest_normalized_document_task.delay(document.id)
    else:
        create_fetch_candidate_store(mgr.config).advance_candidate(artifact.candidate_id, "review_required")
    _finish_source_task_if_terminal(artifact.source_task_id, mgr.config)
    return {"artifact_id": artifact.id, "normalized_document_id": document.id, "outcome": document.outcome.value}


@shared_task
def rebuild_dedup_cache_task(batch_size=1000):
    """从 PostgreSQL 权威 occurrence 全量重建 Redis 热点索引。"""
    config = get_config_manager().config
    result = create_dedup_maintenance_service(config).rebuild_cache(batch_size=batch_size)
    logger.info("dedup_cache.rebuilt", **result)
    return result

def _legacy_pipeline_removed(self, manual=False, task_run_id=None):
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
