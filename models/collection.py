"""来源级采集与确定性清洗的纯数据领域模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from typing import Any
from uuid import uuid4


def utcnow() -> datetime:
    return datetime.now(UTC)


class CollectionRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


class SourceTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PAUSED = "paused"


class FetchMethod(str, Enum):
    HTTP = "http"
    BROWSER = "browser"


class ArtifactStatus(str, Enum):
    FETCHED = "fetched"
    NOT_MODIFIED = "not_modified"
    BLOCKED = "blocked"
    FAILED = "failed"


class CandidateStatus(str, Enum):
    DISCOVERED = "discovered"
    FETCHING = "fetching"
    FETCHED = "fetched"
    NORMALIZED = "normalized"
    ACCEPTED = "accepted"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"
    FAILED = "failed"
    UNCHANGED = "unchanged"


class NormalizationOutcome(str, Enum):
    ACCEPTED = "accepted"
    RETRY_RENDER = "retry_render"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


@dataclass
class SourceCursor:
    source_profile_id: str
    value: str
    etag: str | None = None
    last_modified: str | None = None
    next_due_at: datetime | None = None
    consecutive_unchanged: int = 0
    consecutive_failures: int = 0
    circuit_open_until: datetime | None = None
    updated_at: datetime = field(default_factory=utcnow)


@dataclass
class SourceFetchPolicy:
    render_required: bool = False
    strict_rate_limit: bool = False
    requests_per_minute: int = 30
    domain_concurrency: int = 2
    max_response_bytes: int = 20 * 1024 * 1024
    max_decompression_ratio: float = 100.0
    timeout_seconds: float = 30.0
    etag: str | None = None
    last_modified: str | None = None


@dataclass
class CollectionRun:
    status: CollectionRunStatus = CollectionRunStatus.PENDING
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class SourceFetchTask:
    collection_run_id: str
    source_profile_id: str
    status: SourceTaskStatus = SourceTaskStatus.PENDING
    attempt: int = 0
    error: dict[str, Any] | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    @property
    def idempotency_key(self) -> str:
        return f"{self.collection_run_id}:{self.source_profile_id}"


@dataclass
class FetchCandidate:
    source_profile_id: str
    normalized_url: str
    discovered_at: datetime
    discovery_cursor: str
    expected_media_type: str | None = None
    canonical_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    status: CandidateStatus = CandidateStatus.DISCOVERED
    id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def idempotency_key(self) -> str:
        raw = f"{self.source_profile_id}\0{self.normalized_url}\0{self.discovery_cursor}"
        return sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class DiscoveryResult:
    candidates: list[FetchCandidate]
    next_cursor: SourceCursor | None = None
    response_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class FetchResult:
    request_url: str
    final_url: str
    method: FetchMethod
    status: ArtifactStatus
    http_status: int | None
    headers: dict[str, str]
    body: bytes | None
    reason_code: str | None = None


@dataclass
class RawFetchArtifact:
    candidate_id: str
    source_task_id: str
    request_url: str
    final_url: str
    fetch_method: FetchMethod
    status: ArtifactStatus
    http_status: int | None
    content_type: str | None
    body_hash: str | None
    observed_at: datetime
    id: str = field(default_factory=lambda: str(uuid4()))
    blob_path: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    retained: bool = False
    retention_reason: str | None = None
    expires_at: datetime | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class ContentBlock:
    id: str
    block_type: str
    text: str
    ordinal: int
    source_locator: str


@dataclass(frozen=True)
class NormalizerRules:
    version: str
    minimum_text_length: int = 80
    maximum_link_density: float = 0.65
    content_selector: str | None = None


@dataclass
class NormalizedDocument:
    artifact_id: str
    normalizer_version: str
    outcome: NormalizationOutcome
    blocks: list[ContentBlock]
    reason_codes: list[str]
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=utcnow)

    @property
    def idempotency_key(self) -> str:
        return f"{self.artifact_id}:{self.normalizer_version}"
