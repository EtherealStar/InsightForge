"""Structured intel fact domain models — target contract (Milestone 2).

This module defines the three-layer core types:

  * ``IntelFact`` — atomic reality proposition with discrete lifecycle /
    verification states, never with business score.
  * ``FactEvidenceLink`` — relation between fact and immutable Evidence
    Reference, carries ``stance``.
  * ``IntelFactCandidate`` / ``FactResolution`` — pure data feeding the
    conservative fact-resolution pipeline.

The legacy dataclasses (``EvidenceRef`` with ``owner_type/owner_id``,
``FactKind`` / ``IntelDimension``, importance/confidence score fields)
live in :mod:`models.evidence` and a separate ``IntelFactLegacy`` alias
in :mod:`models.intel_compat` (created on demand) so existing Service /
Store / API / Agent callers can keep compiling during cut-over. They
will be removed in Milestone 7.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


def new_fact_id() -> str:
    return str(uuid4())


class FactType(str, Enum):
    PRODUCT = "product"
    COMMERCIAL = "commercial"
    CORPORATE = "corporate"
    ECOSYSTEM = "ecosystem"
    CUSTOMER_MARKET = "customer_market"
    RISK = "risk"
    GENERAL = "general"


class FactLifecycleStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"
    REJECTED = "rejected"


class VerificationStatus(str, Enum):
    SINGLE_SOURCE = "single_source"
    SELF_REPORTED = "self_reported"
    CORROBORATED = "corroborated"
    DISPUTED = "disputed"


class TimePrecision(str, Enum):
    DAY = "day"
    MONTH = "month"
    QUARTER = "quarter"
    UNKNOWN = "unknown"


class FactEntityRole(str, Enum):
    SUBJECT = "subject"
    COUNTERPART = "counterpart"
    MENTIONED = "mentioned"


class LinkReviewStatus(str, Enum):
    CONFIRMED = "confirmed"
    NEEDS_REVIEW = "needs_review"


@dataclass
class IntelFactCompetitorLink:
    fact_id: str
    competitor_id: int
    role: FactEntityRole | str = FactEntityRole.SUBJECT
    review_status: LinkReviewStatus | str = LinkReviewStatus.CONFIRMED
    created_at: datetime | None = None


@dataclass
class IntelFactProductLink:
    fact_id: str
    product_id: int
    role: FactEntityRole | str = FactEntityRole.SUBJECT
    review_status: LinkReviewStatus | str = LinkReviewStatus.CONFIRMED
    created_at: datetime | None = None


@dataclass
class FactEvidenceLink:
    fact_id: str
    evidence_ref_id: str
    stance: str = "supports"
    created_at: datetime | None = None


@dataclass
class IntelFact:
    id: str = field(default_factory=new_fact_id)
    fact_type: FactType | str = FactType.GENERAL
    fact_text: str = ""
    normalized_data: dict[str, Any] | None = None
    occurred_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    time_precision: TimePrecision | str | None = None
    candidate_key: str | None = None
    lifecycle_status: FactLifecycleStatus | str | None = None
    verification_status: VerificationStatus | str | None = None
    status_reason: str = ""
    supersedes_fact_id: str | None = None
    created_by: str = "system"
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class IntelFactCandidate:
    """A candidate fact produced by the structured extraction pipeline.

    ``candidate_key`` is only for recall. ``key_qualifiers`` are the
    critical limiting facts (price, currency, version, market, billing
    period, time bucket) the conservative resolver compares across
    candidates before deciding same/different/uncertain.
    """
    candidate_key: str
    fact_type: FactType | str
    fact_text: str
    normalized_data: dict[str, Any] | None
    occurred_at: datetime | None
    valid_from: datetime | None
    valid_to: datetime | None
    time_precision: TimePrecision | str | None
    subject_competitor_ids: list[int] = field(default_factory=list)
    subject_product_ids: list[int] = field(default_factory=list)
    key_qualifiers: dict[str, Any] = field(default_factory=dict)
    evidence_ref_id: str | None = None


class FactResolutionOutcome(str, Enum):
    SAME = "same"
    DIFFERENT = "different"
    UNCERTAIN = "uncertain"


@dataclass
class FactResolution:
    outcome: FactResolutionOutcome
    matched_fact_id: str | None = None
    reason: str = ""