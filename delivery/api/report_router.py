"""分析报告 API 路由"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.config_manager import get_config_manager
from delivery.auth import AuthContext, require_admin, require_analyst, require_viewer

router = APIRouter(prefix="/api/reports", tags=["reports"])


# ================================================================
# Request / Response Models
# ================================================================

class ReportGenerateRequest(BaseModel):
    competitor_ids: list[int]
    report_type: str = "overview"       # overview / comparison / briefing
    focus: str = ""                     # 分析重点
    dimensions: list[str] = []
    date_from: str | None = None
    date_to: str | None = None
    auto_publish: bool = False


class ReportRejectRequest(BaseModel):
    reason: str = ""


# ================================================================
# Routes
# ================================================================

@router.get("")
def list_reports(
    report_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    _actor: AuthContext = Depends(require_viewer),
):
    """获取报告列表。"""
    mgr = get_config_manager()
    reports = mgr.report_store.list_reports(
        report_type=report_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "reports": [
            {
                "id": r.id,
                "title": r.title,
                "report_type": r.report_type.value if hasattr(r.report_type, 'value') else r.report_type,
                "competitor_ids": r.competitor_ids,
                "status": r.status.value if hasattr(r.status, 'value') else r.status,
                "review_status": getattr(getattr(r, "review_status", None), "value", getattr(r, "review_status", "not_reviewed")),
                "quality_score": getattr(r, "quality_score", None),
                "quality_summary": getattr(r, "quality_summary", ""),
                "source_refs_count": len(r.source_refs),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in reports
        ],
        "total": len(reports),
    }


@router.post("/generate")
def generate_report(
    body: ReportGenerateRequest,
    actor: AuthContext = Depends(require_analyst),
):
    """Generate an analysis report through ReportService."""
    if not body.competitor_ids:
        raise HTTPException(status_code=400, detail="请至少提供一个竞品 ID")
    mgr = get_config_manager()
    try:
        result = mgr.report_service.generate_analysis_report(
            body.competitor_ids,
            report_type=body.report_type,
            focus=body.focus,
            dimensions=body.dimensions or None,
            date_from=body.date_from,
            date_to=body.date_to,
            auto_publish=body.auto_publish,
            actor=actor.actor,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"报告生成失败: {exc}")


@router.get("/{report_id}")
def get_report(
    report_id: int,
    _actor: AuthContext = Depends(require_viewer),
):
    """获取报告详情（含 claims、evidence 和质量摘要）。"""
    mgr = get_config_manager()
    detail = mgr.report_service.get_report_detail(report_id)
    if not detail:
        raise HTTPException(status_code=404, detail="报告不存在")
    return detail


@router.get("/{report_id}/quality")
def get_report_quality(
    report_id: int,
    _actor: AuthContext = Depends(require_viewer),
):
    """获取报告质量审查列表。"""
    mgr = get_config_manager()
    report = mgr.report_store.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    reviews = mgr.report_store.list_quality_reviews(report_id)
    return {
        "report_id": report_id,
        "reviews": [
            {
                **review.__dict__,
                "status": review.status.value if hasattr(review.status, "value") else review.status,
                "created_at": review.created_at.isoformat() if review.created_at else None,
            }
            for review in reviews
        ],
    }


@router.post("/{report_id}/quality/review")
def review_report_quality(
    report_id: int,
    actor: AuthContext = Depends(require_analyst),
):
    """重新运行报告质量门禁。"""
    mgr = get_config_manager()
    report = mgr.report_store.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    try:
        return mgr.report_service.review_existing_report(report_id, actor=actor.actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"报告质量审查失败: {exc}")


@router.get("/{report_id}/audit")
def get_report_audit(
    report_id: int,
    _actor: AuthContext = Depends(require_viewer),
):
    """获取报告的完整审计链路。"""
    mgr = get_config_manager()
    report = mgr.report_store.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    audit_trail = mgr.report_store.get_audit_trail(report_id)
    return {
        "report_id": report_id,
        "title": report.title,
        "audit_trail": audit_trail,
    }


@router.post("/{report_id}/approve")
def approve_report(
    report_id: int,
    actor: AuthContext = Depends(require_admin),
):
    """人工审批通过报告。"""
    mgr = get_config_manager()
    try:
        return mgr.report_service.approve_report(report_id, actor=actor.actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"报告审批失败: {exc}")


@router.post("/{report_id}/reject")
def reject_report(
    report_id: int,
    body: ReportRejectRequest | None = None,
    actor: AuthContext = Depends(require_admin),
):
    """人工拒绝报告并要求修订。"""
    mgr = get_config_manager()
    try:
        return mgr.report_service.reject_report(
            report_id,
            reason=body.reason if body else "",
            actor=actor.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"报告拒绝失败: {exc}")


@router.post("/{report_id}/publish")
def publish_report(
    report_id: int,
    actor: AuthContext = Depends(require_admin),
):
    """发布已审批报告。"""
    mgr = get_config_manager()
    try:
        return mgr.report_service.publish_report(report_id, actor=actor.actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"报告发布失败: {exc}")


@router.delete("/{report_id}")
def delete_report(
    report_id: int,
    _actor: AuthContext = Depends(require_admin),
):
    """删除报告。"""
    mgr = get_config_manager()
    report = mgr.report_store.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    mgr.report_store.delete_report(report_id)
    return {"message": "已删除"}
