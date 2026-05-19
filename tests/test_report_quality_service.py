from types import SimpleNamespace

from models.report import (
    AnalysisReport,
    ReportEvidenceRef,
    ReportQualityReview,
    ReportReviewStatus,
    ReportStatus,
)
from services.report_quality_service import ReportQualityService


class FakeCompetitorStore:
    def __init__(self, existing=(1,)):
        self.existing = set(existing)

    def get_competitor(self, competitor_id):
        return SimpleNamespace(id=competitor_id) if competitor_id in self.existing else None


class FakeReportStore:
    def __init__(self, report=None, evidence_refs=None):
        self.report = report or AnalysisReport(
            id=1,
            title="Report",
            competitor_ids=[1],
            content="# Report\nFinding [E1]",
        )
        self.claim_refs = []
        self.evidence_refs = evidence_refs or []
        self.reviews = []
        self.audit = []

    def get_report(self, report_id):
        return self.report if report_id == self.report.id else None

    def list_report_claims(self, report_id):
        return self.claim_refs

    def list_report_evidence_refs(self, report_id):
        return self.evidence_refs

    def save_quality_review(self, review):
        self.reviews.append(review)
        return review

    def append_audit_log(self, report_id, session_id, action, detail, source_refs=None):
        self.audit.append((action, detail))


class BadJudge:
    def judge_json(self, *args, **kwargs):
        return []


class LowScoreJudge:
    def judge_json(self, *args, **kwargs):
        return {
            "overall_score": 0.4,
            "dimension_scores": {"grounding": 0.9, "citation_accuracy": 0.9},
            "issues": [],
            "revision_suggestions": [],
        }


def _evidence(label="E1", url="https://example.com", evidence_ref_id="ev1"):
    return ReportEvidenceRef(
        report_id=1,
        evidence_ref_id=evidence_ref_id,
        citation_label=label,
        url=url,
        title="Source",
        snippet="Source text",
    )


def test_rule_gate_blocks_report_without_evidence():
    store = FakeReportStore(evidence_refs=[])
    service = ReportQualityService(store, FakeCompetitorStore())

    review = service.review_report(1, run_judge=False)

    assert review.status == ReportReviewStatus.FAILED
    assert any(issue["category"] == "missing_evidence" for issue in review.issues)


def test_rule_gate_blocks_missing_citation_label():
    store = FakeReportStore(evidence_refs=[_evidence(label="E1")])
    store.report.content = "# Report\nFinding [E2]"
    service = ReportQualityService(store, FakeCompetitorStore())

    review = service.review_report(1, run_judge=False)

    assert review.status == ReportReviewStatus.FAILED
    assert any(issue["category"] == "bad_citation" for issue in review.issues)


def test_rule_gate_blocks_untraceable_evidence():
    store = FakeReportStore(evidence_refs=[_evidence(evidence_ref_id=None, url="")])
    service = ReportQualityService(store, FakeCompetitorStore())

    review = service.review_report(1, run_judge=False)

    assert review.status == ReportReviewStatus.FAILED
    assert any(issue["category"] == "untraceable_evidence" for issue in review.issues)


def test_rule_gate_blocks_missing_competitor():
    store = FakeReportStore(evidence_refs=[_evidence()])
    service = ReportQualityService(store, FakeCompetitorStore(existing=()))

    review = service.review_report(1, run_judge=False)

    assert review.status == ReportReviewStatus.FAILED
    assert any(issue["category"] == "invalid_competitor" for issue in review.issues)


def test_judge_malformed_json_fails_review():
    store = FakeReportStore(evidence_refs=[_evidence()])
    service = ReportQualityService(store, FakeCompetitorStore(), judge_client=BadJudge())

    review = service.review_report(1, run_judge=True)

    assert review.status == ReportReviewStatus.FAILED
    assert any(issue["category"] == "judge_parse_failed" for issue in review.issues)


def test_judge_low_score_fails_review():
    store = FakeReportStore(evidence_refs=[_evidence()])
    service = ReportQualityService(store, FakeCompetitorStore(), judge_client=LowScoreJudge())

    review = service.review_report(1, run_judge=True)

    assert review.status == ReportReviewStatus.FAILED
    assert review.overall_score == 0.4
