"""V2 target Protocols for the three-layer structured intelligence model.

These are the target-shape contracts that ``PostgresIntelStoreV2``,
``PostgresInsightStoreV2`` and ``PostgresSourceProfileStoreV2`` implement.

They live alongside the legacy Protocols (which keep their wider
signature so existing Service / Store / API / Agent consumers continue
to compile) until Milestone 7 deletes the legacy adapter.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from models.target_evidence import EvidenceReference
from models.target_insight import ClaimFactLink, ClaimMaturity, InsightClaim
from models.target_intel import (
    FactEvidenceLink,
    FactLifecycleStatus,
    IntelFact,
    IntelFactCompetitorLink,
    IntelFactProductLink,
    VerificationStatus,
)
from models.source_governance import SourceProfile


@runtime_checkable
class IntelStoreV2Protocol(Protocol):
    """Target contract for Intel Fact and Fact ↔ Evidence / Competitor / Product."""

    # ---- fact lifecycle ----
    def save_fact(self, fact: IntelFact) -> IntelFact: ...
    def get_fact(self, fact_id: str) -> IntelFact | None: ...
    def list_facts(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IntelFact]: ...
    def find_fact_candidates(
        self, candidate_key: str, limit: int = 20
    ) -> list[IntelFact]: ...
    def update_fact_lifecycle(
        self,
        fact_id: str,
        lifecycle_status: FactLifecycleStatus | str,
        status_reason: str = "",
    ) -> IntelFact: ...
    def update_fact_verification(
        self,
        fact_id: str,
        verification_status: VerificationStatus | str | None,
        status_reason: str = "",
    ) -> IntelFact: ...

    # ---- evidence anchor ----
    def save_evidence_reference(
        self, evidence: EvidenceReference
    ) -> EvidenceReference: ...
    def get_evidence_reference(
        self, evidence_ref_id: str
    ) -> EvidenceReference | None: ...
    def find_evidence_by_anchor(
        self,
        document_version_id: str,
        source_occurrence_id: str,
        quote_hash: str,
    ) -> EvidenceReference | None: ...

    # ---- fact ↔ evidence ----
    def link_fact_evidence(self, link: FactEvidenceLink) -> FactEvidenceLink: ...
    def list_fact_evidence(self, fact_id: str) -> list[FactEvidenceLink]: ...
    def move_fact_evidence(
        self,
        source_fact_id: str,
        target_fact_id: str,
        evidence_ref_ids: list[str],
    ) -> int: ...
    def delete_fact_evidence(self, fact_id: str, evidence_ref_id: str) -> None: ...

    # ---- fact ↔ competitor / product ----
    def link_fact_to_competitor(
        self, link: IntelFactCompetitorLink
    ) -> IntelFactCompetitorLink: ...
    def unlink_fact_from_competitor(
        self,
        fact_id: str,
        competitor_id: int,
        role: str | None = None,
    ) -> None: ...
    def list_fact_competitors(
        self, fact_id: str
    ) -> list[IntelFactCompetitorLink]: ...
    def link_fact_to_product(
        self, link: IntelFactProductLink
    ) -> IntelFactProductLink: ...
    def unlink_fact_from_product(
        self, fact_id: str, product_id: int, role: str | None = None
    ) -> None: ...
    def list_fact_products(self, fact_id: str) -> list[IntelFactProductLink]: ...

    # ---- context for verification ----
    def resolve_evidence_context(
        self,
        *,
        document_version_id: str,
        source_occurrence_id: str,
    ) -> dict[str, Any]: ...


@runtime_checkable
class InsightStoreV2Protocol(Protocol):
    """Target contract for Insight Claim and Claim ↔ Fact."""

    def save_claim(self, claim: InsightClaim) -> InsightClaim: ...
    def get_claim(self, claim_id: str) -> InsightClaim | None: ...
    def list_claims(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InsightClaim]: ...
    def update_claim_maturity(
        self,
        claim_id: str,
        maturity: ClaimMaturity | str,
        status_reason: str = "",
        *,
        approved_by: str | None = None,
        approved_at: datetime | None = None,
    ) -> InsightClaim: ...
    def replace_claim_facts(
        self,
        claim_id: str,
        links: list[ClaimFactLink],
    ) -> int: ...
    def list_claim_facts(self, claim_id: str) -> list[ClaimFactLink]: ...
    def find_claims_by_fact(self, fact_id: str) -> list[InsightClaim]: ...
    def mark_dependent_supported_claims_needs_review(
        self,
        fact_id: str,
        status_reason: str,
    ) -> list[InsightClaim]: ...


@runtime_checkable
class SourceProfileStoreV2Protocol(Protocol):
    """Extends :class:`SourceProfileStoreProtocol` with competitor control."""

    def resolve_domain(self, domain: str) -> SourceProfile | None: ...
    def list_profiles(self, *, tier: str | None = None) -> list[SourceProfile]: ...
    def save_profile(
        self, profile: SourceProfile, *, actor: str, reason: str
    ) -> SourceProfile: ...
    def list_revisions(self, profile_id: str): ...  # returns list[SourceProfileRevision]

    # ---- competitor control ----
    def save_profile_competitor(
        self,
        profile_id: str,
        competitor_id: int,
        *,
        actor: str,
        reason: str,
    ) -> None: ...
    def remove_profile_competitor(
        self, profile_id: str, competitor_id: int
    ) -> None: ...
    def list_profile_competitors(self, profile_id: str) -> list[int]: ...
    def find_controlled_profile_ids(self, competitor_id: int) -> list[str]: ...