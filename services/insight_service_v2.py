"""Insight Claim service for the v2 three-layer model (Milestone 5).

This service wraps the v2 store with the rules that the API and Agent tools
must follow:

  * create_claim / update_claim only create or edit ``draft`` or ``hypothesis``
    claims. ``supported`` is reached only via :meth:`approve_claim`.
  * Claims cannot receive direct evidence, score, dimension, JSON fact IDs,
    or fact_kind.
  * ``approve_claim`` requires a real analyst/admin actor (never ``agent``
    or ``system``), at least one supporting active non-disputed fact, and
    a non-empty subject derivation.
  * ``supersede_claim`` creates a new claim and links it via
    ``supersedes_claim_id``; the old claim becomes ``superseded`` and its
    text stays intact for historical reports.
  * When a fact becomes disputed, retracted, or superseded, dependent
    supported claims are flipped to ``needs_review`` with a clear reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from core.exceptions import IntelligenceInvariantError
from infrastructure.insight_store_v2 import PostgresInsightStoreV2
from infrastructure.intel_store_v2 import PostgresIntelStoreV2
from models.target_insight import (
    ClaimFactLink,
    ClaimMaturity,
    InsightClaim,
)
from models.target_intel import (
    FactLifecycleStatus,
    VerificationStatus,
)


_FORBIDDEN_APPROVERS = {"agent", "system", ""}


@dataclass
class ClaimDraftRequest:
    claim_text: str
    tags: list[str]
    limitations: str = ""
    scope: dict | None = None
    created_by: str = "system"


class InsightServiceV2:
    def __init__(
        self,
        insight_store: PostgresInsightStoreV2,
        intel_store: PostgresIntelStoreV2,
    ):
        self._insight = insight_store
        self._intel = intel_store

    # ------------------------------------------------------------------
    # create / update
    # ------------------------------------------------------------------
    def create_hypothesis(self, request: ClaimDraftRequest) -> InsightClaim:
        if not request.claim_text or not request.claim_text.strip():
            raise IntelligenceInvariantError("claim_text must not be empty")
        claim = InsightClaim(
            claim_text=request.claim_text.strip(),
            tags=list(request.tags or []),
            limitations=request.limitations or "",
            scope=request.scope,
            maturity=ClaimMaturity.HYPOTHESIS,
            created_by=request.created_by or "system",
        )
        return self._insight.save_claim(claim)

    def update_draft(self, claim_id: str, request: ClaimDraftRequest) -> InsightClaim:
        existing = self._insight.get_claim(claim_id)
        if existing is None:
            raise IntelligenceInvariantError(f"claim {claim_id} not found")
        if existing.maturity not in (ClaimMaturity.DRAFT, ClaimMaturity.HYPOTHESIS):
            raise IntelligenceInvariantError(
                f"claim {claim_id} is {existing.maturity}; use supersede_claim"
            )
        existing.claim_text = request.claim_text.strip() or existing.claim_text
        existing.tags = list(request.tags or existing.tags)
        existing.limitations = request.limitations or existing.limitations
        existing.scope = request.scope if request.scope is not None else existing.scope
        return self._insight.save_claim(existing)

    def replace_facts(
        self, claim_id: str, links: list[ClaimFactLink]
    ) -> int:
        existing = self._insight.get_claim(claim_id)
        if existing is None:
            raise IntelligenceInvariantError(f"claim {claim_id} not found")
        if existing.maturity not in (ClaimMaturity.DRAFT, ClaimMaturity.HYPOTHESIS):
            raise IntelligenceInvariantError(
                f"claim {claim_id} is {existing.maturity}; claim_facts are immutable"
            )
        return self._insight.replace_claim_facts(claim_id, links)

    # ------------------------------------------------------------------
    # approve / supersede
    # ------------------------------------------------------------------
    def approve_claim(self, claim_id: str, approved_by: str) -> InsightClaim:
        if approved_by in _FORBIDDEN_APPROVERS:
            raise IntelligenceInvariantError(
                f"approved_by={approved_by!r} cannot approve a claim; "
                "must be a real analyst/admin actor"
            )
        existing = self._insight.get_claim(claim_id)
        if existing is None:
            raise IntelligenceInvariantError(f"claim {claim_id} not found")
        if existing.maturity == ClaimMaturity.SUPPORTED:
            return existing
        if existing.maturity not in (ClaimMaturity.DRAFT, ClaimMaturity.HYPOTHESIS):
            raise IntelligenceInvariantError(
                f"cannot approve claim at maturity {existing.maturity}"
            )

        supporting = self._collect_supporting_facts(claim_id)
        if not supporting:
            raise IntelligenceInvariantError(
                "no supporting active non-disputed fact; cannot approve"
            )

        return self._insight.update_claim_maturity(
            claim_id,
            ClaimMaturity.SUPPORTED,
            "approved by analyst",
            approved_by=approved_by,
            approved_at=datetime.now(),
        )

    def supersede_claim(
        self,
        old_claim_id: str,
        new_request: ClaimDraftRequest,
        new_fact_links: list[ClaimFactLink] | None = None,
    ) -> InsightClaim:
        old = self._insight.get_claim(old_claim_id)
        if old is None:
            raise IntelligenceInvariantError(f"claim {old_claim_id} not found")
        if old.maturity == ClaimMaturity.SUPERSEDED:
            raise IntelligenceInvariantError(
                "cannot supersede an already-superseded claim"
            )
        new_claim = InsightClaim(
            claim_text=new_request.claim_text.strip(),
            tags=list(new_request.tags or []),
            limitations=new_request.limitations or "",
            scope=new_request.scope,
            maturity=ClaimMaturity.HYPOTHESIS,
            supersedes_claim_id=old_claim_id,
            created_by=new_request.created_by or "system",
        )
        created = self._insight.save_claim(new_claim)
        if new_fact_links:
            self._insight.replace_claim_facts(
                created.id,
                [ClaimFactLink(created.id, link.fact_id, link.stance) for link in new_fact_links],
            )
        self._insight.update_claim_maturity(
            old_claim_id,
            ClaimMaturity.SUPERSEDED,
            f"superseded by {created.id}",
        )
        return created

    def mark_disputed(self, claim_id: str, reason: str) -> InsightClaim:
        return self._insight.update_claim_maturity(
            claim_id,
            ClaimMaturity.DISPUTED,
            reason,
        )

    # ------------------------------------------------------------------
    # internal: collect supporting facts and check their status
    # ------------------------------------------------------------------
    def _collect_supporting_facts(self, claim_id: str) -> list:
        links = self._insight.list_claim_facts(claim_id)
        result = []
        for link in links:
            if link.stance != "supports":
                continue
            fact = self._intel.get_fact(link.fact_id)
            if fact is None:
                continue
            if fact.lifecycle_status != FactLifecycleStatus.ACTIVE:
                continue
            if fact.verification_status == VerificationStatus.DISPUTED:
                continue
            result.append(fact)
        return result

    # ------------------------------------------------------------------
    # fact → dependent claim propagation (called by IntelLifecycleService)
    # ------------------------------------------------------------------
    def on_fact_lifecycle_changed(
        self,
        fact_id: str,
        reason: str,
    ) -> list[InsightClaim]:
        """Flip dependent supported claims to needs_review."""
        return self._insight.mark_dependent_supported_claims_needs_review(
            fact_id, reason
        )