"""多来源证据的确定性验证规则。"""
from __future__ import annotations

import hashlib
import re

from models.evidence import EvidenceRef, EvidenceRole, EvidenceStance
from models.intel import IntelFact, VerificationStatus


class EvidenceVerificationService:
    @staticmethod
    def assertion_key(data: dict) -> str:
        parts = [data.get("subject", ""), data.get("fact_type", "general"), data.get("predicate", ""), data.get("object", ""), data.get("event_date", "")]
        normalized = "|".join(re.sub(r"\s+", " ", str(value)).strip().casefold() for value in parts)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def derive_status(self, fact: IntelFact, evidence: list[dict | EvidenceRef]) -> tuple[VerificationStatus, str]:
        values = [item if isinstance(item, dict) else vars(item) for item in evidence]
        independent = [
            item for item in values
            if self._value(item.get("role")) == EvidenceRole.INDEPENDENT.value
            and str(item.get("source_tier", "unknown")).upper() in {"A", "B"}
        ]
        # 同一簇中的转载只能计作一个独立来源。
        independent_clusters = {
            item.get("document_cluster_id") or item.get("source_document_id")
            for item in independent
            if item.get("document_cluster_id") or item.get("source_document_id")
        }
        contradictory = any(
            self._value(item.get("stance") or item.get("relation"))
            == EvidenceStance.CONTRADICTS.value
            for item in values
        )
        if contradictory:
            return VerificationStatus.DISPUTED, "存在明确反证"
        if len(independent_clusters) >= 2:
            return VerificationStatus.CORROBORATED, "两个独立文档簇提供合格证据"
        if any(
            self._value(item.get("role"))
            in {EvidenceRole.PRIMARY.value, EvidenceRole.INTERESTED_CLAIM.value}
            for item in values
        ):
            return VerificationStatus.SELF_REPORTED, "证据主要来自主体自述"
        return VerificationStatus.UNVERIFIED, "尚无足够独立证据"

    @staticmethod
    def _value(value):
        return value.value if hasattr(value, "value") else value
