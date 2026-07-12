from datetime import UTC, datetime

import pytest

from models.collection import ContentBlock, FetchCandidate, NormalizationOutcome, NormalizedDocument, RawFetchArtifact, FetchMethod, ArtifactStatus
from models.document import ChildChunkPoint, ParentDocumentChunk
from models.document_governance import DedupCommitResult, DedupDecision, DocumentVersion
from models.source_governance import SourceProfile, SourceTier
from services.normalized_ingestion_service import NormalizedIngestionService


class LookupStore:
    def __init__(self, value):
        self.value = value

    def get_document(self, _): return self.value
    def get_artifact(self, _): return self.value
    def get_candidate(self, _): return self.value
    def get_profile(self, _): return self.value


class Clustering:
    def commit(self, occurrence):
        occurrence.document_id = "document-1"
        return DedupCommitResult(occurrence, DedupDecision.NEW_CLUSTER, True, True)


class Versions:
    def __init__(self): self.activated = None
    def begin(self, document_id, content, content_hash): return DocumentVersion(document_id, 1, content, content_hash, id="version-1")
    def activate(self, version): self.activated = version; version.status = "active"; return version
    def fail(self, version): version.status = "failed"; return version


class Documents:
    def __init__(self): self.saved = None; self.parents = []
    def save_document(self, document): self.saved = document; return document
    def save_parent_chunks(self, parents): self.parents = parents; return len(parents)
    def mark_points_vectorized(self, points): self.points = points
    def mark_points_vector_failed(self, point_ids, error): pass
    def update_parse_status(self, document_id, status, error=None): self.status = status


class Chunker:
    def chunk_document(self, document):
        child = ChildChunkPoint("point-1", document.document_id, "parent-1", document.content, 10, 0)
        parent = ParentDocumentChunk("parent-1", document.document_id, document.content, 10, ["point-1"])
        return [child], [parent]


class Embedder:
    def embed(self, texts): return [[0.1, 0.2] for _ in texts]


class VectorIndex:
    def upsert_child_chunks(self, chunks, embeddings): self.chunks = chunks; return len(chunks)


def build_service(outcome=NormalizationOutcome.ACCEPTED):
    normalized = NormalizedDocument(
        "artifact-1", "v1", outcome,
        [ContentBlock("block-1", "p", "Verbatim accepted body.", 0, "block:0")], [],
        title="Release", id="normalized-1",
    )
    artifact = RawFetchArtifact(
        "candidate-1", "task-1", "https://example.com/post", "https://example.com/post",
        FetchMethod.HTTP, ArtifactStatus.FETCHED, 200, "text/html", "hash", datetime.now(UTC), id="artifact-1",
    )
    candidate = FetchCandidate("profile-1", "https://example.com/post", datetime.now(UTC), "cursor", id="candidate-1")
    profile = SourceProfile("example.com", tier=SourceTier.A, id="profile-1", revision_id="revision-1")
    documents = Documents()
    versions = Versions()
    service = NormalizedIngestionService(
        LookupStore(normalized), LookupStore(artifact), LookupStore(candidate), LookupStore(profile),
        Clustering(), versions, documents, Chunker(), Embedder(), VectorIndex(),
    )
    return service, documents, versions


def test_accepted_normalized_document_enters_governed_vectorized_document_version():
    service, documents, versions = build_service()

    result = service.ingest("normalized-1")

    assert result.document_id == "document-1"
    assert result.document_version_id == "version-1"
    assert result.points == 1
    assert documents.saved.content == "Verbatim accepted body."
    assert documents.saved.metadata["normalized_document_id"] == "normalized-1"
    assert documents.status == "vectorized"
    assert versions.activated.id == "version-1"


def test_non_accepted_normalized_document_cannot_enter_ingest():
    service, _, _ = build_service(NormalizationOutcome.REVIEW_REQUIRED)
    with pytest.raises(ValueError, match="accepted"):
        service.ingest("normalized-1")
