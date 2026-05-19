"""Governed analysis report workflow service."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import structlog

from core.protocols import CompetitorStoreProtocol, LLMClientProtocol, ReportStoreProtocol
from models.report import (
    AnalysisReport,
    ReportClaimRef,
    ReportEvidenceRef,
    ReportReviewStatus,
    ReportStatus,
    ReportType,
)
from services.insight_service import InsightService
from services.intel_service import IntelService
from services.report_quality_service import ReportQualityService

logger = structlog.get_logger(__name__)


class ReportService:
    """Build, persist, review, and transition analysis reports."""

    def __init__(
        self,
        competitor_store: CompetitorStoreProtocol,
        intel_service: IntelService,
        insight_service: InsightService,
        llm_client: LLMClientProtocol | None = None,
        report_store: ReportStoreProtocol | None = None,
        quality_service: ReportQualityService | None = None,
        *,
        auto_publish_enabled: bool = False,
    ):
        self.competitor_store = competitor_store
        self.intel_service = intel_service
        self.insight_service = insight_service
        self.llm_client = llm_client
        self.report_store = report_store
        self.quality_service = quality_service
        self.auto_publish_enabled = auto_publish_enabled

    def build_report_context(
        self,
        competitor_ids: list[int],
        *,
        dimensions: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        focus: str = "",
        report_type: str = "overview",
        actor: str = "system",
    ) -> dict[str, Any]:
        competitors = []
        products = []
        limitations = []
        valid_competitor_ids = []
        for competitor_id in competitor_ids:
            competitor = self.competitor_store.get_competitor(competitor_id)
            if competitor:
                competitors.append(competitor)
                valid_competitor_ids.append(competitor_id)
                products.extend(self.competitor_store.list_products(competitor_id))
            else:
                limitations.append(f"competitor not found: {competitor_id}")

        facts = []
        claims = []
        requested_dimensions = dimensions or [None]
        for dimension in requested_dimensions:
            filters: dict[str, Any] = {"competitor_ids": valid_competitor_ids or competitor_ids}
            if dimension:
                filters["dimension"] = dimension
            if date_from:
                filters["date_from"] = date_from
            if date_to:
                filters["date_to"] = date_to
            if focus:
                filters["keyword"] = focus
            facts.extend(self.intel_service.list_facts(filters, limit=100))
            claim_filters: dict[str, Any] = {"competitor_ids": valid_competitor_ids or competitor_ids}
            if dimension:
                claim_filters["dimension"] = dimension
            claims.extend(self.insight_service.list_claims(claim_filters, limit=50))

        facts = _dedupe_dicts(facts)
        claims = _dedupe_dicts(claims)
        evidence_refs = self._collect_evidence_refs(facts, claims)
        if report_type == ReportType.COMPARISON.value and len(valid_competitor_ids) < 2:
            limitations.append("comparison report requires at least two valid competitors")
        if not facts:
            limitations.append("no structured facts matched the report request")
        if not evidence_refs:
            limitations.append("no evidence references matched the report request")

        coverage = {
            "competitor_count": len(valid_competitor_ids),
            "fact_count": len(facts),
            "claim_count": len(claims),
            "evidence_count": len(evidence_refs),
            "dimensions": [
                dimension for dimension in requested_dimensions if dimension
            ],
        }
        request = {
            "competitor_ids": competitor_ids,
            "valid_competitor_ids": valid_competitor_ids,
            "dimensions": dimensions or [],
            "date_from": date_from,
            "date_to": date_to,
            "focus": focus,
            "report_type": report_type,
            "actor": actor,
        }
        retrieval_trace = {
            "fact_limit_per_dimension": 100,
            "claim_limit_per_dimension": 50,
            "deduped": True,
        }
        context = {
            "request": request,
            "competitors": competitors,
            "products": products,
            "facts": facts,
            "claims": claims,
            "evidence_refs": evidence_refs,
            "coverage": coverage,
            "limitations": limitations,
            "retrieval_trace": retrieval_trace,
        }
        context["generation_context_hash"] = self._hash_context(context)
        return context

    def select_or_create_claims(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        claims = list(context.get("claims") or [])
        if claims or not context.get("facts"):
            return claims
        try:
            built = self.insight_service.build_claims_from_facts(
                {"competitor_ids": context["request"]["valid_competitor_ids"]},
                max_claims=8,
            )
        except Exception as exc:
            logger.warning("report.claim_generation_failed", error=str(exc))
            return claims
        generated = [
            self.insight_service.get_claim_detail(claim.id) or {"id": claim.id}
            for claim in built
        ]
        context["claims"] = generated
        return generated

    def draft_report(self, context: dict[str, Any]) -> str:
        if self.llm_client is None:
            raise RuntimeError("主 LLM 客户端未配置")

        prompt = self._build_draft_prompt(context)
        return self.llm_client.generate(
            system_prompt="你是一位资深竞品分析师，只基于给定 facts、claims 和 evidence 生成报告。",
            user_message=prompt,
        )

    def save_draft(
        self,
        context: dict[str, Any],
        content: str,
        *,
        actor: str = "system",
    ) -> AnalysisReport:
        if self.report_store is None:
            raise RuntimeError("ReportStore 未配置")

        competitors = context["competitors"]
        comp_names = ", ".join(getattr(comp, "name", "") for comp in competitors) or "Unknown"
        source_refs = [
            {
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "source_document_id": item.get("source_document_id"),
                "parent_chunk_id": item.get("parent_chunk_id"),
                "evidence_id": item.get("id"),
                "citation_label": self._citation_label(index),
                "retrieved_at": datetime.now().isoformat(),
            }
            for index, item in enumerate(context["evidence_refs"], start=1)
        ]
        report = AnalysisReport(
            title=f"{comp_names} - {self._report_type_label(context['request']['report_type'])}",
            report_type=self._safe_report_type(context["request"]["report_type"]),
            competitor_ids=context["request"]["competitor_ids"],
            content=content,
            source_refs=source_refs,
            audit_trail=[
                {
                    "action": "report_drafted",
                    "timestamp": datetime.now().isoformat(),
                    "actor": actor,
                    **context["coverage"],
                }
            ],
            status=ReportStatus.DRAFT,
            review_status=ReportReviewStatus.NOT_REVIEWED,
            generation_context_hash=context["generation_context_hash"],
        )
        saved = self.report_store.save_report(report)

        claim_refs = [
            ReportClaimRef(
                report_id=saved.id or 0,
                claim_id=str(claim.get("id")),
                section_key=str(claim.get("dimension", "")),
                position=index,
                usage_type="supporting",
            )
            for index, claim in enumerate(context.get("claims") or [], start=1)
            if claim.get("id")
        ]
        evidence_refs = [
            ReportEvidenceRef(
                report_id=saved.id or 0,
                evidence_ref_id=item.get("id"),
                claim_id=item.get("claim_id") or item.get("owner_id")
                if item.get("owner_type") == "insight_claim"
                else None,
                fact_id=item.get("fact_id") or item.get("owner_id")
                if item.get("owner_type") == "intel_fact"
                else None,
                section_key=str(item.get("dimension", "")),
                citation_label=self._citation_label(index),
                url=item.get("url", ""),
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
            )
            for index, item in enumerate(context["evidence_refs"], start=1)
        ]
        if claim_refs:
            self.report_store.attach_claims(saved.id or 0, claim_refs)
        if evidence_refs:
            self.report_store.attach_evidence_refs(saved.id or 0, evidence_refs)

        self._append_audit(saved, "report_context_built", context["coverage"])
        self._append_audit(
            saved,
            "report_claims_selected",
            {"claim_count": len(claim_refs)},
        )
        self._append_audit(
            saved,
            "report_drafted",
            {"evidence_count": len(evidence_refs), "actor": actor},
        )
        return saved

    def run_quality_gate(
        self,
        report: AnalysisReport,
        context: dict[str, Any],
        *,
        actor: str = "system",
    ):
        if self.quality_service is None:
            raise RuntimeError("ReportQualityService 未配置")
        if self.report_store is None or report.id is None:
            raise RuntimeError("ReportStore 未配置或报告未保存")
        self.report_store.update_report_status(
            report.id,
            ReportStatus.QUALITY_REVIEWING.value,
            review_status=ReportReviewStatus.NOT_REVIEWED.value,
            actor=actor,
        )
        return self.quality_service.review_report(
            report.id,
            actor=actor,
            run_judge=True,
            context=context,
        )

    def apply_quality_result(
        self,
        report_id: int,
        review,
        *,
        auto_publish: bool = False,
        actor: str = "system",
    ) -> AnalysisReport:
        if self.report_store is None:
            raise RuntimeError("ReportStore 未配置")
        review_status = _enum_value(review.status)
        blocking_count = self._blocking_issue_count(review.issues)
        if review_status == ReportReviewStatus.FAILED.value:
            status = ReportStatus.REVISION_REQUIRED.value
            audit_action = "report_revision_required"
        elif review_status == ReportReviewStatus.PASSED.value:
            status = (
                ReportStatus.APPROVED.value
                if auto_publish and self.auto_publish_enabled
                else ReportStatus.WAITING_REVIEW.value
            )
            audit_action = "report_waiting_review"
        else:
            status = ReportStatus.WAITING_REVIEW.value
            audit_action = "report_waiting_review"

        summary = self._quality_summary(review)
        updated = self.report_store.update_report_status(
            report_id,
            status,
            review_status=review_status,
            quality_score=review.overall_score,
            quality_summary=summary,
            actor=actor,
        )
        self._append_audit(
            updated,
            audit_action,
            {
                "review_id": review.id,
                "review_status": review_status,
                "quality_score": review.overall_score,
                "blocking_issues_count": blocking_count,
            },
        )
        return updated

    def generate_analysis_report(
        self,
        competitor_ids: list[int],
        *,
        report_type: str = "overview",
        focus: str = "",
        dimensions: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        auto_publish: bool = False,
        actor: str = "system",
    ) -> dict[str, Any]:
        context = self.build_report_context(
            competitor_ids,
            dimensions=dimensions,
            date_from=date_from,
            date_to=date_to,
            focus=focus,
            report_type=report_type,
            actor=actor,
        )
        if not context["competitors"]:
            raise ValueError("未找到有效竞品。请使用 list_competitors 查看可用竞品。")
        self.select_or_create_claims(context)
        context["evidence_refs"] = self._collect_evidence_refs(
            context["facts"],
            context["claims"],
        )
        context["coverage"]["claim_count"] = len(context["claims"])
        context["coverage"]["evidence_count"] = len(context["evidence_refs"])
        content = self.draft_report(context)
        report = self.save_draft(context, content, actor=actor)
        review = self.run_quality_gate(report, context, actor=actor)
        updated = self.apply_quality_result(
            report.id or 0,
            review,
            auto_publish=auto_publish,
            actor=actor,
        )
        return self._result_dict(updated, review)

    def get_report_detail(self, report_id: int) -> dict[str, Any] | None:
        if self.report_store is None:
            raise RuntimeError("ReportStore 未配置")
        report = self.report_store.get_report(report_id)
        if report is None:
            return None
        claim_refs = self.report_store.list_report_claims(report_id)
        evidence_refs = self.report_store.list_report_evidence_refs(report_id)
        reviews = self.report_store.list_quality_reviews(report_id)
        return self._report_dict(
            report,
            claims=claim_refs,
            evidence_refs=evidence_refs,
            quality_reviews=reviews,
        )

    def review_existing_report(
        self,
        report_id: int,
        *,
        actor: str = "system",
    ) -> dict[str, Any]:
        if self.report_store is None or self.quality_service is None:
            raise RuntimeError("ReportStore 或 ReportQualityService 未配置")
        self.report_store.update_report_status(
            report_id,
            ReportStatus.QUALITY_REVIEWING.value,
            actor=actor,
        )
        review = self.quality_service.review_report(report_id, actor=actor, run_judge=True)
        updated = self.apply_quality_result(report_id, review, actor=actor)
        return self._result_dict(updated, review)

    def approve_report(self, report_id: int, *, actor: str = "system") -> dict[str, Any]:
        if self.report_store is None:
            raise RuntimeError("ReportStore 未配置")
        report = self.report_store.get_report(report_id)
        if report is None:
            raise ValueError("报告不存在")
        if _enum_value(report.status) != ReportStatus.WAITING_REVIEW.value:
            raise ValueError("只有 waiting_review 状态的报告可以审批通过")
        if _enum_value(report.review_status) != ReportReviewStatus.PASSED.value:
            raise ValueError("质量门禁未通过的报告不能审批通过")
        updated = self.report_store.update_report_status(
            report_id,
            ReportStatus.APPROVED.value,
            actor=actor,
        )
        self._append_audit(
            updated,
            "report_approved",
            {"actor": actor},
        )
        return self._report_dict(
            updated,
            claims=self.report_store.list_report_claims(report_id),
            evidence_refs=self.report_store.list_report_evidence_refs(report_id),
            quality_reviews=self.report_store.list_quality_reviews(report_id),
        )

    def reject_report(
        self,
        report_id: int,
        *,
        reason: str = "",
        actor: str = "system",
    ) -> dict[str, Any]:
        if self.report_store is None:
            raise RuntimeError("ReportStore 未配置")
        report = self.report_store.get_report(report_id)
        if report is None:
            raise ValueError("报告不存在")
        if _enum_value(report.status) != ReportStatus.WAITING_REVIEW.value:
            raise ValueError("只有 waiting_review 状态的报告可以拒绝")
        updated = self.report_store.update_report_status(
            report_id,
            ReportStatus.REVISION_REQUIRED.value,
            actor=actor,
        )
        self._append_audit(
            updated,
            "report_rejected",
            {"actor": actor, "reason": reason},
        )
        return self._report_dict(
            updated,
            claims=self.report_store.list_report_claims(report_id),
            evidence_refs=self.report_store.list_report_evidence_refs(report_id),
            quality_reviews=self.report_store.list_quality_reviews(report_id),
        )

    def publish_report(self, report_id: int, *, actor: str = "system") -> dict[str, Any]:
        if self.report_store is None:
            raise RuntimeError("ReportStore 未配置")
        report = self.report_store.get_report(report_id)
        if report is None:
            raise ValueError("报告不存在")
        if _enum_value(report.status) != ReportStatus.APPROVED.value:
            raise ValueError("只有 approved 状态的报告可以发布")
        if _enum_value(report.review_status) != ReportReviewStatus.PASSED.value:
            raise ValueError("质量门禁未通过的报告不能发布")
        updated = self.report_store.update_report_status(
            report_id,
            ReportStatus.PUBLISHED.value,
            actor=actor,
        )
        self._append_audit(
            updated,
            "report_published",
            {"actor": actor},
        )
        return self._report_dict(
            updated,
            claims=self.report_store.list_report_claims(report_id),
            evidence_refs=self.report_store.list_report_evidence_refs(report_id),
            quality_reviews=self.report_store.list_quality_reviews(report_id),
        )

    def _build_draft_prompt(self, context: dict[str, Any]) -> str:
        competitors = context["competitors"]
        comp_names = ", ".join(getattr(comp, "name", "") for comp in competitors)
        products_text = "\n".join(
            f"[{getattr(product, 'competitor_id', '-')}] 产品: {getattr(product, 'name', '')} | "
            f"类别: {getattr(product, 'category', '')} | 定价: {getattr(product, 'pricing_info', '')}"
            for product in context["products"]
        ) or "暂无产品线数据"
        facts_text = "\n".join(
            f"- [{fact.get('fact_type')}/{fact.get('dimension')}] {fact.get('fact_text')} "
            f"(fact_id={fact.get('id')})"
            for fact in context["facts"][:80]
        ) or "暂无结构化事实"
        claims_text = "\n".join(
            f"- [{claim.get('claim_type')}/{claim.get('dimension')}] {claim.get('claim_text')} "
            f"(claim_id={claim.get('id')})"
            for claim in context["claims"][:40]
        ) or "暂无分析 claims"
        evidence_text = "\n".join(
            f"- [{self._citation_label(index)}] {item.get('title') or item.get('url') or item.get('parent_chunk_id')}: "
            f"{item.get('snippet', '')[:260]}"
            for index, item in enumerate(context["evidence_refs"][:60], start=1)
        ) or "暂无 evidence refs"
        focus_text = f"\n分析重点: {context['request']['focus']}" if context["request"]["focus"] else ""
        return f"""请基于以下结构化竞品事实、claims 和 evidence，生成一份{self._report_type_label(context['request']['report_type'])}。

