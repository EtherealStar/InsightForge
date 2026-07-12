"""将 accepted Normalized Document 接入治理、版本、索引与向量化边界。"""
from __future__ import annotations

from dataclasses import dataclass

from models.collection import NormalizationOutcome
from models.document import SourceDocument
from models.document_governance import DedupDecision, SourceOccurrence
from services.document_fingerprint_service import fingerprint


@dataclass(frozen=True)
class NormalizedIngestionResult:
    normalized_document_id: str
    document_id: str
    document_version_id: str | None
    points: int
    status: str


class NormalizedIngestionService:
    def __init__(
        self,
        normalized_store,
        artifact_store,
        candidate_store,
        source_profile_store,
        clustering_service,
        version_service,
        document_store,
        chunking_service,
        embedding_client,
        vector_index,
    ):
        self.normalized_store = normalized_store
        self.artifact_store = artifact_store
        self.candidate_store = candidate_store
        self.source_profile_store = source_profile_store
        self.clustering_service = clustering_service
        self.version_service = version_service
        self.document_store = document_store
        self.chunking_service = chunking_service
        self.embedding_client = embedding_client
        self.vector_index = vector_index

    def ingest(self, normalized_document_id: str) -> NormalizedIngestionResult:
        normalized = self.normalized_store.get_document(normalized_document_id)
        if normalized is None:
            raise KeyError(f"normalized document 不存在: {normalized_document_id}")
        if normalized.outcome is not NormalizationOutcome.ACCEPTED:
            raise ValueError("只有 accepted normalized document 可以进入 ingest")

        artifact = self.artifact_store.get_artifact(normalized.artifact_id)
        candidate = self.candidate_store.get_candidate(artifact.candidate_id) if artifact else None
        profile = self.source_profile_store.get_profile(candidate.source_profile_id) if candidate else None
        if artifact is None or candidate is None or profile is None or profile.admission != "admit":
            raise ValueError("artifact、candidate 或受治理来源档案缺失，禁止 ingest")

        # Content Block 是证据权威正文，进入知识库前不得生成式改写。
        content = "\n\n".join(block.text for block in normalized.blocks).strip()
        content_hash, simhash, shingles = fingerprint(content)
        occurrence = SourceOccurrence(
            document_id="",
            url=artifact.final_url,
            normalized_url=candidate.normalized_url,
            title=normalized.title or candidate.metadata.get("title") or "Untitled",
            content_hash=content_hash,
            simhash=simhash,
            shingles=tuple(sorted(shingles)),
            content_length=len(content),
            source_profile_revision_id=profile.revision_id,
            source_tier=profile.tier.value,
            source_kind=profile.source_kind.value,
        )
        committed = self.clustering_service.commit(occurrence)
        if not committed.requires_build and committed.decision not in {
            DedupDecision.NEW_CLUSTER,
            DedupDecision.CANONICAL_PROMOTED,
        }:
            return NormalizedIngestionResult(
                normalized.id, committed.occurrence.document_id, None, 0, committed.decision.value
            )

        document_id = committed.occurrence.document_id
        version = self.version_service.begin(document_id, content, content_hash)
        document = SourceDocument(
            document_id=document_id,
            title=occurrence.title,
            content=content,
            source_type="collection",
            document_type="article",
            url=artifact.final_url,
            canonical_url=candidate.canonical_url or candidate.normalized_url,
            content_hash=content_hash,
            metadata={
                "normalized_document_id": normalized.id,
                "normalizer_version": normalized.normalizer_version,
                "artifact_id": artifact.id,
                "source_occurrence_id": committed.occurrence.id,
                "document_version_id": version.id,
                "semantic_blocks": [
                    {
                        "type": block.block_type,
                        "text": block.text,
                        "heading_path": [normalized.title] if normalized.title else [],
                        "source_locator": block.source_locator,
                    }
                    for block in normalized.blocks
                ],
            },
            parse_status="parsed",
        )
        try:
            self.document_store.save_document(document)
            children, parents = self.chunking_service.chunk_document(document)
            if parents:
                saved = self.document_store.save_parent_chunks(parents)
                if saved != len(parents):
                    raise RuntimeError(f"父 chunk 写入不完整: {saved}/{len(parents)}")
            embeddings = self.embedding_client.embed([child.content for child in children])
            if len(embeddings) != len(children):
                raise RuntimeError(f"Embedding 数量不匹配: {len(embeddings)}/{len(children)}")
            points = self.vector_index.upsert_child_chunks(children, embeddings) if children else 0
            if points != len(children):
                raise RuntimeError(f"向量写入不完整: {points}/{len(children)}")
            if children:
                self.document_store.mark_points_vectorized(children)
            self.document_store.update_parse_status(document_id, "vectorized")
            self.version_service.activate(version)
            return NormalizedIngestionResult(normalized.id, document_id, version.id, points, "vectorized")
        except Exception as exc:
            self.version_service.fail(version)
            self.document_store.update_parse_status(document_id, "failed", {"message": str(exc)})
            raise
