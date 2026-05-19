"""Insight claim domain model."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4
from typing import Any


def new_claim_id() -> str:
    return str(uuid4())


class ClaimType(str, Enum):
    TREND = "trend"
    COMPARISON = "comparison"
    RISK = "risk"
    OPPORTUNITY = "opportunity"
    FINDING = "finding"
    HYPOTHESIS = "hypothesis"


class ClaimStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    REJECTED = "rejected"
    ARCHIVED = "archived"


@dataclass
class InsightClaim:
    claim_text: str
    claim_type: ClaimType | str = ClaimType.FINDING
    dimension: str = "general"
    competitor_ids: list[int] = field(default_factory=list)
    product_ids: list[int] = field(default_factory=list)
    fact_ids: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    limitations: str = ""
    status: ClaimStatus | str = ClaimStatus.DRAFT
    created_by: str = "system"
    id: str = field(default_factory=new_claim_id)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
