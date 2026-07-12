"""稳定文档簇、来源实例和版本模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class DedupDecision(str, Enum):
    NEW_CLUSTER = "new_cluster"
    DUPLICATE = "duplicate"
    REVIEW_REQUIRED = "review_required"
    QUARANTINED = "quarantined"
    UNCHANGED = "unchanged"
    CANONICAL_PROMOTED = "canonical_promoted"


@dataclass(frozen=True)
class SimHashFingerprint:
    value: int
    high_bands: tuple[int, ...]
    gray_bands: tuple[int, ...]
    algorithm_version: str = "simhash-v1"


@dataclass
class DocumentCluster:
    document_id: str = field(default_factory=lambda: str(uuid4()))
    active_version_id: str | None = None
    created_at: datetime | None = None


@dataclass
class SourceOccurrence:
    document_id: str
    url: str
    normalized_url: str
    title: str
    content_hash: str
    simhash: SimHashFingerprint
    shingles: tuple[str, ...] = ()
    content_length: int = 0
    source_profile_revision_id: str | None = None
    source_tier: str = "unknown"
    source_kind: str = "other"
    id: str = field(default_factory=lambda: str(uuid4()))
    observed_at: datetime | None = None


@dataclass(frozen=True)
class DedupCommitResult:
    """权威归簇结果；调用方只能依据该结果决定是否构建派生数据。"""

    occurrence: SourceOccurrence
    decision: DedupDecision
    created_cluster: bool = False
    requires_build: bool = False


@dataclass
class DocumentVersion:
    document_id: str
    version: int
    content: str
    content_hash: str
    status: str = "building"
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime | None = None


@dataclass
class DuplicateCandidate:
    left_occurrence_id: str
    right_occurrence_id: str
    hamming_distance: int
    shingle_jaccard: float
    shingle_containment: float
    decision: DedupDecision = DedupDecision.REVIEW_REQUIRED
    reason: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
