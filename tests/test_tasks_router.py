"""Task status API response tests."""

from models.task_run import TaskEvent, TaskRun, TaskStage
from delivery.api.tasks_router import get_task_status, list_task_runs


class FakeAsyncResult:
    status = "PENDING"
    result = None

    def __init__(self, task_id, app=None):
        self.task_id = task_id

    def ready(self):
        return False

    def successful(self):
        return False


class FakeTaskStore:
    def list_runs(self, filters=None, limit=50, offset=0):
        return (
            [
                TaskRun(
                    id="run-1",
                    task_type="pipeline",
                    status="succeeded",
                    result={"embedded": 3},
                )
            ],
            1,
        )

    def get_run(self, run_id):
        return TaskRun(
            id=run_id,
            task_type="pipeline",
            status="succeeded",
            result={"embedded": 3},
        )

    def list_stages(self, run_id):
        return [
            TaskStage(
                id="stage-1",
                task_run_id=run_id,
                name="vectorize",
                status="succeeded",
            )
        ]

    def list_events(self, run_id, limit=200):
        return [
            TaskEvent(
                id="event-1",
                task_run_id=run_id,
                event_type="qdrant_upsert",
                payload={"points": 3},
                stage_id="stage-1",
            )
        ]


class FakeConfigManager:
    task_run_store = FakeTaskStore()


def test_task_status_includes_postgres_history(monkeypatch):
    import core.config_manager as config_manager
    import delivery.api.tasks_router as tasks_router

    monkeypatch.setattr(tasks_router, "AsyncResult", FakeAsyncResult)
    monkeypatch.setattr(tasks_router, "_get_celery_app", lambda: None)
    monkeypatch.setattr(config_manager, "get_config_manager", lambda: FakeConfigManager())

    response = get_task_status("run-1")

    assert response["task_id"] == "run-1"
    assert response["status"] == "succeeded"
    assert response["ready"] is True
    assert response["celery_status"] == "PENDING"
    assert response["result"] == {"embedded": 3}
    assert response["run"]["task_type"] == "pipeline"
    assert response["stages"][0]["name"] == "vectorize"
    assert response["events"][0]["event_type"] == "qdrant_upsert"


def test_list_task_runs_returns_paginated_items(monkeypatch):
    import core.config_manager as config_manager

    monkeypatch.setattr(config_manager, "get_config_manager", lambda: FakeConfigManager())

    response = list_task_runs(task_type="pipeline", status="succeeded", limit=20, offset=0)

    assert response["total"] == 1
    assert response["limit"] == 20
    assert response["offset"] == 0
    assert response["items"][0]["id"] == "run-1"
    assert response["items"][0]["task_type"] == "pipeline"
