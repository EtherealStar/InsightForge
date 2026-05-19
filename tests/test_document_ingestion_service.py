"""DocumentIngestionService tests."""

from infrastructure.chunking_service import ChunkingService
from infrastructure.parsers.document_parser import DocumentParser
from models.file_asset import DocumentBlob
from models.task_run import TaskEvent, TaskRun, TaskStage
from services.document_ingestion_service import DocumentIngestionService
from services.task_run_reporter import TaskRunReporter


class FakeUploadStore:
    def __init__(self, blobs):
        self.blobs = blobs
        self.statuses = {}
        self.finished = None

    def create_batch(self, batch):
        return batch

    def finish_batch(self, batch_id, status, error=None):
        self.finished = (batch_id, status, error)
        return None

    def save_blob(self, blob):
        return blob

    def get_blob(self, blob_id):
        return next((blob for blob in self.blobs if blob.id == blob_id), None)

    def list_blobs(self, batch_id):
        return [blob for blob in self.blobs if blob.upload_batch_id == batch_id]

    def find_blobs_by_sha256(self, sha256):
        return [blob for blob in self.blobs if blob.sha256 == sha256]

    def update_blob_status(self, blob_id, status, error=None):
        self.statuses[blob_id] = (status, error)


class FakeDocumentStore:
    def __init__(self):
        self.documents = {}
        self.statuses = {}
        self.parents = []
        self.vectorized = []

    def save_document(self, document):
        self.documents[document.document_id] = document
        return document

    def get_document(self, document_id):
        return self.documents.get(document_id)

    def list_documents(self, filters=None, limit=50, offset=0):
        return list(self.documents.values())

    def update_parse_status(self, document_id, status, error=None):
        self.statuses[document_id] = (status, error)

    def save_parent_chunks(self, parent_chunks):
        self.parents.extend(parent_chunks)
        return len(parent_chunks)

    def get_parent_chunks_by_ids(self, parent_chunk_ids):
        return [pc for pc in self.parents if pc.parent_chunk_id in parent_chunk_ids]

    def search_parent_chunks_by_keyword(self, query, top_k=20):
        return []

    def mark_points_vectorized(self, points):
        self.vectorized.extend(points)

    def mark_points_vector_failed(self, point_ids, error):
        pass

    def delete_document(self, document_id):
        self.documents.pop(document_id, None)


class FakeEmbedding:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeVectorIndex:
    def __init__(self):
        self.upserted = []

    def healthcheck(self):
        return True

    def ensure_collection(self):
        return None

    def recreate_collection(self):
        return None

    def upsert_child_chunks(self, chunks, embeddings):
        self.upserted.extend(chunks)
        assert len(chunks) == len(embeddings)
        return len(chunks)

    def search_child_chunks(self, query_embedding, top_k=10, filters=None):
        return []

    def delete_by_document_ids(self, document_ids):
        return None

    def delete_by_point_ids(self, point_ids):
        return None


class FakeTaskRunStore:
    def __init__(self):
        self.create_run_calls = []
        self.started = []
        self.finished = []
        self.stages = []
        self.events = []

    def create_run(self, task_type, input, idempotency_key=None):
        self.create_run_calls.append((task_type, input, idempotency_key))
        return TaskRun(id="run-new", task_type=task_type, input=input)

    def start_run(self, run_id):
        self.started.append(run_id)
        return TaskRun(id=run_id, task_type="upload_batch_ingestion", status="running")

    def finish_run(self, run_id, status, result=None, error=None):
        self.finished.append((run_id, status, result, error))
        return TaskRun(id=run_id, task_type="upload_batch_ingestion", status=status)

    def create_stage(self, run_id, name):
        stage = TaskStage(id=f"stage-{len(self.stages) + 1}", task_run_id=run_id, name=name)
        self.stages.append(stage)
        return stage

    def finish_stage(self, stage_id, status, result=None, error=None):
        stage = next(stage for stage in self.stages if stage.id == stage_id)
        return TaskStage(
            id=stage.id,
            task_run_id=stage.task_run_id,
            name=stage.name,
            status=status,
            result=result or {},
            error=error or {},
        )

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
        return TaskRun(id=run_id, task_type="upload_batch_ingestion")

    def list_stages(self, run_id):
        return [stage for stage in self.stages if stage.task_run_id == run_id]

    def list_events(self, run_id, limit=200):
        return [event for event in self.events if event.task_run_id == run_id][:limit]


