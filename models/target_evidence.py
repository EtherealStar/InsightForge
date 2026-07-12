"""Evidence Reference domain model — target contract (Milestone 2).

Evidence Reference is an immutable anchor to a Document Version's character
range. It carries no owner, no role, no relevance score. The relation to a
fact (``stance``) lives in ``FactEvidenceLink``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


def new_evidence_id() -> str:
    return str(uuid4())


class EvidenceStance(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXTUAL = "contextual"


@dataclass(frozen=True)
class CharRangeLocator:
    """0-based, end-exclusive Unicode character range.

    ``start`` and ``end`` are Python string indices into the Document
    Version's ``content``; the slice ``content[start:end]`` must equal
    ``quoted_text`` byte-for-byte.
    """
    start: int
    end: int

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "char_range", "start": int(self.start), "end": int(self.end)}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CharRangeLocator":
        if not payload or payload.get("kind") != "char_range":
            raise ValueError(f"unsupported locator kind: {payload!r}")
        start = int(payload["start"])
        end = int(payload["end"])
        if start < 0 or end <= start:
            raise ValueError(f"invalid char range: {start}-{end}")
        return cls(start=start, end=end)


@dataclass
class EvidenceReference:
    id: str = field(default_factory=new_evidence_id)
    document_version_id: str = ""
    source_occurrence_id: str = ""
    quoted_text: str = ""
    quote_hash: str = ""
    locator: dict[str, Any] | None = None
    parent_chunk_id: str | None = None
    created_at: datetime | None = None