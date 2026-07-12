"""来源、文档簇和证据治理 API。"""
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.config_manager import get_config_manager
from core.factory import create_source_profile_store
from delivery.auth import require_admin, require_viewer
from models.source_governance import SourceKind, SourceProfile, SourceTier
from services.source_governance_service import SourceGovernanceService

router = APIRouter(prefix="/api/governance", tags=["governance"], dependencies=[Depends(require_viewer)])


class SourceProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str
    tier: SourceTier = SourceTier.UNKNOWN
    source_kind: SourceKind = SourceKind.OTHER
    inherit_to_subdomains: bool = False
    reason: str = Field(min_length=1)


def _service():
    config = get_config_manager().config
    return SourceGovernanceService(create_source_profile_store(config))


def _serialize(value):
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


@router.get("/sources")
def list_sources(tier: str | None = Query(default=None)):
    return {"sources": _serialize(_service().list_profiles(tier=tier))}


@router.get("/sources/pending")
def list_pending_sources():
    return {"sources": _serialize(_service().list_profiles(tier=SourceTier.UNKNOWN.value))}


@router.get("/sources/{profile_id}/revisions")
def list_source_revisions(profile_id: str):
    return {"revisions": _serialize(_service().list_revisions(profile_id))}


@router.put("/sources/{domain}", dependencies=[Depends(require_admin)])
def save_source(domain: str, body: SourceProfileInput):
    service = _service()
    normalized = service.normalize_domain(domain)
    if normalized != service.normalize_domain(body.domain):
        raise HTTPException(status_code=400, detail="路径域名与请求体域名不一致")
    profile = service.resolve_profile(normalized) or SourceProfile(domain=normalized)
    profile.domain = normalized
    profile.tier = body.tier
    profile.source_kind = body.source_kind
    profile.inherit_to_subdomains = body.inherit_to_subdomains
    return _serialize(service.save_profile(profile, actor="api-admin", reason=body.reason))
