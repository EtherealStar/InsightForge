"""Structured intel fact domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from uuid import uuid4
from typing import Any


def new_fact_id() -> str:
    return str(uuid4())


class FactKind(str, Enum):
    FACT = "fact"
    EVENT = "event"
    SIGNAL = "signal"


class FactType(str, Enum):
    FEATURE_RELEASE = "feature_release"
    PRICING_CHANGE = "pricing_change"
    PARTNERSHIP = "partnership"
    HIRING = "hiring"
    FUNDING = "funding"
    CUSTOMER_CASE = "customer_case"
    SECURITY = "security"
    LEGAL = "legal"
    MARKET_SIGNAL = "market_signal"
    GENERAL = "general"


class IntelDimension(str, Enum):
    PRODUCT = "product"
    TECHNOLOGY = "technology"
    GO_TO_MARKET = "go_to_market"
    PRICING = "pricing"
    CUSTOMER = "customer"
    ECOSYSTEM = "ecosystem"
    RISK = "risk"
    FINANCIAL = "financial"
    TALENT = "talent"
    GENERAL = "general"


class FactStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    SELF_REPORTED = "self_reported"
    CORROBORATED = "corroborated"
    DISPUTED = "disputed"


@dataclass
class IntelFactCompetitorLink:
    fact_id: str
    competitor_id: int
    relation_type: str = "subject"
    confidence_score: float = 1.0
    created_at: datetime | None = None


@dataclass
class IntelFactProductLink:
    fact_id: str
    product_id: int
    relation_type: str = "subject"
    confidence_score: float = 1.0
    created_at: datetime | None = None


@dataclass
class IntelFact:
    fact_kind: FactKind | str = FactKind.FACT
    fact_type: FactType | str = FactType.GENERAL
    dimension: IntelDimension | str = IntelDimension.GENERAL
    subject: str = ""
    predicate: str = ""
    object: str = ""
    fact_text: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    event_date: date | None = None
    observed_at: datetime | None = None
    importance_score: float = 0.0
    confidence_score: float = 0.0
    extraction_method: str = "llm"
    extraction_version: str = ""
    assertion_key: str = ""
    verification_status: VerificationStatus | str = VerificationStatus.UNVERIFIED
    verification_reason: str = ""
    status: FactStatus | str = FactStatus.DRAFT
    created_by: str = "system"
    id: str = field(default_factory=new_fact_id)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    competitor_ids: list[int] = field(default_factory=list)
    product_ids: list[int] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
