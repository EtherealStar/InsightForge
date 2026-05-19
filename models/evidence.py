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


@dataclass
class EvidenceRef:
    owner_type: EvidenceOwnerType | str
    owner_id: str
    source_document_id: str | None = None
    parent_chunk_id: str | None = None
    url: str = ""
    title: str = ""
    snippet: str = ""
    quote_hash: str = ""
    evidence_type: EvidenceType | str = EvidenceType.SOURCE_CHUNK
    relevance_score: float = 0.0
    id: str = field(default_factory=new_evidence_id)
    created_at: datetime | None = None