## 竞品: {comp_names}{focus_text}

## 产品线
{products_text}

## Facts
{facts_text}

## Claims
{claims_text}

## Evidence
{evidence_text}

## 数据限制
{context["limitations"] or "无"}

要求:
1. 使用 Markdown，必须包含执行摘要、关键变化、对比分析、机会与风险、数据限制、证据附录。
2. 每条关键结论都要使用 evidence label，例如 [E1]。
3. 不要使用未在 facts、claims、evidence 或竞品档案中出现的产品、价格、客户或融资信息。
4. 数据不足时明确写在“数据限制”章节，不要输出确定性趋势。
5. 使用中文，保持专业客观。"""

    @staticmethod
    def _collect_evidence_refs(
        facts: list[dict[str, Any]],
        claims: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        evidence_refs: list[dict[str, Any]] = []
        seen = set()
        for owner in [*facts, *claims]:
            for evidence in owner.get("evidence_refs", []) or []:
                if not isinstance(evidence, dict):
                    continue
                evidence_id = evidence.get("id") or json.dumps(evidence, sort_keys=True, default=str)
                if evidence_id in seen:
                    continue
                seen.add(evidence_id)
                item = dict(evidence)
                item.setdefault("owner_id", owner.get("id"))
                item.setdefault(
                    "owner_type",
                    "insight_claim" if "claim_text" in owner else "intel_fact",
                )
                item.setdefault("dimension", owner.get("dimension", ""))
                evidence_refs.append(item)
        return evidence_refs

    def _append_audit(self, report: AnalysisReport, action: str, detail: dict[str, Any]) -> None:
        if self.report_store is None or report.id is None:
            return
        try:
            self.report_store.append_audit_log(report.id, report.session_id, action, detail)
        except Exception as exc:
            logger.warning("report.audit_failed", report_id=report.id, action=action, error=str(exc))

    @staticmethod
    def _result_dict(report: AnalysisReport, review) -> dict[str, Any]:
        return {
            "report_id": report.id,
            "status": _enum_value(report.status),
            "review_status": _enum_value(report.review_status),
            "quality_score": report.quality_score,
            "quality_summary": report.quality_summary,
            "blocking_issues_count": ReportService._blocking_issue_count(review.issues),
            "content": report.content,
            "issues": review.issues,
        }

    @staticmethod
    def _report_dict(
        report: AnalysisReport,
        *,
        claims: list[ReportClaimRef],
        evidence_refs: list[ReportEvidenceRef],
        quality_reviews: list[Any],
    ) -> dict[str, Any]:
        return {
            "id": report.id,
            "title": report.title,
            "report_type": _enum_value(report.report_type),
            "competitor_ids": report.competitor_ids,
            "content": report.content,
            "source_refs": report.source_refs,
            "audit_trail": report.audit_trail,
            "status": _enum_value(report.status),
            "review_status": _enum_value(report.review_status),
            "quality_score": report.quality_score,
            "quality_summary": report.quality_summary,
            "claims": [ref.__dict__ for ref in claims],
            "evidence_refs": [ref.__dict__ for ref in evidence_refs],
            "quality_reviews": [
                {
                    **review.__dict__,
                    "status": _enum_value(review.status),
                    "created_at": review.created_at.isoformat() if review.created_at else None,
                }
                for review in quality_reviews
            ],
            "session_id": report.session_id,
            "version": report.version,
            "approved_by": report.approved_by,
            "approved_at": report.approved_at.isoformat() if report.approved_at else None,
            "published_at": report.published_at.isoformat() if report.published_at else None,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "updated_at": report.updated_at.isoformat() if report.updated_at else None,
        }

    @staticmethod
    def _blocking_issue_count(issues: list[dict[str, Any]]) -> int:
        return sum(1 for issue in issues if issue.get("severity") == "blocker")

    @staticmethod
    def _quality_summary(review) -> str:
        blocking = ReportService._blocking_issue_count(review.issues)
        status = _enum_value(review.status)
        return f"{review.review_type} review {status}; score={review.overall_score:.2f}; blockers={blocking}"

    @staticmethod
    def _hash_context(context: dict[str, Any]) -> str:
        payload = {
            "request": context["request"],
            "coverage": context["coverage"],
            "limitations": context["limitations"],
            "fact_ids": [item.get("id") for item in context["facts"]],
            "claim_ids": [item.get("id") for item in context["claims"]],
            "evidence_ids": [item.get("id") for item in context["evidence_refs"]],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _safe_report_type(report_type: str) -> ReportType:
        try:
            return ReportType(report_type)
        except ValueError:
            return ReportType.OVERVIEW

    @staticmethod
    def _report_type_label(report_type: str) -> str:
        labels = {
            "overview": "竞品概览报告",
            "comparison": "竞品对比报告",
            "briefing": "市场动态简报",
            "deep_research": "深度研究报告",
        }
        return labels.get(report_type, "竞品分析报告")

    @staticmethod
    def _citation_label(index: int) -> str:
        return f"E{index}"


def _dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for item in items:
        key = item.get("id") or json.dumps(item, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value
