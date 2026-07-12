"""Insight Claim domain model — target contract (Milestone 2).

Insight Claim is an analytical conclusion built from Intel Facts. It is
indirectly connected to Evidence References via ``claim_facts`` →
``fact_evidence``. There is no direct evidence association, no JSON ID
arrays and no business score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


def new_claim_id() -> str:
    return str(uuid4())


class ClaimMaturity(str, Enum):
    DRAFT = "draft"
    HYPOTHESIS = "hypothesis"
    SUPPORTED = "supported"
    NEEDS_REVIEW = "needs_review"
    DISPUTED = "disputed"
    SUPERSEDED = "superseded"


class ClaimStance(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXTUAL = "contextual"


@dataclass
class ClaimFactLink:
    claim_id: str
    fact_id: str
    stance: ClaimStance | str = ClaimStance.SUPPORTS
    created_at: datetime | None = None


@dataclass
class InsightClaim:
    id: str = field(default_factory=new_claim_id)
    claim_text: str = ""
    tags: list[str] = field(default_factory=list)
    limitations: str = ""
    scope: dict[str, Any] | None = None
    maturity: ClaimMaturity | str | None = None
    status_reason: str = ""
    approved_by: str | None = None
    approved_at: datetime | None = None
    supersedes_claim_id: str | None = None
    created_by: str = "system"
    created_at: datetime | None = None
    updated_at: datetime | None = None