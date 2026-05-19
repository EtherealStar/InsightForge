"""Structured intel fact API routes."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.config_manager import get_config_manager
from delivery.auth import require_analyst, require_viewer

router = APIRouter(prefix="/api/intel", tags=["intel"], dependencies=[Depends(require_viewer)])
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


class IntelFactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_document_id: str
    fact_kind: str = "fact"
    fact_type: str = "general"
    dimension: str = "general"
    subject: str
    predicate: str
    object: str = ""
    fact_text: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    event_date: date | None = None
    observed_at: datetime | None = None
    importance_score: float = 0.0
    confidence_score: float = 0.0
    source_reliability: float = 0.0
    extraction_method: str = "manual"
    extraction_version: str = ""
    dedupe_key: str = ""
    status: str = "draft"
    competitor_ids: list[int] = Field(default_factory=list)
    product_ids: list[int] = Field(default_factory=list)
    evidence: list[EvidenceRefInput] = Field(default_factory=list)


class IntelFactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_kind: str | None = None
    fact_type: str | None = None
    dimension: str | None = None
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    fact_text: str | None = None
    attributes: dict[str, Any] | None = None
    event_date: date | None = None
    importance_score: float | None = None
    confidence_score: float | None = None
    status: str | None = None


class IntelFactStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


class FactCompetitorLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competitor_id: int
    relation_type: str = "subject"
    confidence_score: float = 1.0


class FactProductLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int
    relation_type: str = "subject"
    confidence_score: float = 1.0


def _get_service():
    return get_config_manager().intel_service


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


def _filters(
    fact_type: str | None,
    dimension: str | None,
    status: str | None,
    source_document_id: str | None,
    competitor_id: int | None,
    competitor_ids: list[int] | None,
    product_id: int | None,
    product_ids: list[int] | None,
    date_from: date | None,
    date_to: date | None,
    keyword: str | None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if fact_type:
        filters["fact_type"] = fact_type
    if dimension:
        filters["dimension"] = dimension
    if status:
        filters["status"] = status
    if source_document_id:
        filters["source_document_id"] = source_document_id
    if competitor_id is not None:
        filters["competitor_id"] = competitor_id
    if competitor_ids:
        filters["competitor_ids"] = competitor_ids
    if product_id is not None:
        filters["product_id"] = product_id
    if product_ids:
        filters["product_ids"] = product_ids
    if date_from:
        filters["date_from"] = date_from.isoformat()
    if date_to:
        filters["date_to"] = date_to.isoformat()
    if keyword:
        filters["keyword"] = keyword
    return filters


@router.get("/facts")
def list_facts(
    fact_type: str | None = None,
    dimension: str | None = None,
    status: str | None = None,
    source_document_id: str | None = None,
    competitor_id: int | None = None,
    competitor_ids: list[int] | None = Query(default=None),
    product_id: int | None = None,
    product_ids: list[int] | None = Query(default=None),
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List structured intel facts."""
    try:
        filters = _filters(
            fact_type,
            dimension,
            status,
            source_document_id,
            competitor_id,
            competitor_ids,
            product_id,
            product_ids,
            date_from,
            date_to,
            keyword,
        )
        facts = _get_service().list_facts(filters, limit=limit, offset=offset)
        return {"facts": _serialize(facts), "total": len(facts), "limit": limit, "offset": offset}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("intel_api.list_facts_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="查询结构化事实失败")


@router.get("/facts/{fact_id}")
def get_fact(fact_id: str):
    """Get one structured intel fact with evidence refs."""
    try:
        fact = _get_service().get_fact_detail(fact_id)
        if not fact:
            raise HTTPException(status_code=404, detail="结构化事实不存在")
        return _serialize(fact)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("intel_api.get_fact_failed", fact_id=fact_id, error=str(exc))
        raise HTTPException(status_code=500, detail="获取结构化事实失败")


@router.post("/facts", dependencies=[Depends(require_analyst)])
def create_fact(body: IntelFactCreate):
    """Create a draft structured intel fact."""
    if body.status.lower() == "active":
        raise HTTPException(status_code=400, detail="API only creates draft IntelFact")
    try:
        data = body.model_dump()
        data["status"] = "draft"
        data["evidence"] = [item.model_dump() for item in body.evidence]
        fact = _get_service().create_fact(data, created_by="api")
        detail = _get_service().get_fact_detail(fact.id)
        return _serialize(detail or fact)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("intel_api.create_fact_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="创建结构化事实失败")


@router.put("/facts/{fact_id}", dependencies=[Depends(require_analyst)])
def update_fact(fact_id: str, body: IntelFactUpdate):
    """Update an existing draft/non-active structured intel fact."""
    data = body.model_dump(exclude_none=True)
    if data.get("status") == "active":
        raise HTTPException(status_code=400, detail="API cannot activate IntelFact")
    try:
        fact = _get_service().update_fact(fact_id, data, updated_by="api")
        if not fact:
            raise HTTPException(status_code=404, detail="结构化事实不存在")
        detail = _get_service().get_fact_detail(fact_id)
        return _serialize(detail or fact)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("intel_api.update_fact_failed", fact_id=fact_id, error=str(exc))
        raise HTTPException(status_code=500, detail="更新结构化事实失败")


@router.patch("/facts/{fact_id}/status", dependencies=[Depends(require_analyst)])
def update_fact_status(fact_id: str, body: IntelFactStatusUpdate):
    """Update a fact status without allowing API activation."""
    if body.status not in {"draft", "rejected", "archived"}:
        raise HTTPException(
            status_code=400,
            detail="status must be one of: draft, rejected, archived",
        )
    try:
        fact = _get_service().update_fact(fact_id, {"status": body.status}, updated_by="api")
        if not fact:
            raise HTTPException(status_code=404, detail="结构化事实不存在")
        detail = _get_service().get_fact_detail(fact_id)
        return _serialize(detail or fact)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("intel_api.update_fact_status_failed", fact_id=fact_id, error=str(exc))
        raise HTTPException(status_code=500, detail="更新结构化事实状态失败")


@router.post("/facts/{fact_id}/competitors", dependencies=[Depends(require_analyst)])
def link_fact_to_competitor(fact_id: str, body: FactCompetitorLinkCreate):
    """Link a fact to a competitor."""
    try:
        _get_service().link_fact_to_competitor(
            fact_id,
            body.competitor_id,
            body.relation_type,
            body.confidence_score,
        )
        detail = _get_service().get_fact_detail(fact_id)
        return _serialize(detail or {"id": fact_id})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("intel_api.link_competitor_failed", fact_id=fact_id, error=str(exc))
        raise HTTPException(status_code=500, detail="关联竞品失败")


@router.post("/facts/{fact_id}/products", dependencies=[Depends(require_analyst)])
def link_fact_to_product(fact_id: str, body: FactProductLinkCreate):
    """Link a fact to a product."""
    try:
        _get_service().link_fact_to_product(
            fact_id,
            body.product_id,
            body.relation_type,
            body.confidence_score,
        )
        detail = _get_service().get_fact_detail(fact_id)
        return _serialize(detail or {"id": fact_id})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("intel_api.link_product_failed", fact_id=fact_id, error=str(exc))
        raise HTTPException(status_code=500, detail="关联产品失败")


@router.get("/facts/{fact_id}/evidence")
def list_fact_evidence(fact_id: str):
    """List evidence refs for a fact."""
    try:
        fact = _get_service().get_fact_detail(fact_id)
        if not fact:
            raise HTTPException(status_code=404, detail="结构化事实不存在")
        evidence = fact.get("evidence_refs", [])
        return {"evidence_refs": _serialize(evidence), "total": len(evidence)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("intel_api.list_evidence_failed", fact_id=fact_id, error=str(exc))
        raise HTTPException(status_code=500, detail="查询证据失败")


@router.post("/facts/{fact_id}/evidence", dependencies=[Depends(require_analyst)])
def create_fact_evidence(fact_id: str, body: EvidenceRefInput):
    """Attach evidence to a fact."""
    try:
        evidence = _get_service().attach_evidence(
            "intel_fact",
            fact_id,
            body.model_dump(),
        )
        return _serialize(evidence)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("intel_api.create_evidence_failed", fact_id=fact_id, error=str(exc))
        raise HTTPException(status_code=500, detail="新增证据失败")


@router.post("/pipeline", dependencies=[Depends(require_analyst)])
def run_intel_pipeline():
    """Run the intel ingestion pipeline asynchronously."""
    try:
        from scheduler.tasks import run_pipeline_task

        mgr = get_config_manager()
        run = mgr.task_run_store.create_run(
            "intel_pipeline",
            {"manual": True, "trigger": "api"},
        )
        try:
            task = run_pipeline_task.apply_async(
                kwargs={"manual": True, "task_run_id": run.id},
                task_id=run.id,
            )
        except Exception as enqueue_error:
            mgr.task_run_store.finish_run(
                run.id,
                "failed",
                error={"message": str(enqueue_error), "stage": "enqueue"},
            )
            raise
        return {"status": "ok", "task_id": task.id, "message": "情报采集任务已开始"}
    except Exception as exc:
        logger.exception("intel_api.pipeline_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"情报采集任务触发失败: {exc}")
