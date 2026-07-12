"""PipelineService tests for document parent chunks + Qdrant child points."""

from datetime import datetime
from unittest.mock import MagicMock

from models.article import Article, Language
from models.document import ChildChunkPoint, ParentDocumentChunk
from models.document_governance import DedupCommitResult, DedupDecision
from models.task_run import TaskEvent, TaskRun, TaskStage
from services.pipeline_service import PipelineService
from services.task_run_reporter import TaskRunReporter


def _article(article_id: int = 1) -> Article:
    return Article(
        id=article_id,
        title="Pipeline Test",
        url="https://example.com/pipeline",
        content="Pipeline test content",
        source="PipelineSource",
        language=Language.EN,
        published_at=datetime.now(),
    )


def _service(
    document_store=None,
    vector_index=None,
    embedding_client=None,
    chunking_service=None,
    collector=None,
    task_reporter=None,
    intel_service=None,
    competitor_service=None,
    document_clustering_service=None,
):
    if document_clustering_service is None:
        document_clustering_service = MagicMock()

        def commit(occurrence):
            occurrence.document_id = "cluster-test"
            return DedupCommitResult(occurrence, DedupDecision.NEW_CLUSTER, True, True)

        document_clustering_service.commit.side_effect = commit
    return PipelineService(
        collector=collector or MagicMock(),
        document_store=document_store or MagicMock(),
        vector_index=vector_index or MagicMock(),
        embedding_client=embedding_client or MagicMock(),
        chunking_service=chunking_service,
        task_reporter=task_reporter,
        intel_service=intel_service,
        competitor_service=competitor_service,
        document_clustering_service=document_clustering_service,
    )


class FakeTaskRunStore:
    def __init__(self):
        self.stages = []
        self.events = []

    def create_run(self, task_type, input, idempotency_key=None):
        return TaskRun(id="run-1", task_type=task_type, input=input)

    def start_run(self, run_id):
        return TaskRun(id=run_id, task_type="pipeline", status="running")

    def finish_run(self, run_id, status, result=None, error=None):
        return TaskRun(id=run_id, task_type="pipeline", status=status)

    def create_stage(self, run_id, name):
        stage = TaskStage(id=f"stage-{len(self.stages) + 1}", task_run_id=run_id, name=name)
        self.stages.append(stage)
        return stage

    def finish_stage(self, stage_id, status, result=None, error=None):
        stage = next(item for item in self.stages if item.id == stage_id)
        stage.status = status
        stage.result = result or {}
        stage.error = error or {}
        return stage

    def append_event(self, run_id, event_type, payload=None, stage_id=None):
        event = TaskEvent(
            id=f"event-{len(self.events) + 1}",
            task_run_id=run_id,
            event_type=event_type,
            payload=payload or {},
            stage_id=stage_id,
        )
        self.events.append(event)
        return event

    def get_run(self, run_id):
        return TaskRun(id=run_id, task_type="pipeline")

    def list_stages(self, run_id):
        return [stage for stage in self.stages if stage.task_run_id == run_id]

    def list_events(self, run_id, limit=200):
        return [event for event in self.events if event.task_run_id == run_id][:limit]


def _chunking_service():
    cs = MagicMock()
    child = ChildChunkPoint(
        point_id="doc:c:0",
        document_id="doc",
        parent_chunk_id="doc:p0",
        content="child chunk",
        token_count=10,
        chunk_index=0,
        doc_name="test doc",
    )
    parent = ParentDocumentChunk(
        parent_chunk_id="doc:p0",
        document_id="doc",
        content="parent chunk",
        token_count=10,
        child_point_ids=["doc:c:0"],
        doc_name="test doc",
    )
    cs.chunk_documents.return_value = ([child], [parent])
    return cs


def test_pipeline_full_run(mock_embedding_client):
    document_store = MagicMock()
    document_store.save_parent_chunks.return_value = 1
    vector_index = MagicMock()
    vector_index.upsert_child_chunks.return_value = 1
    collector = MagicMock()
    collector.fetch_all.return_value = [_article(None)]
    intel_service = MagicMock()
    intel_service.extract_facts_from_document.return_value = {
        "created": 1,
        "updated": 0,
        "skipped": 0,
    }
    competitor_service = MagicMock()
    competitor_service.auto_link_facts.return_value = {"linked": 1, "facts_processed": 1}

    service = _service(
        document_store=document_store,
        vector_index=vector_index,
        embedding_client=mock_embedding_client,
        chunking_service=_chunking_service(),
        collector=collector,
        intel_service=intel_service,
        competitor_service=competitor_service,
    )
    result = service.run()

    assert result["fetched"] == 1
    assert result["new"] == 1
    assert result["embedded"] == 1
    assert result["facts_created"] == 1
    assert result["intel_linked"] == 1
    assert result["errors"] == []
    document_store.save_document.assert_called()
    document_store.save_parent_chunks.assert_called()
    vector_index.upsert_child_chunks.assert_called()
    document_store.mark_points_vectorized.assert_called()
    document_store.update_parse_status.assert_called()


