"""V2 Intelligence API router (Milestone 6).

Exposes the new three-layer contract:
  * /api/v2/intel/facts            — list / get / create draft / activate / supersede
  * /api/v2/intel/facts/{id}/split — move evidence to a new draft fact
  * /api/v2/intel/evidence         — create immutable anchors
  * /api/v2/intel/claims           — list / get / create hypothesis / approve / supersede

These endpoints run alongside the legacy routers during the cut-over window.
All legacy score / dimension / fact_kind fields are rejected by Pydantic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
import psycopg2
from psycopg2.extras import DictCursor

from core.config import AppConfig
from core.exceptions import (
    IntelligenceInvariantError,
    StoreError,
)
from core.config_manager import get_config_manager
from infrastructure.insight_store_v2 import PostgresInsightStoreV2
from infrastructure.intel_store_v2 import PostgresIntelStoreV2
from models.target_evidence import EvidenceReference
from models.target_insight import ClaimFactLink, ClaimMaturity, InsightClaim
from models.target_intel import (
    FactEntityRole,
    FactEvidenceLink,
    FactLifecycleStatus,
    IntelFact,
    IntelFactCompetitorLink,
    LinkReviewStatus,
    VerificationStatus,
)
from services.evidence_anchor_service import (
    AnchorRequest,
    EvidenceAnchorService,
)
from services.evidence_verification_v2 import EvidenceVerificationServiceV2
from services.insight_service_v2 import ClaimDraftRequest, InsightServiceV2
from services.intel_lifecycle_service import IntelLifecycleService


router = APIRouter(prefix="/api/v2", tags=["intelligence-v2"])


# ----- Pydantic schemas -------------------------------------------------


class EvidenceReferenceCreate(BaseModel):
    document_version_id: str
    source_occurrence_id: str
    quoted_text: str
    locator: dict[str, Any]
    parent_chunk_id: Optional[str] = None
    client_quote_hash: Optional[str] = None


class IntelFactCreate(BaseModel):
    fact_type: str
    fact_text: str
    normalized_schema: Optional[str] = None
    normalized_data: Optional[dict[str, Any]] = None
    occurred_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    time_precision: Optional[str] = None
    candidate_key: Optional[str] = None
    subject_competitor_ids: list[int] = Field(default_factory=list)
    subject_product_ids: list[int] = Field(default_factory=list)


class IntelFactResponse(BaseModel):
    id: str
    fact_type: str
    fact_text: str
    lifecycle_status: Optional[str]
    verification_status: Optional[str]
    status_reason: str = ""
    normalized_data: Optional[dict[str, Any]] = None
    occurred_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    time_precision: Optional[str] = None
    candidate_key: Optional[str] = None
    supersedes_fact_id: Optional[str] = None
    created_by: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ActivateResponse(BaseModel):
    fact: IntelFactResponse
    is_active: bool
    status_reason: str = ""


class SplitRequest(BaseModel):
    source_fact_id: str
    target_fact_id: str
    evidence_ref_ids: list[str]


class SupersedeFactRequest(BaseModel):
    old_fact_id: str
    new_fact: IntelFactCreate


class SubjectLinkCreate(BaseModel):
    competitor_id: Optional[int] = None
    product_id: Optional[int] = None
    role: str = "subject"
    review_status: str = "needs_review"


class ClaimCreate(BaseModel):
    claim_text: str
    tags: list[str] = Field(default_factory=list)
    limitations: str = ""
    scope: Optional[dict[str, Any]] = None
    fact_ids: list[str] = Field(default_factory=list)


class ClaimReplaceFacts(BaseModel):
    links: list[dict[str, Any]]


class ClaimApproveRequest(BaseModel):
    approved_by: str


class ClaimResponse(BaseModel):
    id: str
    claim_text: str
    tags: list[str] = Field(default_factory=list)
    limitations: str = ""
    scope: Optional[dict[str, Any]] = None
    maturity: Optional[str]
    status_reason: str = ""
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    supersedes_claim_id: Optional[str] = None
    created_by: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ----- dependency -----------------------------------------------------


def _services():
    config: AppConfig = get_config_manager().config
    store = PostgresIntelStoreV2(config.pg_dsn)
    insight = PostgresInsightStoreV2(config.pg_dsn)
    anchor = EvidenceAnchorService(store)
    verifier = EvidenceVerificationServiceV2(config.pg_dsn)
    lifecycle = IntelLifecycleService(store, verifier)
    insight_svc = InsightServiceV2(insight, store)
    return store, insight, anchor, lifecycle, insight_svc


# ----- helpers --------------------------------------------------------


def _fact_to_response(fact: IntelFact) -> IntelFactResponse:
    return IntelFactResponse(
        id=fact.id,
        fact_type=str(fact.fact_type),
        fact_text=fact.fact_text,
        lifecycle_status=str(fact.lifecycle_status) if fact.lifecycle_status else None,
        verification_status=str(fact.verification_status) if fact.verification_status else None,
        status_reason=fact.status_reason or "",
        normalized_data=fact.normalized_data,
        occurred_at=fact.occurred_at,
        valid_from=fact.valid_from,
        valid_to=fact.valid_to,
        time_precision=str(fact.time_precision) if fact.time_precision else None,
        candidate_key=fact.candidate_key,
        supersedes_fact_id=fact.supersedes_fact_id,
        created_by=fact.created_by,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
    )


def _claim_to_response(claim: InsightClaim) -> ClaimResponse:
    return ClaimResponse(
        id=claim.id,
        claim_text=claim.claim_text,
        tags=list(claim.tags or []),
        limitations=claim.limitations or "",
        scope=claim.scope,
        maturity=str(claim.maturity) if claim.maturity else None,
        status_reason=claim.status_reason or "",
        approved_by=claim.approved_by,
        approved_at=claim.approved_at,
        supersedes_claim_id=claim.supersedes_claim_id,
        created_by=claim.created_by,
        created_at=claim.created_at,
        updated_at=claim.updated_at,
    )


def _handle_invariance_error(exc: IntelligenceInvariantError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


def _handle_store_error(exc: StoreError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


# ----- intel fact routes ----------------------------------------------


@router.get("/intel/facts")
def list_intel_facts(
    lifecycle_status: Optional[str] = Query(None),
    verification_status: Optional[str] = Query(None),
    fact_type: Optional[str] = Query(None),
    subject_competitor_id: Optional[int] = Query(None),
    occurred_from: Optional[datetime] = Query(None),
    occurred_to: Optional[datetime] = Query(None),
    keyword: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    store, *_ = _services()
    facts = store.list_facts(
        {
            "lifecycle_status": lifecycle_status,
            "verification_status": verification_status,
            "fact_type": fact_type,
            "subject_competitor_id": subject_competitor_id,
            "occurred_from": occurred_from,
            "occurred_to": occurred_to,
            "keyword": keyword,
        },
        limit=limit,
        offset=offset,
    )
    return {"items": [_fact_to_response(f).model_dump() for f in facts]}


@router.get("/intel/facts/{fact_id}")
def get_intel_fact(fact_id: str):
    store, *_ = _services()
    fact = store.get_fact(fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="fact not found")
    return _fact_to_response(fact).model_dump()


@router.post("/intel/facts", status_code=201)
def create_intel_fact(payload: IntelFactCreate, created_by: str = "user"):
    _store, _insight, _anchor, lifecycle, _svc = _services()
    try:
        fact = lifecycle.create_draft_fact(
            fact_type=payload.fact_type,
            fact_text=payload.fact_text,
            candidate_key=payload.candidate_key,
            normalized_schema=payload.normalized_schema,
            normalized_data=payload.normalized_data,
            occurred_at=payload.occurred_at,
            valid_from=payload.valid_from,
            valid_to=payload.valid_to,
            time_precision=payload.time_precision,
            created_by=created_by,
        )
    except IntelligenceInvariantError as exc:
        raise _handle_invariance_error(exc)
    return _fact_to_response(fact).model_dump()


@router.post("/intel/facts/{fact_id}/activate")
def activate_intel_fact(fact_id: str):
    _store, _insight, _anchor, lifecycle, _svc = _services()
    try:
        report = lifecycle.activate_fact(fact_id)
    except IntelligenceInvariantError as exc:
        raise _handle_invariance_error(exc)
    return {
        "fact": _fact_to_response(report.fact).model_dump(),
        "is_active": report.is_active,
        "status_reason": report.status_reason,
    }


@router.post("/intel/facts/{fact_id}/retract")
def retract_intel_fact(fact_id: str, reason: str = Query(...)):
    _store, _insight, _anchor, lifecycle, _svc = _services()
    try:
        fact = lifecycle.retract_fact(fact_id, reason)
    except IntelligenceInvariantError as exc:
        raise _handle_invariance_error(exc)
    return _fact_to_response(fact).model_dump()


@router.post("/intel/facts/supersede", status_code=201)
def supersede_intel_fact(payload: SupersedeFactRequest):
    _store, _insight, _anchor, lifecycle, _svc = _services()
    new = IntelFact(
        fact_type=payload.new_fact.fact_type,
        fact_text=payload.new_fact.fact_text,
        normalized_data=payload.new_fact.normalized_data,
        occurred_at=payload.new_fact.occurred_at,
        valid_from=payload.new_fact.valid_from,
        valid_to=payload.new_fact.valid_to,
        time_precision=payload.new_fact.time_precision,
        candidate_key=payload.new_fact.candidate_key,
        lifecycle_status="draft",
    )
    try:
        created = lifecycle.supersede_fact(
            old_fact_id=payload.old_fact_id, new_fact=new
        )
    except IntelligenceInvariantError as exc:
        raise _handle_invariance_error(exc)
    return _fact_to_response(created).model_dump()


@router.post("/intel/facts/split")
def split_intel_fact(payload: SplitRequest):
    _store, _insight, _anchor, lifecycle, _svc = _services()
    try:
        moved = lifecycle.split_fact_evidence(
            source_fact_id=payload.source_fact_id,
            target_fact_id=payload.target_fact_id,
            evidence_ref_ids=payload.evidence_ref_ids,
        )
    except IntelligenceInvariantError as exc:
        raise _handle_invariance_error(exc)
    return {"moved": moved}


# ----- subject link routes --------------------------------------------


class LinkFactEvidenceRequest(BaseModel):
    evidence_ref_id: str
    stance: str = "supports"


@router.post("/intel/facts/{fact_id}/evidence")
def link_fact_to_evidence(fact_id: str, payload: LinkFactEvidenceRequest):
    store, *_ = _services()
    try:
        link = store.link_fact_evidence(
            FactEvidenceLink(fact_id, payload.evidence_ref_id, payload.stance)
        )
        return link.__dict__
    except psycopg2.errors.CheckViolation as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/intel/facts/{fact_id}/subjects")
def add_subject_link(fact_id: str, payload: SubjectLinkCreate):
    store, *_ = _services()
    try:
        if payload.competitor_id is not None:
            link = IntelFactCompetitorLink(
                fact_id=fact_id,
                competitor_id=payload.competitor_id,
                role=payload.role,
                review_status=payload.review_status,
            )
            store.link_fact_to_competitor(link)
            return link.__dict__
        raise HTTPException(status_code=422, detail="competitor_id required")
    except psycopg2.errors.CheckViolation as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# ----- evidence routes -------------------------------------------------


@router.post("/intel/evidence", status_code=201)
def create_evidence_reference(payload: EvidenceReferenceCreate):
    _store, _insight, anchor, _lifecycle, _svc = _services()
    try:
        evidence = anchor.create_evidence_reference(
            AnchorRequest(
                document_version_id=payload.document_version_id,
                source_occurrence_id=payload.source_occurrence_id,
                quoted_text=payload.quoted_text,
                locator=payload.locator,
                parent_chunk_id=payload.parent_chunk_id,
                client_quote_hash=payload.client_quote_hash,
            )
        )
    except IntelligenceInvariantError as exc:
        raise _handle_invariance_error(exc)
    return {
        "id": evidence.id,
        "document_version_id": evidence.document_version_id,
        "source_occurrence_id": evidence.source_occurrence_id,
        "quoted_text": evidence.quoted_text,
        "quote_hash": evidence.quote_hash,
        "locator": evidence.locator,
    }


# ----- claim routes ----------------------------------------------------


@router.get("/intel/claims")
def list_intel_claims(
    maturity: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    fact_id: Optional[str] = Query(None),
    competitor_id: Optional[int] = Query(None),
    product_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    _store, insight, _anchor, _lifecycle, _svc = _services()
    claims = insight.list_claims(
        {
            "maturity": maturity,
            "tag": tag,
            "fact_id": fact_id,
            "competitor_id": competitor_id,
            "product_id": product_id,
            "keyword": keyword,
        },
        limit=limit,
        offset=offset,
    )
    return {"items": [_claim_to_response(c).model_dump() for c in claims]}


@router.get("/intel/claims/{claim_id}")
def get_intel_claim(claim_id: str):
    _store, insight, _anchor, _lifecycle, _svc = _services()
    claim = insight.get_claim(claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return _claim_to_response(claim).model_dump()


@router.post("/intel/claims", status_code=201)
def create_intel_claim(payload: ClaimCreate, created_by: str = "agent"):
    _store, _insight, _anchor, _lifecycle, insight_svc = _services()
    if not payload.fact_ids:
        raise HTTPException(
            status_code=422,
            detail="claims must reference at least one fact via fact_ids",
        )
    try:
        claim = insight_svc.create_hypothesis(
            ClaimDraftRequest(
                claim_text=payload.claim_text,
                tags=payload.tags,
                limitations=payload.limitations,
                scope=payload.scope,
                created_by=created_by,
            )
        )
        insight_svc.replace_facts(
            claim.id,
            [ClaimFactLink(claim.id, fid, "supports") for fid in payload.fact_ids],
        )
    except IntelligenceInvariantError as exc:
        raise _handle_invariance_error(exc)
    return _claim_to_response(claim).model_dump()


@router.post("/intel/claims/{claim_id}/approve")
def approve_intel_claim(claim_id: str, payload: ClaimApproveRequest):
    _store, _insight, _anchor, _lifecycle, insight_svc = _services()
    try:
        claim = insight_svc.approve_claim(claim_id, payload.approved_by)
    except IntelligenceInvariantError as exc:
        raise _handle_invariance_error(exc)
    return _claim_to_response(claim).model_dump()


@router.post("/intel/claims/{claim_id}/facts")
def replace_claim_facts(claim_id: str, payload: ClaimReplaceFacts):
    _store, _insight, _anchor, _lifecycle, insight_svc = _services()
    links = [
        ClaimFactLink(claim_id, item["fact_id"], item.get("stance", "supports"))
        for item in payload.links
    ]
    try:
        n = insight_svc.replace_facts(claim_id, links)
    except IntelligenceInvariantError as exc:
        raise _handle_invariance_error(exc)
    return {"replaced": n}