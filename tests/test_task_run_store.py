"""PostgresTaskRunStore tests."""

import os

import pytest

from infrastructure.task_run_store import PostgresTaskRunStore


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_PG_DSN"),
    reason="Requires PostgreSQL instance with infrastructure migrations applied",
)


def test_task_run_store_persists_run_stage_and_events(test_dsn):
    store = PostgresTaskRunStore(test_dsn)

    run = store.create_run(
        task_type="upload_parse",
        input={"batch_id": "batch-1"},
        idempotency_key="upload:batch-1",
    )
    assert run.status == "pending"
    assert run.input == {"batch_id": "batch-1"}
    assert run.result == {}
    assert run.error == {}

    running = store.start_run(run.id)
    assert running.status == "running"
    assert running.started_at is not None
    assert running.updated_at >= running.created_at

    stage = store.create_stage(run.id, "parse_documents")
    assert stage.status == "running"
    assert stage.started_at is not None

    first_event = store.append_event(
        run.id,
        "stage_started",
        {"name": stage.name},
        stage_id=stage.id,
    )
    second_event = store.append_event(
        run.id,
        "stage_finished",
        {"name": stage.name},
        stage_id=stage.id,
    )

    finished_stage = store.finish_stage(
        stage.id,
        "succeeded",
        result={"documents": 2},
    )
    assert finished_stage.status == "succeeded"
    assert finished_stage.result == {"documents": 2}
    assert finished_stage.error == {}
    assert finished_stage.finished_at is not None

    finished_run = store.finish_run(
        run.id,
        "succeeded",
        result={"documents": 2},
    )
    assert finished_run.status == "succeeded"
    assert finished_run.result == {"documents": 2}
    assert finished_run.error == {}
    assert finished_run.finished_at is not None

    loaded = store.get_run(run.id)
    assert loaded is not None
    assert loaded.idempotency_key == "upload:batch-1"

    stages = store.list_stages(run.id)
    assert [item.id for item in stages] == [stage.id]
    assert stages[0].name == "parse_documents"

    events = store.list_events(run.id)
    assert [event.id for event in events] == [first_event.id, second_event.id]
    assert events[0].payload == {"name": "parse_documents"}
    assert events[0].stage_id == stage.id
