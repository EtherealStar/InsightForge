"""来源治理领域模型：来源等级描述来源本身，不替代事实验证。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class SourceTier(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    UNKNOWN = "unknown"


class SourceKind(str, Enum):
    OFFICIAL = "official"
    NEWS = "news"
    COMMUNITY = "community"
    AGGREGATOR = "aggregator"
    RESEARCH = "research"
    OTHER = "other"


@dataclass
class SourceProfileRevision:
    profile_id: str
    tier: SourceTier
    source_kind: SourceKind
    reason: str
    actor: str
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime | None = None


@dataclass
class SourceProfile:
    domain: str
    tier: SourceTier = SourceTier.UNKNOWN
    source_kind: SourceKind = SourceKind.OTHER
    inherit_to_subdomains: bool = False
    id: str = field(default_factory=lambda: str(uuid4()))
    revision_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def admission(self) -> str:
        if self.tier in (SourceTier.A, SourceTier.B, SourceTier.C):
            return "admit"
        if self.tier is SourceTier.D:
            return "quarantine"
        return "pending_review"
