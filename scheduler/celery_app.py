import os
import structlog
from celery import Celery
from celery.signals import setup_logging as celery_setup_logging
from celery.signals import task_prerun, task_postrun
from celery.schedules import crontab
from core.config_manager import get_config_manager
from core.logging import setup_logging

mgr = get_config_manager()
config = mgr.config

app = Celery(
    "logos_scheduler",
    broker=config.celery_broker_url,
    backend=config.celery_result_backend,
    include=["scheduler.tasks"]
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    beat_schedule={
        "collection-beat": {
            "task": "scheduler.tasks.start_collection_run_task",
            "schedule": crontab(minute="*/5"),  # 每5分钟检查一次是否需要执行
        },
        "collection-reconcile": {
            "task": "scheduler.tasks.reconcile_collection_runs_task",
            "schedule": 60.0,
        },
        "collection-artifact-cleanup": {
            "task": "scheduler.tasks.cleanup_fetch_artifacts_task",
            "schedule": crontab(minute=15, hour="*"),
        },
    },
    task_routes={
        "scheduler.tasks.fetch_http_candidate_task": {"queue": "fetch.http"},
        "scheduler.tasks.fetch_browser_candidate_task": {"queue": "fetch.browser"},
        "scheduler.tasks.normalize_artifact_task": {"queue": "normalize"},
        "scheduler.tasks.ingest_normalized_document_task": {"queue": "ingest"},
        "scheduler.tasks.enrich_normalized_document_task": {"queue": "enrich"},
        "scheduler.tasks.ocr_artifact_task": {"queue": "ocr"},
    },
)

@celery_setup_logging.connect
def on_setup_logging(**kwargs):
    # 接管 celery 的日志，改为使用 structlog
    setup_logging(level=config.log_level)

@task_prerun.connect
def on_task_prerun(task_id, task, **kwargs):
    # 任务开始时注入 task_id 和 task_name 到日志上下文
    structlog.contextvars.bind_contextvars(task_id=task_id, task_name=task.name)

@task_postrun.connect
def on_task_postrun(**kwargs):
    # 任务结束时清理上下文，避免串线
    structlog.contextvars.clear_contextvars()

if __name__ == "__main__":
    app.start()