def _blob(path, batch_id="batch-1"):
    return DocumentBlob(
        upload_batch_id=batch_id,
        original_filename=path.name,
        safe_filename=path.name,
        content_type="text/markdown",
        file_ext=".md",
        size_bytes=path.stat().st_size,
        sha256="sha",
        storage_path=str(path),
    )


def test_document_ingestion_service_indexes_markdown_blob(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# Product\n\nThis product launched a new feature.", encoding="utf-8")
    blob = _blob(path)
    upload_store = FakeUploadStore([blob])
    document_store = FakeDocumentStore()
    vector_index = FakeVectorIndex()
    service = DocumentIngestionService(
        upload_store=upload_store,
        document_store=document_store,
        parser=DocumentParser(),
        chunking_service=ChunkingService(max_child_tokens=120, target_parent_tokens=240),
        embedding_client=FakeEmbedding(),
        vector_index=vector_index,
    )

    document = service.ingest_blob(
        blob,
        context={"document_type": "competitor_doc", "competitor_ids": [1]},
    )

    assert document.source_type == "upload"
    assert document.document_type == "competitor_doc"
    assert document.competitor_ids == [1]
    assert document_store.statuses[document.document_id][0] == "vectorized"
    assert upload_store.statuses[blob.id][0] == "parsed"
    assert document_store.parents
    assert vector_index.upserted
    assert document_store.vectorized == vector_index.upserted


def test_document_ingestion_service_batch_marks_partial_failure(tmp_path):
    good = tmp_path / "good.md"
    bad = tmp_path / "bad.pdf"
    good.write_text("# Good\n\nContent", encoding="utf-8")
    bad.write_bytes(b"%PDF")
    blobs = [_blob(good), _blob(bad)]
    blobs[1].original_filename = "bad.pdf"
    blobs[1].safe_filename = "bad.pdf"
    blobs[1].file_ext = ".pdf"
    upload_store = FakeUploadStore(blobs)
    service = DocumentIngestionService(
        upload_store=upload_store,
        document_store=FakeDocumentStore(),
        parser=DocumentParser(),
        chunking_service=ChunkingService(max_child_tokens=120, target_parent_tokens=240),
        embedding_client=FakeEmbedding(),
        vector_index=FakeVectorIndex(),
    )

    documents = service.ingest_batch("batch-1")

    assert len(documents) == 1
    assert upload_store.finished[1] == "partial_failed"
    assert upload_store.statuses[blobs[1].id][0] == "failed"


def test_document_ingestion_service_reuses_existing_task_run(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# Product\n\nThis product launched a new feature.", encoding="utf-8")
    blob = _blob(path)
    upload_store = FakeUploadStore([blob])
    task_store = FakeTaskRunStore()
    reporter = TaskRunReporter(task_store, run_id="run-existing")
    service = DocumentIngestionService(
        upload_store=upload_store,
        document_store=FakeDocumentStore(),
        parser=DocumentParser(),
        chunking_service=ChunkingService(max_child_tokens=120, target_parent_tokens=240),
        embedding_client=FakeEmbedding(),
        vector_index=FakeVectorIndex(),
        task_run_store=task_store,
    )

    documents = service.ingest_batch("batch-1", task_reporter=reporter)

    assert len(documents) == 1
    assert task_store.create_run_calls == []
    assert {stage.task_run_id for stage in task_store.stages} == {"run-existing"}
    assert any(event.event_type == "qdrant_upsert" for event in task_store.events)
