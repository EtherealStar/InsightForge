"""Collection Run 的来源级扇出和 PostgreSQL fan-in 规则。"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from models.collection import CollectionRun, CollectionRunStatus, SourceFetchTask, SourceTaskStatus


TERMINAL_TASK_STATUSES = {SourceTaskStatus.SUCCEEDED, SourceTaskStatus.FAILED, SourceTaskStatus.PAUSED}


def summarize_run(tasks: list[SourceFetchTask]) -> CollectionRunStatus:
    if not tasks or any(task.status not in TERMINAL_TASK_STATUSES for task in tasks):
        return CollectionRunStatus.RUNNING
    failures = sum(task.status in {SourceTaskStatus.FAILED, SourceTaskStatus.PAUSED} for task in tasks)
    if failures == 0:
        return CollectionRunStatus.SUCCEEDED
    if failures == len(tasks):
        return CollectionRunStatus.FAILED
    return CollectionRunStatus.PARTIAL_FAILED


class CollectionOrchestrator:
    def __init__(self, store, enqueue_source_task: Callable[[str], None]):
        self.store = store
        self.enqueue_source_task = enqueue_source_task

    def create_run(self, source_profile_ids: list[str]) -> CollectionRun:
        run = self.store.create_run(CollectionRun(status=CollectionRunStatus.RUNNING, started_at=datetime.now(UTC)))
        for profile_id in source_profile_ids:
            task = self.store.create_task(SourceFetchTask(run.id, profile_id))
            # 数据库身份先提交，消息只携带 task ID；消息丢失可由 reconciler 重建。
            self.enqueue_source_task(task.id)
        return run

    def reconcile(self, run_id: str, *, stale_after: timedelta = timedelta(minutes=10)) -> CollectionRun:
        tasks = self.store.list_tasks(run_id)
        stale_before = datetime.now(UTC) - stale_after
        for task in tasks:
            if task.status is SourceTaskStatus.PENDING or (
                task.status is SourceTaskStatus.RUNNING and task.updated_at < stale_before
            ):
                self.enqueue_source_task(task.id)
        return self.store.finish_run(run_id, summarize_run(tasks))
