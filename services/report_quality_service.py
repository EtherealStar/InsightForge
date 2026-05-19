"""Report quality gate service."""
from __future__ import annotations

import json
import re
from typing import Any

import structlog

from core.protocols import (
    CompetitorStoreProtocol,
    JudgeClientProtocol,
    ReportStoreProtocol,
)
from models.report import (
    AnalysisReport,
    ReportClaimRef,
    ReportEvidenceRef,
    ReportQualityReview,
    ReportReviewStatus,
)

logger = structlog.get_logger(__name__)

_CITATION_PATTERN = re.compile(r"\[([Ee]\d+)\]")


class ReportQualityService:
    """Run rule-based and optional LLM judge checks for analysis reports."""

    prompt_version = "report-quality-v1"

    def __init__(
        self,
        report_store: ReportStoreProtocol,
        competitor_store: CompetitorStoreProtocol,
        judge_client: JudgeClientProtocol | None = None,
        *,
        min_score: float = 0.75,
        min_grounding: float = 0.8,
        min_citation_accuracy: float = 0.8,
        judge_temperature: float = 0.0,
    ):
        self.report_store = report_store
        self.competitor_store = competitor_store
        self.judge_client = judge_client
        self.min_score = min_score
        self.min_grounding = min_grounding
        self.min_citation_accuracy = min_citation_accuracy
        self.judge_temperature = judge_temperature

    def review_report(
        self,
        report_id: int,
        *,
        actor: str = "system",
        run_judge: bool = True,
        context: dict[str, Any] | None = None,
    ) -> ReportQualityReview:
        report = self.report_store.get_report(report_id)
        if report is None:
            raise ValueError(f"Report not found: {report_id}")
        claim_refs = self.report_store.list_report_claims(report_id)
        evidence_refs = self.report_store.list_report_evidence_refs(report_id)

        rule_review = self.run_rule_gate(
            report,
            claim_refs,
            evidence_refs,
            context=context,
            actor=actor,
        )
        if _enum_value(rule_review.status) == ReportReviewStatus.FAILED.value:
            return rule_review
        if not run_judge:
            return rule_review
        return self.run_judge_review(
            report,
            claim_refs,
            evidence_refs,
            actor=actor,
        )

    def run_rule_gate(
        self,
        report: AnalysisReport,
        claim_refs: list[ReportClaimRef],
        evidence_refs: list[ReportEvidenceRef],
        *,
        context: dict[str, Any] | None = None,
        actor: str = "system",
    ) -> ReportQualityReview:
        issues: list[dict[str, Any]] = []
        content = (report.content or "").strip()
        citation_labels = {ref.citation_label for ref in evidence_refs if ref.citation_label}
        content_citations = {match.upper() for match in _CITATION_PATTERN.findall(content)}

        if not content:
            issues.append(_issue("blocker", "empty_report", "报告正文为空。"))
        elif not self._has_section_heading(content):
            issues.append(
                _issue("blocker", "invalid_structure", "报告正文缺少 Markdown 章节标题。")
            )

        for competitor_id in report.competitor_ids:
            if self.competitor_store.get_competitor(competitor_id) is None:
                issues.append(
                    _issue(
                        "blocker",
                        "invalid_competitor",
                        f"报告涉及的竞品不存在: {competitor_id}",
                    )
                )

        if not evidence_refs:
            issues.append(
                _issue("blocker", "missing_evidence", "报告没有绑定任何 evidence 引用。")
            )

        for ref in evidence_refs:
            if not self._evidence_has_trace(ref):
                issues.append(
                    _issue(
                        "blocker",
                        "untraceable_evidence",
                        f"证据 {ref.citation_label or ref.id} 无法回链到来源。",
                        section_key=ref.section_key,
                        evidence_ref_ids=[ref.evidence_ref_id or ref.id],
                    )
                )

        missing_citations = sorted(
            label for label in content_citations if label not in {v.upper() for v in citation_labels}
        )
        for label in missing_citations:
            issues.append(
                _issue("blocker", "bad_citation", f"正文引用 [{label}] 未绑定 evidence。")
            )

        if claim_refs and not evidence_refs:
            issues.append(
                _issue(
                    "blocker",
                    "unsupported_claim",
                    "报告绑定了 claim，但没有绑定可追溯 evidence。",
                )
            )

        limitations = context.get("limitations") if context else None
        if limitations and not self._mentions_limitations(content):
            issues.append(
                _issue(
                    "blocker",
                    "missing_limitation",
                    "上下文存在数据限制，但报告未显式说明 limitations。",
                )
            )

        source_count = len(
            {
                ref.url or ref.evidence_ref_id or f"{ref.report_id}:{ref.fact_id}:{ref.claim_id}"
                for ref in evidence_refs
            }
        )
        if evidence_refs and source_count < 3:
            issues.append(
                _issue(
                    "minor",
                    "low_source_coverage",
                    "报告独立来源少于 3 个，建议人工复核来源覆盖。",
                )
            )

        status = (
            ReportReviewStatus.FAILED
            if any(issue.get("severity") == "blocker" for issue in issues)
            else ReportReviewStatus.PASSED
        )
        overall_score = 1.0 if status == ReportReviewStatus.PASSED else 0.0
        if status == ReportReviewStatus.PASSED and source_count < 3:
            overall_score = 0.85

        review = ReportQualityReview(
            report_id=report.id or 0,
            review_type="rule",
            status=status,
            overall_score=overall_score,
            dimension_scores={
                "grounding": 1.0 if evidence_refs else 0.0,
                "citation_accuracy": 1.0 if not missing_citations else 0.0,
                "completeness": 1.0 if self._has_section_heading(content) else 0.0,
            },
            issues=issues,
            revision_suggestions=[
                {"message": issue["message"], "category": issue["category"]}
                for issue in issues
                if issue.get("severity") in {"blocker", "major"}
            ],
            prompt_version=self.prompt_version,
            reviewed_by=actor,
        )
        saved = self.report_store.save_quality_review(review)
        self._append_audit(
            report,
            "report_quality_rule_reviewed",
            saved,
            blocking_count=sum(1 for issue in issues if issue.get("severity") == "blocker"),
        )
        return saved

    def run_judge_review(
        self,
        report: AnalysisReport,
        claim_refs: list[ReportClaimRef],
        evidence_refs: list[ReportEvidenceRef],
        *,
        actor: str = "system",
    ) -> ReportQualityReview:
        if self.judge_client is None:
            review = ReportQualityReview(
                report_id=report.id or 0,
                review_type="llm",
                status=ReportReviewStatus.NEEDS_HUMAN,
                overall_score=0.0,
                issues=[
                    _issue(
                        "major",
                        "judge_unavailable",
                        "Judge 客户端未配置，报告需要人工复核。",
                    )
                ],
                revision_suggestions=[],
                prompt_version=self.prompt_version,
                reviewed_by=actor,
            )
            saved = self.report_store.save_quality_review(review)
            self._append_audit(report, "report_quality_judge_reviewed", saved, blocking_count=0)
            return saved

        try:
            payload = self.judge_client.judge_json(
                self._judge_system_prompt(),
                self._judge_user_message(report, claim_refs, evidence_refs),
                schema_name="report_quality_review",
                temperature=self.judge_temperature,
            )
        except Exception as exc:
            logger.warning("report_quality.judge_failed", report_id=report.id, error=str(exc))
            return self._save_failed_judge_review(report, actor, f"Judge 调用失败: {exc}")

        if not isinstance(payload, dict):
            return self._save_failed_judge_review(report, actor, "Judge 返回不是 JSON object。")

        try:
            overall_score = _safe_score(payload.get("overall_score"))
            dimension_scores = dict(payload.get("dimension_scores") or {})
            issues = list(payload.get("issues") or [])
            revision_suggestions = list(payload.get("revision_suggestions") or [])
        except Exception as exc:
            return self._save_failed_judge_review(report, actor, f"Judge JSON 解析失败: {exc}")

        normalized_scores = {
            str(key): _safe_score(value)
            for key, value in dimension_scores.items()
        }
        blocker_issues = [
            issue
            for issue in issues
            if str(issue.get("severity", "")).lower() == "blocker"
        ]
        grounding = normalized_scores.get("grounding", overall_score)
        citation_accuracy = normalized_scores.get("citation_accuracy", overall_score)
        passed = (
            not blocker_issues
            and overall_score >= self.min_score
            and grounding >= self.min_grounding
            and citation_accuracy >= self.min_citation_accuracy
        )
        status = ReportReviewStatus.PASSED if passed else ReportReviewStatus.FAILED
        review = ReportQualityReview(
            report_id=report.id or 0,
            review_type="llm",
            status=status,
            overall_score=overall_score,
            dimension_scores=normalized_scores,
            issues=issues,
            revision_suggestions=revision_suggestions,
            model_provider=str(payload.get("model_provider", "")),
            model_name=str(payload.get("model_name", "")),
            prompt_version=str(payload.get("prompt_version") or self.prompt_version),
            reviewed_by=actor,
        )
        saved = self.report_store.save_quality_review(review)
        self._append_audit(
            report,
            "report_quality_judge_reviewed",
            saved,
            blocking_count=len(blocker_issues),
        )
        return saved

    @staticmethod
    def _has_section_heading(content: str) -> bool:
        return any(line.lstrip().startswith("#") for line in content.splitlines())

    @staticmethod
    def _mentions_limitations(content: str) -> bool:
        lowered = content.lower()
        return any(token in lowered for token in ("限制", "不足", "局限", "limitations", "数据限制"))

    @staticmethod
    def _evidence_has_trace(ref: ReportEvidenceRef) -> bool:
        if ref.evidence_ref_id:
            return True
        if ref.url:
            return True
        return False

    def _save_failed_judge_review(
        self,
        report: AnalysisReport,
        actor: str,
        message: str,
    ) -> ReportQualityReview:
        review = ReportQualityReview(
            report_id=report.id or 0,
            review_type="llm",
            status=ReportReviewStatus.FAILED,
            overall_score=0.0,
            dimension_scores={},
            issues=[_issue("blocker", "judge_parse_failed", message)],
            revision_suggestions=[{"message": "重新运行 Judge 或转人工复核。"}],
            prompt_version=self.prompt_version,
            reviewed_by=actor,
        )
        saved = self.report_store.save_quality_review(review)
        self._append_audit(report, "report_quality_judge_reviewed", saved, blocking_count=1)
        return saved

    def _append_audit(
        self,
        report: AnalysisReport,
        action: str,
        review: ReportQualityReview,
        *,
        blocking_count: int,
    ) -> None:
        if report.id is None:
            return
        try:
            self.report_store.append_audit_log(
                report.id,
                report.session_id,
                action,
                {
                    "review_id": review.id,
                    "review_type": review.review_type,
                    "status": _enum_value(review.status),
                    "overall_score": review.overall_score,
                    "issue_count": len(review.issues),
                    "blocking_issues_count": blocking_count,
                },
            )
        except Exception as exc:
            logger.warning("report_quality.audit_failed", report_id=report.id, error=str(exc))

    @staticmethod
    def _judge_system_prompt() -> str:
        return (
            "你是企业竞品分析报告质量审查员。只输出 JSON，检查 grounding、"
            "citation_accuracy、completeness、contradiction、hallucination_risk、"
            "business_usefulness 和 limitations_quality。"
        )

    @staticmethod
    def _judge_user_message(
        report: AnalysisReport,
        claim_refs: list[ReportClaimRef],
        evidence_refs: list[ReportEvidenceRef],
    ) -> str:
        payload = {
            "report": {
                "id": report.id,
                "title": report.title,
                "competitor_ids": report.competitor_ids,
                "content": report.content,
            },
            "claim_refs": [ref.__dict__ for ref in claim_refs],
            "evidence_refs": [ref.__dict__ for ref in evidence_refs],
            "required_json_shape": {
                "overall_score": 0.0,
                "dimension_scores": {
                    "grounding": 0.0,
                    "citation_accuracy": 0.0,
                    "completeness": 0.0,
                    "contradiction": 0.0,
                    "hallucination_risk": 0.0,
                    "business_usefulness": 0.0,
                    "limitations_quality": 0.0,
                },
                "issues": [],
                "revision_suggestions": [],
            },
        }
        return json.dumps(payload, ensure_ascii=False, default=str)


def _issue(
    severity: str,
    category: str,
    message: str,
    *,
    section_key: str = "",
    claim_id: str | None = None,
    evidence_ref_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "category": category,
        "section_key": section_key,
        "claim_id": claim_id,
        "message": message,
        "evidence_ref_ids": evidence_ref_ids or [],
    }


def _safe_score(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"invalid score: {value!r}")
    return max(0.0, min(1.0, parsed))


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value
