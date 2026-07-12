"""Evidence reference domain model."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


def new_evidence_id() -> str:
    return str(uuid4())


class EvidenceOwnerType(str, Enum):
    INTEL_FACT = "intel_fact"
    INSIGHT_CLAIM = "insight_claim"


class EvidenceType(str, Enum):
    SOURCE_CHUNK = "source_chunk"
    URL = "url"
    MANUAL = "manual"
    SEARCH_RESULT = "search_result"


class EvidenceRole(str, Enum):
    PRIMARY = "primary"
    INDEPENDENT = "independent"
    INTERESTED_CLAIM = "interested_claim"
    COMMUNITY_REPORT = "community_report"
    AGGREGATOR = "aggregator"
    UNKNOWN = "unknown"


class EvidenceStance(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


@dataclass
class EvidenceRef:
    owner_type: EvidenceOwnerType | str
    owner_id: str
    source_document_id: str | None = None
    document_version_id: str | None = None
    source_occurrence_id: str | None = None
    parent_chunk_id: str | None = None
    url: str = ""
    title: str = ""
    snippet: str = ""
    quote_hash: str = ""
    evidence_type: EvidenceType | str = EvidenceType.SOURCE_CHUNK
    relevance_score: float = 0.0
    role: EvidenceRole | str = EvidenceRole.UNKNOWN
    stance: EvidenceStance | str = EvidenceStance.SUPPORTS
    source_tier: str = "unknown"
    source_kind: str = "other"
    role_overridden: bool = False
    override_reason: str = ""
    override_actor: str = ""
    id: str = field(default_factory=new_evidence_id)
    created_at: datetime | None = None
