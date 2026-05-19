"""Lightweight task run audit helper."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from core.protocols import RedisStateStoreProtocol, TaskRunStoreProtocol
from models.task_run import TaskRun, TaskStage, TaskStatus

logger = structlog.get_logger(__name__)


@dataclass
class TaskRunReporter:
    """Mirror durable task history to PostgreSQL and best-effort Redis state."""

    task_run_store: TaskRunStoreProtocol | None = None
    redis_state_store: RedisStateStoreProtocol | None = None
    run_id: str | None = None

    def create_run(
        self,
        task_type: str,
        input: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> TaskRun | None:
        if not self.task_run_store:
            return None
        run = self.task_run_store.create_run(
            task_type,
            input or {},
            idempotency_key=idempotency_key,
        )
        self.run_id = run.id
        self.set_status(run.status, {"task_type": task_type})
        self.event("run_created", {"task_type": task_type, "input": input or {}})
        return run

    def start_run(self, run_id: str | None = None) -> TaskRun | None:
        if run_id:
            self.run_id = run_id
        if not self.task_run_store or not self.run_id:
            return None
        run = self.task_run_store.start_run(self.run_id)
        self.set_status(run.status, {"task_type": run.task_type})
        self.event("run_started", {"task_type": run.task_type})
        return run

    def finish_run(
        self,
        status: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> TaskRun | None:
        if not self.task_run_store or not self.run_id:
            return None
        run = self.task_run_store.finish_run(
            self.run_id,
            status,
            result=result,
            error=error,
        )
        self.set_status(status, {"result": result or {}, "error": error or {}})
        self.event("run_finished", {"status": status, "result": result or {}, "error": error or {}})
        return run

    def start_stage(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
    ) -> TaskStage | None:
        if not self.task_run_store or not self.run_id:
            return None
        stage = self.task_run_store.create_stage(self.run_id, name)
        payload = payload or {}
        self.set_status(TaskStatus.RUNNING.value, {"stage": name, **payload})
        self.event("stage_started", {"name": name, **payload}, stage_id=stage.id)
        return stage

    def finish_stage(
        self,
        stage: TaskStage | None,
        status: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> TaskStage | None:
        if not self.task_run_store or not self.run_id or not stage:
            return None
        finished = self.task_run_store.finish_stage(
            stage.id,
            status,
            result=result,
            error=error,
        )
        payload = {
            "name": stage.name,
            "status": status,
            "result": result or {},
            "error": error or {},
        }
        self.set_status(status, payload)
        self.event("stage_finished", payload, stage_id=stage.id)
        return finished

    def event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        stage_id: str | None = None,
    ) -> None:
        if not self.run_id:
            return
        event_payload = payload or {}
        if self.task_run_store:
            try:
                self.task_run_store.append_event(
                    self.run_id,
                    event_type,
                    event_payload,
                    stage_id=stage_id,
                )
            except Exception as e:
                logger.warning(
                    "task_reporter.append_event_failed",
                    run_id=self.run_id,
                    event_type=event_type,
                    error=str(e),
                )
        if self.redis_state_store:
            self.redis_state_store.append_task_event(
                self.run_id,
                {"event_type": event_type, "payload": event_payload, "stage_id": stage_id},
            )

    def set_status(self, status: str, payload: dict[str, Any] | None = None) -> None:
        if self.redis_state_store and self.run_id:
            self.redis_state_store.set_task_status(
                self.run_id,
                status,
                payload or {},
                ttl_seconds=86400,
            )
