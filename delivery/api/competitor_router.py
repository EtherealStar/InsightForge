"""竞品管理 API 路由"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.config_manager import get_config_manager
from delivery.auth import require_admin, require_analyst, require_viewer
from services.competitor_service import CompetitorService

router = APIRouter(prefix="/api/competitors", tags=["competitors"], dependencies=[Depends(require_viewer)])
logger = structlog.get_logger(__name__)


# ================================================================
# Request / Response Models
# ================================================================

class CompetitorCreate(BaseModel):
    name: str
    aliases: list[str] = []
    website: str = ""
    industry: str = ""
    description: str = ""
    logo_url: str = ""
    tags: list[str] = []


class CompetitorUpdate(BaseModel):
    name: Optional[str] = None
    aliases: Optional[list[str]] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    tags: Optional[list[str]] = None
    status: Optional[str] = None


class ProductCreate(BaseModel):
    name: str
    description: str = ""
    category: str = ""
    url: str = ""
    pricing_info: str = ""


class CompetitorFactCompareRequest(BaseModel):
    competitor_ids: list[int]
    dimensions: list[str] = []
    date_from: date | None = None
    date_to: date | None = None


# ================================================================
# Helper
# ================================================================

def _get_service() -> CompetitorService:
    mgr = get_config_manager()
    return mgr.competitor_service


def _competitor_to_dict(comp) -> dict:
    return {
        "id": comp.id,
        "name": comp.name,
        "aliases": comp.aliases,
        "website": comp.website,
        "industry": comp.industry,
        "description": comp.description,
        "logo_url": comp.logo_url,
        "tags": comp.tags,
        "status": comp.status,
        "created_at": comp.created_at.isoformat() if comp.created_at else None,
        "updated_at": comp.updated_at.isoformat() if comp.updated_at else None,
    }


def _product_to_dict(product) -> dict:
    return {
        "id": product.id,
        "competitor_id": product.competitor_id,
        "name": product.name,
        "description": product.description,
        "category": product.category,
        "url": product.url,
        "pricing_info": product.pricing_info,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None,
    }


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


def _fact_to_dict(fact) -> dict:
    return _serialize(
        {
            "id": fact.id,
            "fact_kind": fact.fact_kind,
            "fact_type": fact.fact_type,
            "dimension": fact.dimension,
            "subject": fact.subject,
            "predicate": fact.predicate,
            "object": fact.object,
            "fact_text": fact.fact_text,
            "attributes": fact.attributes,
            "event_date": fact.event_date,
            "observed_at": fact.observed_at,
            "importance_score": fact.importance_score,
            "confidence_score": fact.confidence_score,
            "assertion_key": fact.assertion_key,
            "verification_status": getattr(fact.verification_status, "value", fact.verification_status),
            "verification_reason": fact.verification_reason,
            "status": fact.status,
            "competitor_ids": fact.competitor_ids,
            "product_ids": fact.product_ids,
            "evidence_refs": fact.evidence_refs,
        }
    )


def _fact_filters(
    fact_type: str | None = None,
    dimension: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    filters: dict[str, Any] = {"limit": limit}
    if fact_type:
        filters["fact_type"] = fact_type
    if dimension:
        filters["dimension"] = dimension
    if status:
        filters["status"] = status
    if date_from:
        filters["date_from"] = date_from.isoformat()
    if date_to:
        filters["date_to"] = date_to.isoformat()
    if keyword:
        filters["keyword"] = keyword
    return filters


# ================================================================
# Routes
# ================================================================

@router.get("")
def list_competitors(status: str = "active"):
    """列出竞品。"""
    service = _get_service()
    competitors = service.list_competitors(status=status)
    return {
        "competitors": [_competitor_to_dict(c) for c in competitors],
        "total": len(competitors),
    }


@router.post("", dependencies=[Depends(require_analyst)])
def create_competitor(body: CompetitorCreate):
    """创建竞品。"""
    service = _get_service()
    try:
        comp = service.create_competitor(body.model_dump())
        return _competitor_to_dict(comp)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{competitor_id}")
def get_competitor(competitor_id: int):
    """获取竞品详情（含产品线和情报统计）。"""
    service = _get_service()
    try:
        result = service.get_competitor(competitor_id)
        if not result:
            raise HTTPException(status_code=404, detail="竞品不存在")
        return {
            "competitor": _competitor_to_dict(result["competitor"]),
            "products": [_product_to_dict(p) for p in result["products"]],
            "fact_count": result["fact_count"],
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("competitor_api.get_competitor_failed", competitor_id=competitor_id, error=str(e))
        raise HTTPException(status_code=500, detail="获取竞品详情失败")


@router.put("/{competitor_id}", dependencies=[Depends(require_analyst)])
def update_competitor(competitor_id: int, body: CompetitorUpdate):
    """更新竞品信息。"""
    service = _get_service()
    update_data = body.model_dump(exclude_none=True)
    comp = service.update_competitor(competitor_id, update_data)
    if not comp:
        raise HTTPException(status_code=404, detail="竞品不存在")
    return _competitor_to_dict(comp)


@router.delete("/{competitor_id}", dependencies=[Depends(require_admin)])
def delete_competitor(competitor_id: int):
    """删除竞品。"""
    service = _get_service()
    service.delete_competitor(competitor_id)
    return {"message": "已删除"}


@router.post("/{competitor_id}/products", dependencies=[Depends(require_analyst)])
def add_product(competitor_id: int, body: ProductCreate):
    """为竞品添加产品线。"""
    service = _get_service()
    # 确认竞品存在
    if not service.competitor_store.get_competitor(competitor_id):
        raise HTTPException(status_code=404, detail="竞品不存在")
    product = service.add_product(competitor_id, body.model_dump())
    return _product_to_dict(product)


@router.get("/{competitor_id}/products")
def list_products(competitor_id: int):
    """获取竞品的产品线。"""
    service = _get_service()
    products = service.competitor_store.list_products(competitor_id)
    return {"products": [_product_to_dict(p) for p in products]}


@router.delete("/products/{product_id}", dependencies=[Depends(require_admin)])
def delete_product(product_id: int):
    """删除产品线。"""
    service = _get_service()
    service.delete_product(product_id)
    return {"message": "已删除"}


@router.get("/{competitor_id}/facts")
def get_competitor_facts(
    competitor_id: int,
    fact_type: str | None = None,
    dimension: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    """获取竞品结构化 facts 和聚合。"""
    service = _get_service()
    try:
        profile = service.get_competitor_fact_profile(
            competitor_id,
            _fact_filters(fact_type, dimension, status, date_from, date_to, keyword, limit),
        )
        if not profile:
            raise HTTPException(status_code=404, detail="竞品不存在")
        facts = [_fact_to_dict(fact) for fact in profile["facts"]]
        return {
            "competitor": _competitor_to_dict(profile["competitor"]),
            "products": [_product_to_dict(p) for p in profile["products"]],
            "facts": facts,
            "aggregates": _serialize(profile["aggregates"]),
            "total": len(facts),
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("competitor_api.get_facts_failed", competitor_id=competitor_id, error=str(e))
        raise HTTPException(status_code=500, detail="获取竞品 facts 失败")


@router.get("/{competitor_id}/timeline")
def get_competitor_timeline(
    competitor_id: int,
    fact_type: str | None = None,
    dimension: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    """获取竞品事件时间线。"""
    service = _get_service()
    try:
        profile = service.get_competitor_timeline(
            competitor_id,
            _fact_filters(fact_type, dimension, status, date_from, date_to, keyword, limit),
        )
        if not profile:
            raise HTTPException(status_code=404, detail="竞品不存在")
        facts = [_fact_to_dict(fact) for fact in profile["timeline"]]
        return {
            "competitor": _competitor_to_dict(profile["competitor"]),
            "products": [_product_to_dict(p) for p in profile["products"]],
            "timeline": facts,
            "total": len(facts),
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("competitor_api.get_timeline_failed", competitor_id=competitor_id, error=str(e))
        raise HTTPException(status_code=500, detail="获取竞品 timeline 失败")


@router.post("/compare/facts")
def compare_competitor_facts(body: CompetitorFactCompareRequest):
    """基于结构化 facts/events 对比多个竞品。"""
    if len(body.competitor_ids) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 个竞品 ID")
    service = _get_service()
    try:
        time_window = {}
        if body.date_from:
            time_window["date_from"] = body.date_from.isoformat()
        if body.date_to:
            time_window["date_to"] = body.date_to.isoformat()
        return _serialize(
            service.compare_competitor_facts(
                body.competitor_ids,
                dimensions=body.dimensions or None,
                time_window=time_window or None,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("competitor_api.compare_facts_failed", error=str(e))
        raise HTTPException(status_code=500, detail="竞品 facts 对比失败")


@router.post("/auto-link", dependencies=[Depends(require_analyst)])
def auto_link_intel():
    """自动将结构化事实关联到匹配的竞品。"""
    service = _get_service()
    result = service.auto_link_facts()
    return result
