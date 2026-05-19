"""Insight claim API routes."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.config_manager import get_config_manager
from delivery.auth import require_analyst, require_viewer

router = APIRouter(prefix="/api/insights", tags=["insights"], dependencies=[Depends(require_viewer)])
logger = structlog.get_logger(__name__)


class EvidenceRefInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_document_id: str | None = None
    parent_chunk_id: str | None = None
    url: str = ""
    title: str = ""
    snippet: str = ""
    quote_hash: str = ""
    evidence_type: str = "source_chunk"
    relevance_score: float = 1.0


class InsightClaimCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_text: str
    claim_type: str = "finding"
    dimension: str = "general"
    competitor_ids: list[int] = Field(default_factory=list)
    product_ids: list[int] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    limitations: str = ""
    status: str = "draft"
    evidence: list[EvidenceRefInput] = Field(default_factory=list)


class InsightClaimUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_text: str | None = None
    claim_type: str | None = None
    dimension: str | None = None
    competitor_ids: list[int] | None = None
    product_ids: list[int] | None = None
    fact_ids: list[str] | None = None
    confidence_score: float | None = None
    limitations: str | None = None
    status: str | None = None
    evidence: list[EvidenceRefInput] | None = None


def _get_service():
    return get_config_manager().insight_service


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


@router.get("/claims")
def list_claims(
    claim_type: str | None = None,
    dimension: str | None = None,
    status: str | None = None,
    competitor_id: int | None = None,
    competitor_ids: list[int] | None = Query(default=None),
    fact_id: str | None = None,
    fact_ids: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List insight claims."""
    try:
        filters: dict[str, Any] = {}
        if claim_type:
            filters["claim_type"] = claim_type
        if dimension:
            filters["dimension"] = dimension
        if status:
            filters["status"] = status
        if competitor_id is not None:
            filters["competitor_id"] = competitor_id
        if competitor_ids:
            filters["competitor_ids"] = competitor_ids
        if fact_id:
            filters["fact_id"] = fact_id
        if fact_ids:
            filters["fact_ids"] = fact_ids
        claims = _get_service().list_claims(filters, limit=limit, offset=offset)
        return {"claims": _serialize(claims), "total": len(claims), "limit": limit, "offset": offset}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("insight_api.list_claims_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="查询分析 claim 失败")


@router.get("/claims/{claim_id}")
def get_claim(claim_id: str):
    """Get one insight claim with evidence refs."""
    try:
        claim = _get_service().get_claim_detail(claim_id)
        if not claim:
            raise HTTPException(status_code=404, detail="分析 claim 不存在")
        return _serialize(claim)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("insight_api.get_claim_failed", claim_id=claim_id, error=str(exc))
        raise HTTPException(status_code=500, detail="获取分析 claim 失败")


@router.post("/claims", dependencies=[Depends(require_analyst)])
def create_claim(body: InsightClaimCreate):
    """Create a draft insight claim."""
    if body.status.lower() == "active":
        raise HTTPException(status_code=400, detail="API only creates draft InsightClaim")
    try:
        data = body.model_dump()
        data["status"] = "draft"
        data["evidence"] = [item.model_dump() for item in body.evidence]
        claim = _get_service().create_claim(data, created_by="api")
        detail = _get_service().get_claim_detail(claim.id)
        return _serialize(detail or claim)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("insight_api.create_claim_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="创建分析 claim 失败")


@router.put("/claims/{claim_id}", dependencies=[Depends(require_analyst)])
def update_claim(claim_id: str, body: InsightClaimUpdate):
    """Update an existing draft/non-active insight claim."""
    data = body.model_dump(exclude_none=True)
    if data.get("status") == "active":
        raise HTTPException(status_code=400, detail="API cannot activate InsightClaim")
    if "evidence" in data and data["evidence"] is not None:
        data["evidence"] = [item.model_dump() for item in body.evidence or []]
    try:
        claim = _get_service().update_claim(claim_id, data, updated_by="api")
        if not claim:
            raise HTTPException(status_code=404, detail="分析 claim 不存在")
        detail = _get_service().get_claim_detail(claim_id)
        return _serialize(detail or claim)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("insight_api.update_claim_failed", claim_id=claim_id, error=str(exc))
        raise HTTPException(status_code=500, detail="更新分析 claim 失败")


@router.post("/claims/{claim_id}/validate", dependencies=[Depends(require_analyst)])
def validate_claim(claim_id: str):
    """Run Phase 2 evidence validation for one claim."""
    try:
        result = _get_service().validate_claim_evidence(claim_id)
        status_code = 200 if result.get("valid") else 400
        if status_code == 400 and result.get("errors") == [f"InsightClaim not found: {claim_id}"]:
            raise HTTPException(status_code=404, detail="分析 claim 不存在")
        if status_code == 400:
            raise HTTPException(status_code=400, detail=result)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("insight_api.validate_claim_failed", claim_id=claim_id, error=str(exc))
        raise HTTPException(status_code=500, detail="校验分析 claim 失败")
