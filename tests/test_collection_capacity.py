from datetime import UTC, datetime

from infrastructure.connectors import SearchConnector
from models.collection import CollectionRun, FetchCandidate, SourceFetchTask
from models.source_governance import SourceProfile
from services.collection_orchestrator import CollectionOrchestrator


class RunStore:
    def __init__(self): self.tasks = []
    def create_run(self, run): return run
    def create_task(self, task): self.tasks.append(task); return task


def test_one_hundred_due_sources_fan_out_independently():
    store = RunStore()
    enqueued = []
    profiles = [f"source-{index}" for index in range(100)]

    run = CollectionOrchestrator(store, enqueued.append).create_run(profiles)

    assert len(store.tasks) == 100
    assert len(enqueued) == 100
    assert len({task.idempotency_key for task in store.tasks}) == 100
    assert all(task.collection_run_id == run.id for task in store.tasks)


def test_ten_thousand_candidates_have_stable_unique_identity():
    profile = SourceProfile("example.com", id="source-1")
    results = [{"id": index, "url": f"https://example.com/post/{index}?utm_source=load"} for index in range(10_000)]

    discovered = SearchConnector(results, observed_at=datetime(2026, 7, 13, tzinfo=UTC)).discover(profile, None)

    assert len(discovered.candidates) == 10_000
    assert len({candidate.idempotency_key for candidate in discovered.candidates}) == 10_000
