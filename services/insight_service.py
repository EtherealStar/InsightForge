"""Insight claim service."""
from __future__ import annotations

from enum import Enum
from typing import Any

from core.protocols import (
    CompetitorStoreProtocol,
    DocumentStoreProtocol,
    InsightStoreProtocol,
    IntelStoreProtocol,
)
from models.evidence import EvidenceOwnerType, EvidenceRef, EvidenceType
from models.insight import ClaimStatus, ClaimType, InsightClaim


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


class InsightService:
    """Business rules for claims and claim evidence."""

    def __init__(
        self,
        insight_store: InsightStoreProtocol,
        intel_store: IntelStoreProtocol,
        competitor_store: CompetitorStoreProtocol,
        document_store: DocumentStoreProtocol,
    ):
        self.insight_store = insight_store
        self.intel_store = intel_store
        self.competitor_store = competitor_store
        self.document_store = document_store

    def create_claim(self, data: dict, *, created_by: str = "user") -> InsightClaim:
        fact_ids = [str(v) for v in data.get("fact_ids", [])]
        competitor_ids = [int(v) for v in data.get("competitor_ids", [])]
        evidence_data = list(data.get("evidence") or data.get("evidence_refs") or [])
        requested_status = _enum_value(data.get("status", ClaimStatus.DRAFT))

        self._validate_competitors(competitor_ids)
        self._validate_facts(fact_ids)
        if requested_status == ClaimStatus.ACTIVE.value and not fact_ids and not evidence_data:
            raise ValueError("active InsightClaim requires at least one fact or evidence")

        claim = InsightClaim(
            id=data.get("id") or data.get("claim_id") or InsightClaim.__dataclass_fields__["id"].default_factory(),
            claim_text=str(data.get("claim_text", "")).strip(),
            claim_type=data.get("claim_type", ClaimType.FINDING),
            dimension=str(data.get("dimension", "general")),
            competitor_ids=competitor_ids,
            product_ids=[int(v) for v in data.get("product_ids", [])],
            fact_ids=fact_ids,
            confidence_score=_safe_float(data.get("confidence_score")),
            limitations=str(data.get("limitations", "")),
            status=ClaimStatus.DRAFT.value
            if requested_status == ClaimStatus.ACTIVE.value
            else requested_status,
            created_by=created_by,
        )
        if not claim.claim_text:
            raise ValueError("InsightClaim requires claim_text")

        saved = self.insight_store.save_claim(claim)
        for evidence in evidence_data:
            self.attach_evidence(saved.id, evidence)
        if requested_status == ClaimStatus.ACTIVE.value:
            validation = self.validate_claim_evidence(saved.id)
            if not validation["valid"]:
                raise ValueError("; ".join(validation["errors"]))
            saved = self.insight_store.update_claim_status(saved.id, ClaimStatus.ACTIVE.value)
        return saved

    def get_claim_detail(self, claim_id: str) -> dict | None:
        claim = self.insight_store.get_claim(claim_id)
        return self._claim_to_dict(claim) if claim else None

    def update_claim(
        self,
        claim_id: str,
        data: dict,
        *,
        updated_by: str = "user",
    ) -> InsightClaim | None:
        current = self.insight_store.get_claim(claim_id)
        if not current:
            return None
        merged = {
            "id": current.id,
            "claim_text": data.get("claim_text", current.claim_text),
            "claim_type": data.get("claim_type", current.claim_type),
            "dimension": data.get("dimension", current.dimension),
            "competitor_ids": data.get("competitor_ids", current.competitor_ids),
            "product_ids": data.get("product_ids", current.product_ids),
            "fact_ids": data.get("fact_ids", current.fact_ids),
            "confidence_score": data.get("confidence_score", current.confidence_score),
            "limitations": data.get("limitations", current.limitations),
            "status": data.get("status", current.status),
            "evidence": data.get("evidence") or data.get("evidence_refs") or [],
        }
        return self.create_claim(merged, created_by=updated_by)

    def list_claims(
        self,
        filters: dict[str, Any],
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        return [
            self._claim_to_dict(claim)
            for claim in self.insight_store.list_claims(filters, limit=limit, offset=offset)
        ]

    def build_claims_from_facts(
        self,
        filters: dict[str, Any],
        *,
        max_claims: int = 10,
    ) -> list[InsightClaim]:
        facts = self.intel_store.list_facts(filters, limit=max_claims)
        claims: list[InsightClaim] = []
        for fact in facts:
            claim = self.create_claim(
                {
                    "claim_text": fact.fact_text,
                    "claim_type": ClaimType.FINDING.value,
                    "dimension": _enum_value(fact.dimension),
                    "competitor_ids": fact.competitor_ids,
                    "product_ids": fact.product_ids,
                    "fact_ids": [fact.id],
                    "confidence_score": fact.confidence_score,
                    "status": ClaimStatus.DRAFT.value,
                },
                created_by="system",
            )
            claims.append(claim)
        return claims

    def validate_claim_evidence(self, claim_id: str) -> dict:
        claim = self.insight_store.get_claim(claim_id)
        if not claim:
            return {"valid": False, "errors": [f"InsightClaim not found: {claim_id}"]}
        errors: list[str] = []
        if not claim.fact_ids and not claim.evidence_refs:
            errors.append("claim requires at least one fact or evidence")
        for competitor_id in claim.competitor_ids:
            if self.competitor_store.get_competitor(competitor_id) is None:
                errors.append(f"competitor not found: {competitor_id}")
        for evidence in claim.evidence_refs:
            parent_chunk_id = evidence.get("parent_chunk_id")
            url = evidence.get("url")
            if parent_chunk_id:
                if not self.document_store.get_parent_chunks_by_ids([parent_chunk_id]):
                    errors.append(f"evidence parent chunk not found: {parent_chunk_id}")
            elif not url:
                errors.append("evidence requires parent_chunk_id or url")
        return {"valid": not errors, "errors": errors}

    def attach_evidence(self, claim_id: str, evidence_data: dict) -> EvidenceRef:
        if self.insight_store.get_claim(claim_id) is None:
            raise ValueError(f"InsightClaim not found: {claim_id}")
        evidence = EvidenceRef(
            owner_type=EvidenceOwnerType.INSIGHT_CLAIM,
            owner_id=claim_id,
            source_document_id=evidence_data.get("source_document_id"),
            parent_chunk_id=evidence_data.get("parent_chunk_id"),
            url=evidence_data.get("url", ""),
            title=evidence_data.get("title", ""),
            snippet=evidence_data.get("snippet", ""),
            quote_hash=evidence_data.get("quote_hash", ""),
            evidence_type=evidence_data.get("evidence_type", EvidenceType.SOURCE_CHUNK),
            relevance_score=_safe_float(evidence_data.get("relevance_score"), 1.0),
        )
        self._validate_evidence(evidence)
        return self.insight_store.attach_evidence(claim_id, evidence)

    def _validate_competitors(self, competitor_ids: list[int]) -> None:
        for competitor_id in competitor_ids:
            if self.competitor_store.get_competitor(competitor_id) is None:
                raise ValueError(f"Competitor not found: {competitor_id}")

    def _validate_facts(self, fact_ids: list[str]) -> None:
        for fact_id in fact_ids:
            if self.intel_store.get_fact(fact_id) is None:
                raise ValueError(f"IntelFact not found: {fact_id}")

    def _validate_evidence(self, evidence: EvidenceRef) -> None:
        if evidence.parent_chunk_id:
            chunks = self.document_store.get_parent_chunks_by_ids([evidence.parent_chunk_id])
            if not chunks:
                raise ValueError(f"Parent chunk not found: {evidence.parent_chunk_id}")
            if evidence.source_document_id and chunks[0].document_id != evidence.source_document_id:
                raise ValueError("Evidence parent_chunk_id does not match source_document_id")
        elif not evidence.url:
            raise ValueError("Evidence requires parent_chunk_id or url")

    @staticmethod
    def _claim_to_dict(claim: InsightClaim) -> dict:
        return {
            "id": claim.id,
            "claim_text": claim.claim_text,
            "claim_type": _enum_value(claim.claim_type),
            "dimension": claim.dimension,
            "competitor_ids": claim.competitor_ids,
            "product_ids": claim.product_ids,
            "fact_ids": claim.fact_ids,
            "confidence_score": claim.confidence_score,
            "limitations": claim.limitations,
            "status": _enum_value(claim.status),
            "created_by": claim.created_by,
            "created_at": claim.created_at.isoformat() if claim.created_at else None,
            "updated_at": claim.updated_at.isoformat() if claim.updated_at else None,
            "evidence_refs": claim.evidence_refs,
        }