def test_embed_with_chunks_writes_parent_before_embedding_and_qdrant(mock_embedding_client):
    calls = []
    document_store = MagicMock()
    document_store.save_document.side_effect = lambda doc: calls.append("document") or doc
    document_store.save_parent_chunks.side_effect = lambda parents: calls.append("parents") or len(parents)
    document_store.mark_points_vectorized.side_effect = lambda points: calls.append("status")
    mock_embedding_client.embed = MagicMock(
        side_effect=lambda texts: calls.append("embeddings") or [[0.1] * 1536 for _ in texts]
    )
    vector_index = MagicMock()
    vector_index.upsert_child_chunks.side_effect = (
        lambda chunks, embeddings: calls.append("qdrant") or len(chunks)
    )

    service = _service(
        document_store=document_store,
        vector_index=vector_index,
        embedding_client=mock_embedding_client,
        chunking_service=_chunking_service(),
    )
    document = service._article_to_document(_article(), "cluster-test")
    result = {"chunks": 0, "parent_chunks": 0}
    embedded = service._embed_documents([document], result)

    assert embedded == 1
    assert calls == ["parents", "embeddings", "qdrant", "status"]


def test_pipeline_does_not_mark_embedded_when_qdrant_write_incomplete(mock_embedding_client):
    document_store = MagicMock()
    document_store.save_parent_chunks.return_value = 1
    vector_index = MagicMock()
    vector_index.upsert_child_chunks.return_value = 0
    collector = MagicMock()
    collector.fetch_all.return_value = [_article(None)]

    service = _service(
        document_store=document_store,
        vector_index=vector_index,
        embedding_client=mock_embedding_client,
        chunking_service=_chunking_service(),
        collector=collector,
    )
    result = service.run()

    assert result["embedded"] == 0
    assert len(result["errors"]) == 1


def test_pipeline_records_task_stages_and_events(mock_embedding_client):
    document_store = MagicMock()
    document_store.save_parent_chunks.return_value = 1
    vector_index = MagicMock()
    vector_index.upsert_child_chunks.return_value = 1
    collector = MagicMock()
    collector.fetch_all.return_value = [_article(None)]
    task_store = FakeTaskRunStore()

    service = _service(
        document_store=document_store,
        vector_index=vector_index,
        embedding_client=mock_embedding_client,
        chunking_service=_chunking_service(),
        collector=collector,
        task_reporter=TaskRunReporter(task_store, run_id="run-1"),
    )

    result = service.run()

    assert result["embedded"] == 1
    stage_names = {stage.name for stage in task_store.stages}
    assert {
        "collect",
        "markdown",
        "store_source_documents",
        "chunk_and_vectorize",
        "extract_intel_facts",
        "link_facts",
    }.issubset(stage_names)
    assert "summary" not in stage_names
    assert any(event.event_type == "qdrant_upsert" for event in task_store.events)


def test_authoritative_duplicate_only_records_occurrence(mock_embedding_client):
    collector = MagicMock()
    collector.fetch_all.return_value = [_article()]
    clustering = MagicMock()

    def commit(occurrence):
        occurrence.document_id = "cluster-existing"
        return DedupCommitResult(occurrence, DedupDecision.DUPLICATE, False)

    clustering.commit.side_effect = commit
    document_store = MagicMock()
    vector_index = MagicMock()
    intel_service = MagicMock()
    service = _service(
        collector=collector,
        document_store=document_store,
        vector_index=vector_index,
        embedding_client=mock_embedding_client,
        chunking_service=_chunking_service(),
        intel_service=intel_service,
        document_clustering_service=clustering,
    )

    result = service.run()

    assert result["duplicates"] == 1
    assert result["documents"] == 0
    document_store.save_document.assert_not_called()
    vector_index.upsert_child_chunks.assert_not_called()
    intel_service.extract_facts_from_document.assert_not_called()


def test_authoritative_new_cluster_uses_stable_cluster_id(mock_embedding_client):
    clustering = MagicMock()

    def commit(occurrence):
        occurrence.document_id = "cluster-new"
        return DedupCommitResult(occurrence, DedupDecision.NEW_CLUSTER, True)

    clustering.commit.side_effect = commit
    service = _service(
        document_clustering_service=clustering,
    )
    result = {"duplicates": 0, "duplicate_candidates": 0, "quarantined": 0}

    documents = service._prepare_documents([_article()], result)

    assert [document.document_id for document in documents] == ["cluster-new"]
    occurrence = clustering.commit.call_args.args[0]
    assert occurrence.normalized_url == "https://example.com/pipeline"


def test_unfinished_existing_cluster_is_replayed_for_build(mock_embedding_client):
    clustering = MagicMock()

    def commit(occurrence):
        occurrence.document_id = "cluster-unfinished"
        return DedupCommitResult(
            occurrence,
            DedupDecision.UNCHANGED,
            created_cluster=False,
            requires_build=True,
        )

    clustering.commit.side_effect = commit
    service = _service(document_clustering_service=clustering)
    result = {"duplicates": 0, "duplicate_candidates": 0, "quarantined": 0}

    documents = service._prepare_documents([_article()], result)

    assert [document.document_id for document in documents] == ["cluster-unfinished"]
    assert result["duplicates"] == 0
