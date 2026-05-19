import structlog
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from celery.result import AsyncResult

from delivery.auth import require_viewer

router = APIRouter(prefix="/api/tasks", tags=["tasks"], dependencies=[Depends(require_viewer)])
logger = structlog.get_logger(__name__)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _get_celery_app():
    from scheduler.celery_app import app as celery_app

    return celery_app


@router.get("")
def list_task_runs(
    task_type: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    actor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List durable asynchronous task runs."""
    try:
        from core.config_manager import get_config_manager

        filters: dict[str, Any] = {}
        if task_type:
            filters["task_type"] = task_type
        if status:
            filters["status"] = status
        if date_from:
            filters["date_from"] = date_from.isoformat()
        if date_to:
            filters["date_to"] = date_to.isoformat()
        if actor:
            filters["actor"] = actor

        store = get_config_manager().task_run_store
        if not store:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        runs, total = store.list_runs(filters=filters, limit=limit, offset=offset)
        return {
            "items": [_jsonable(run) for run in runs],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error("获取任务列表失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {e}")


@router.get("/{task_id}")
def get_task_status(task_id: str):
    """获取异步任务的状态和结果"""
    try:
        from core.config_manager import get_config_manager

        task_result = AsyncResult(task_id, app=_get_celery_app())
        celery_status = task_result.status
        run = None
        stages = []
        events = []
        task_history_error = None

        try:
            store = get_config_manager().task_run_store
            run = store.get_run(task_id) if store else None
            if run:
                stages = store.list_stages(task_id)
                events = store.list_events(task_id)
        except Exception as history_err:
            task_history_error = str(history_err)
            logger.warning(
                "获取任务历史失败",
                task_id=task_id,
                error=task_history_error,
            )

        terminal_statuses = {"succeeded", "failed", "cancelled", "skipped"}
        run_status = run.status if run else None
        ready = task_result.ready() or run_status in terminal_statuses
        response = {
            "task_id": task_id,
            "status": run_status or celery_status,
            "ready": ready,
            "run": _jsonable(run) if run else None,
            "stages": _jsonable(stages),
            "events": _jsonable(events),
            "celery_status": celery_status,
        }

        if task_history_error:
            response["task_history_error"] = task_history_error

        if run and run.result:
            response["result"] = _jsonable(run.result)
        if run and run.error:
            response["error"] = _jsonable(run.error)

        if task_result.ready():
            if task_result.successful():
                response.setdefault("result", task_result.result)
            else:
                response.setdefault("error", str(task_result.result))
                
        return response
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取任务状态失败: {e}")
