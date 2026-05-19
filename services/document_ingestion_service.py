"""Document ingestion orchestration for uploaded blobs."""
from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

import structlog

from core.protocols import (
    DocumentParserProtocol,
    DocumentStoreProtocol,
    EmbeddingClientProtocol,
    RedisStateStoreProtocol,
    TaskRunStoreProtocol,
    UploadStoreProtocol,
    VectorIndexProtocol,
)
from infrastructure.chunking_service import ChunkingService
from models.document import SourceDocument
from models.file_asset import DocumentBlob
from models.task_run import TaskStatus
from services.task_run_reporter import TaskRunReporter

logger = structlog.get_logger(__name__)


class DocumentIngestionService:
    """Parse uploaded blobs and index them into the document RAG stack."""

    def __init__(
        self,
        upload_store: UploadStoreProtocol,
        document_store: DocumentStoreProtocol,
        parser: DocumentParserProtocol,
        chunking_service: ChunkingService,
        embedding_client: EmbeddingClientProtocol,
        vector_index: VectorIndexProtocol,
        task_run_store: TaskRunStoreProtocol | None = None,
        redis_state_store: RedisStateStoreProtocol | None = None,
    ):
        self.upload_store = upload_store
        self.document_store = document_store
        self.parser = parser
        self.chunking_service = chunking_service
        self.embedding_client = embedding_client
        self.vector_index = vector_index
        self.task_run_store = task_run_store
        self.redis_state_store = redis_state_store

    def ingest_blob(
        self,
        blob: DocumentBlob,
        context: dict[str, Any] | None = None,
        task_reporter: TaskRunReporter | None = None,
    ) -> SourceDocument:
        context = context or {}
        lock_key = f"logos:lock:document_parse:{blob.id}"
        owner = str(uuid4())
        redis_healthy = bool(
            self.redis_state_store and self.redis_state_store.healthcheck()
        )
        if redis_healthy and self.redis_state_store:
            if not self.redis_state_store.acquire_lock(lock_key, owner, ttl_seconds=1800):
                raise RuntimeError(f"Blob is already being parsed: {blob.id}")

        stage = None
        owns_run = task_reporter is None and self.task_run_store is not None
        reporter = task_reporter
        if reporter is None:
            reporter = TaskRunReporter(self.task_run_store, self.redis_state_store)
        if owns_run and reporter:
            run = reporter.create_run(
                "document_ingestion",
                {"blob_id": blob.id, "upload_batch_id": blob.upload_batch_id},
                idempotency_key=f"blob:{blob.sha256}",
            )
            if run:
                reporter.start_run(run.id)
        if reporter:
            stage = reporter.start_stage("parse_documents", {"blob_id": blob.id})

        try:
            parsed = self.parser.parse(blob)
            document = self._to_source_document(blob, parsed, context)
            document = self.document_store.save_document(document)
            self.document_store.update_parse_status(document.document_id, "parsed")
            self.upload_store.update_blob_status(blob.id, "parsed")

            if reporter:
                reporter.finish_stage(
                    stage,
                    TaskStatus.SUCCEEDED.value,
                    {"document_id": document.document_id},
                )
                stage = reporter.start_stage(
                    "chunk_documents",
                    {"document_id": document.document_id},
                )

            children, parents = self.chunking_service.chunk_document(document)
            self.document_store.save_parent_chunks(parents)
            if children:
                self.document_store.update_parse_status(document.document_id, "chunked")

            if reporter:
                reporter.finish_stage(
                    stage,
                    TaskStatus.SUCCEEDED.value,
                    {"parents": len(parents), "children": len(children)},
                )
                stage = reporter.start_stage(
                    "vectorize_document",
                    {"document_id": document.document_id},
                )

            if children:
                vector_lock_key = f"logos:lock:vectorize:{document.document_id}"
                vector_owner = str(uuid4())
                vector_lock_acquired = False
                if redis_healthy and self.redis_state_store:
                    if not self.redis_state_store.acquire_lock(
                        vector_lock_key,
                        vector_owner,
                        ttl_seconds=3600,
                    ):
                        raise RuntimeError(
                            f"Document is already being vectorized: {document.document_id}"
                        )
                    vector_lock_acquired = True
                try:
                    embeddings = self.embedding_client.embed([child.content for child in children])
                    if len(embeddings) != len(children):
                        raise RuntimeError(
                            f"Embedding count mismatch: {len(embeddings)}/{len(children)}"
                        )
                    if reporter:
                        reporter.event(
                            "embed",
                            {"document_id": document.document_id, "children": len(children)},
                        )
                    upserted = self.vector_index.upsert_child_chunks(children, embeddings)
                    if reporter:
                        reporter.event(
                            "qdrant_upsert",
                            {"document_id": document.document_id, "points": upserted},
                        )
                    if upserted != len(children):
                        raise RuntimeError(
                            f"Qdrant point count mismatch: {upserted}/{len(children)}"
                        )
                    self.document_store.mark_points_vectorized(children)
                    self.document_store.update_parse_status(document.document_id, "vectorized")
                    if reporter:
                        reporter.event(
                            "mark_vectorized",
                            {"document_id": document.document_id, "points": len(children)},
                        )
                finally:
                    if vector_lock_acquired and self.redis_state_store:
                        self.redis_state_store.release_lock(vector_lock_key, vector_owner)

            if reporter:
                reporter.finish_stage(
                    stage,
                    TaskStatus.SUCCEEDED.value,
                    {"points": len(children)},
                )
                if owns_run:
                    reporter.finish_run(
                        TaskStatus.SUCCEEDED.value,
                        {"document_id": document.document_id, "points": len(children)},
                    )
            return document
        except Exception as e:
            error = {"message": str(e), "blob_id": blob.id}
            logger.warning("document_ingestion.failed", **error)
            self.upload_store.update_blob_status(blob.id, "failed", error)
            if "document" in locals():
                self.document_store.update_parse_status(document.document_id, "failed", error)
            if "children" in locals():
                self.document_store.mark_points_vector_failed(
                    [child.point_id for child in children],
                    error,
                )
            if reporter:
                reporter.finish_stage(stage, TaskStatus.FAILED.value, error=error)
                if owns_run:
                    reporter.finish_run(TaskStatus.FAILED.value, error=error)
            raise
        finally:
            if redis_healthy and self.redis_state_store:
                self.redis_state_store.release_lock(lock_key, owner)

    def ingest_batch(
        self,
        batch_id: str,
        context: dict[str, Any] | None = None,
        task_reporter: TaskRunReporter | None = None,
    ) -> list[SourceDocument]:
        reporter = task_reporter
        owns_run = reporter is None and self.task_run_store is not None
        if reporter is None:
            reporter = TaskRunReporter(self.task_run_store, self.redis_state_store)
        if owns_run and reporter:
            run = reporter.create_run(
                "upload_batch_ingestion",
                {"batch_id": batch_id, "context": context or {}},
                idempotency_key=f"upload_batch:{batch_id}",
            )
            if run:
                reporter.start_run(run.id)

        stage = reporter.start_stage("upload_batch", {"batch_id": batch_id}) if reporter else None
        documents: list[SourceDocument] = []
        errors: list[dict[str, Any]] = []
        for blob in self.upload_store.list_blobs(batch_id):
            if blob.status in {"rejected", "quarantined"}:
                if reporter:
                    reporter.event(
                        "blob_skipped",
                        {"blob_id": blob.id, "status": blob.status},
                        stage_id=stage.id if stage else None,
                    )
                continue
            try:
                documents.append(
                    self.ingest_blob(
                        blob,
                        context=context,
                        task_reporter=reporter,
                    )
                )
            except Exception as e:
                errors.append({"blob_id": blob.id, "message": str(e)})

        status = "succeeded"
        if errors and documents:
            status = "partial_failed"
        elif errors:
            status = "failed"
        self.upload_store.finish_batch(batch_id, status, {"errors": errors} if errors else None)
        self.last_batch_result = {
            "batch_id": batch_id,
            "batch_status": status,
            "documents": len(documents),
            "errors": errors,
        }
        if reporter:
            stage_status = (
                TaskStatus.SUCCEEDED.value
                if status == "succeeded"
                else TaskStatus.FAILED.value
            )
            reporter.finish_stage(
                stage,
                stage_status,
                {"documents": len(documents), "errors": errors, "batch_status": status},
                {"errors": errors} if errors and not documents else None,
            )
            if owns_run:
                run_status = (
                    TaskStatus.SUCCEEDED.value
                    if status in {"succeeded", "partial_failed"}
                    else TaskStatus.FAILED.value
                )
                reporter.finish_run(
                    run_status,
                    {"documents": len(documents), "errors": errors, "batch_status": status},
                    {"errors": errors} if status == "failed" else None,
                )
        return documents

    @staticmethod
    def _to_source_document(
        blob: DocumentBlob,
        parsed,
        context: dict[str, Any],
    ) -> SourceDocument:
        content_hash = hashlib.sha256(
            (parsed.content or "").encode("utf-8")
        ).hexdigest()
        metadata = {
            **parsed.metadata,
            "warnings": parsed.warnings,
            "upload_batch_id": blob.upload_batch_id,
            "blob_id": blob.id,
            "original_filename": blob.original_filename,
            **dict(context.get("metadata") or {}),
        }
        return SourceDocument(
            document_id=str(uuid4()),
            title=parsed.title,
            content=parsed.content,
            source_type="upload",
            document_type=context.get("document_type", "other"),
            language=context.get("language", ""),
            content_hash=content_hash,
            competitor_ids=list(context.get("competitor_ids") or []),
            product_ids=list(context.get("product_ids") or []),
            metadata=metadata,
            blob_id=blob.id,
            parse_status="pending",
        )
