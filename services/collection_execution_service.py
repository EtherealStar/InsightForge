"""Fetch、artifact、normalize 和 accepted-only ingest 的阶段编排。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from models.collection import (
    ArtifactStatus,
    NormalizationOutcome,
    NormalizerRules,
    RawFetchArtifact,
    SourceFetchPolicy,
)


class CollectionExecutionService:
    def __init__(self, candidate_store, artifact_store, blob_store, normalized_store, normalization_service):
        self.candidates = candidate_store
        self.artifacts = artifact_store
        self.blobs = blob_store
        self.normalized = normalized_store
        self.normalizer = normalization_service

    async def fetch_candidate(self, candidate_id: str, source_task_id: str, engine, policy: SourceFetchPolicy) -> RawFetchArtifact:
        candidate = self.candidates.get_candidate(candidate_id)
        if candidate is None:
            raise KeyError(f"fetch candidate 不存在: {candidate_id}")
        result = await engine.fetch(candidate, policy)
        body_hash = sha256(result.body).hexdigest() if result.body is not None else None
        artifact = RawFetchArtifact(
            candidate.id, source_task_id, result.request_url, result.final_url, result.method, result.status,
            result.http_status, result.headers.get("content-type"), body_hash, datetime.now(UTC),
            headers=result.headers, expires_at=datetime.now(UTC) + timedelta(hours=24), reason_code=result.reason_code,
        )
        if result.body is not None:
            reusable = self.artifacts.find_by_body_hash(body_hash)
            artifact.blob_path = next((item.blob_path for item in reusable if item.blob_path), None)
            if artifact.blob_path is None:
                artifact.blob_path = self.blobs.put(artifact.id, result.body)
        return self.artifacts.save_artifact(artifact)

    def normalize_artifact(self, artifact: RawFetchArtifact, rules: NormalizerRules):
        existing = self.normalized.find_version(artifact.id, rules.version)
        if existing:
            return existing
        if not artifact.blob_path:
            raise ValueError("artifact 没有可重放 body")
        document = self.normalizer.normalize(artifact, self.blobs.get(artifact.blob_path), rules)
        return self.normalized.save_document(document)

    @staticmethod
    def should_ingest(document, source_profile=None) -> bool:
        # 非 accepted 结果不能进入全文索引、向量库或事实抽取。
        if document.outcome is not NormalizationOutcome.ACCEPTED:
            return False
        return source_profile is not None and source_profile.admission == "admit"
