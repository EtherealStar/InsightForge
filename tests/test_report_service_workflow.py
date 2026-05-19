from types import SimpleNamespace

from models.report import AnalysisReport, ReportReviewStatus, ReportStatus
from services.report_quality_service import ReportQualityService
from services.report_service import ReportService


class FakeCompetitorStore:
    def get_competitor(self, competitor_id):
        if competitor_id == 1:
            return SimpleNamespace(id=1, name="Cursor")
        return None

    def list_products(self, competitor_id):
        return []


class FakeIntelService:
    def __init__(self, facts):
        self.facts = facts

    def list_facts(self, filters, limit=100):
        return self.facts


class FakeInsightService:
    def __init__(self, claims=None):
        self.claims = claims or []

    def list_claims(self, filters, limit=50):
        return self.claims

    def build_claims_from_facts(self, filters, max_claims=10):
        return []


class FakeLLM:
    def generate(self, system_prompt, user_message):
        return "# 执行摘要\nCursor 有新能力 [E1]\n\n## 数据限制\n仅基于公开来源。"


class PassingJudge:
    def judge_json(self, *args, **kwargs):
        return {
            "overall_score": 0.91,
            "dimension_scores": {"grounding": 0.9, "citation_accuracy": 0.92},
            "issues": [],
            "revision_suggestions": [],
        }


class MemoryReportStore:
    def __init__(self):
        self.report = None
        self.claim_refs = []
        self.evidence_refs = []
        self.reviews = []
        self.audit = []

    def save_report(self, report):
        report.id = 1
        self.report = report
        return report

    def get_report(self, report_id):
        return self.report if self.report and report_id == self.report.id else None

    def update_report_status(
        self,
        report_id,
        status,
        *,
        review_status=None,
        quality_score=None,
        quality_summary=None,
        actor="system",
    ):
        self.report.status = ReportStatus(status)
        if review_status is not None:
            self.report.review_status = ReportReviewStatus(review_status)
        if quality_score is not None:
            self.report.quality_score = quality_score
        if quality_summary is not None:
            self.report.quality_summary = quality_summary
        return self.report

    def attach_claims(self, report_id, claim_refs):
        self.claim_refs.extend(claim_refs)

    def list_report_claims(self, report_id):
        return self.claim_refs

    def attach_evidence_refs(self, report_id, evidence_refs):
        self.evidence_refs.extend(evidence_refs)

    def list_report_evidence_refs(self, report_id):
        return self.evidence_refs

    def save_quality_review(self, review):
        self.reviews.append(review)
        return review

    def list_quality_reviews(self, report_id):
        return self.reviews

    def append_audit_log(self, report_id, session_id, action, detail, source_refs=None):
        self.audit.append((action, detail))


def _fact_with_evidence():
    return {
        "id": "fact1",
        "fact_type": "feature_release",
        "dimension": "product",
        "fact_text": "Cursor released a feature.",
        "evidence_refs": [
            {
                "id": "ev1",
                "owner_type": "intel_fact",
                "owner_id": "fact1",
                "url": "https://example.com",
                "title": "Cursor source",
                "snippet": "Cursor released a feature.",
            }
        ],
    }


def _build_service(facts, judge_client=None):
    report_store = MemoryReportStore()
    competitor_store = FakeCompetitorStore()
    quality_service = ReportQualityService(
        report_store,
        competitor_store,
        judge_client=judge_client,
    )
    return ReportService(
        competitor_store=competitor_store,
        intel_service=FakeIntelService(facts),
        insight_service=FakeInsightService(),
        llm_client=FakeLLM(),
        report_store=report_store,
        quality_service=quality_service,
    ), report_store


def test_generate_report_with_passing_quality_waits_for_review():
    service, store = _build_service([_fact_with_evidence()], judge_client=PassingJudge())

    result = service.generate_analysis_report([1])

    assert result["report_id"] == 1
    assert result["status"] == "waiting_review"
    assert result["review_status"] == "passed"
    assert result["quality_score"] == 0.91
    assert result["blocking_issues_count"] == 0
    assert store.report.status == ReportStatus.WAITING_REVIEW
    assert store.evidence_refs[0].citation_label == "E1"


def test_generate_report_quality_failure_requires_revision():
    service, store = _build_service([])

    result = service.generate_analysis_report([1])

    assert result["status"] == "revision_required"
    assert result["review_status"] == "failed"
    assert result["blocking_issues_count"] > 0
    assert store.report.status == ReportStatus.REVISION_REQUIRED


def test_auto_publish_true_does_not_publish_when_quality_fails():
    service, store = _build_service([])

    result = service.generate_analysis_report([1], auto_publish=True)

    assert result["status"] == "revision_required"
    assert store.report.status != ReportStatus.PUBLISHED


def test_waiting_review_passed_report_can_be_approved_and_published():
    service, store = _build_service([_fact_with_evidence()], judge_client=PassingJudge())
    service.generate_analysis_report([1])

    approved = service.approve_report(1, actor="admin")
    published = service.publish_report(1, actor="admin")

    assert approved["status"] == "approved"
    assert published["status"] == "published"
    assert [item[0] for item in store.audit][-2:] == ["report_approved", "report_published"]


def test_quality_failed_report_cannot_be_approved():
    service, store = _build_service([])
    service.generate_analysis_report([1])

    try:
        service.approve_report(1, actor="admin")
    except ValueError as exc:
        assert "waiting_review" in str(exc) or "质量门禁" in str(exc)
    else:
        raise AssertionError("expected approve_report to reject failed report")

    assert store.report.status == ReportStatus.REVISION_REQUIRED


def test_waiting_review_report_can_be_rejected():
    service, store = _build_service([_fact_with_evidence()], judge_client=PassingJudge())
    service.generate_analysis_report([1])

    result = service.reject_report(1, reason="needs changes", actor="admin")

    assert result["status"] == "revision_required"
    assert store.report.status == ReportStatus.REVISION_REQUIRED
    assert store.audit[-1][0] == "report_rejected"
