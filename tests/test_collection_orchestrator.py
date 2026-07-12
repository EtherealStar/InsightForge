from models.collection import CollectionRun, CollectionRunStatus, SourceFetchTask, SourceTaskStatus
from services.collection_orchestrator import summarize_run


def test_one_source_failure_produces_partial_failed_run():
    run = CollectionRun()
    tasks = [
        SourceFetchTask(run.id, "a", status=SourceTaskStatus.SUCCEEDED),
        SourceFetchTask(run.id, "b", status=SourceTaskStatus.FAILED),
    ]
    assert summarize_run(tasks) is CollectionRunStatus.PARTIAL_FAILED


def test_pending_task_keeps_run_running():
    run = CollectionRun()
    tasks = [SourceFetchTask(run.id, "a", status=SourceTaskStatus.PENDING)]
    assert summarize_run(tasks) is CollectionRunStatus.RUNNING
