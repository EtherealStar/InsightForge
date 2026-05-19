"""Task run history models.

PostgreSQL owns durable task run, stage, and event records. Redis may mirror
execution-time state, but these dataclasses represent the authoritative rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class TaskStatus(StrEnum):
    """Shared lifecycle states for task runs and stages."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


def new_task_id() -> str:
    return str(uuid4())


@dataclass
class TaskRun:
    """Durable top-level asynchronous task run."""

    id: str
    task_type: str
    status: str = TaskStatus.PENDING.value
    idempotency_key: str | None = None
    input: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] = field(default_factory=dict)
    attempt: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class TaskStage:
    """Durable stage record within a task run."""

    id: str
    task_run_id: str
    name: str
    status: str = TaskStatus.PENDING.value
    result: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


@dataclass
class TaskEvent:
    """Append-only task event for audit and realtime replay."""

    id: str
    task_run_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    stage_id: str | None = None
    created_at: datetime | None = None
