import os
from datetime import date
from pathlib import Path

import psycopg2
import pytest

from infrastructure.competitor_store import PostgresCompetitorStore
from infrastructure.document_store import PostgresDocumentStore
from infrastructure.insight_store import PostgresInsightStore
from infrastructure.intel_store import PostgresIntelStore
from infrastructure.report_store import PostgresReportStore
from models.competitor import Competitor, CompetitorProduct
from models.document import ParentDocumentChunk, SourceDocument
from models.evidence import EvidenceOwnerType, EvidenceRef
from models.insight import ClaimType, InsightClaim
from models.intel import FactType, IntelDimension, IntelFact
from models.report import (
    AnalysisReport,
    ReportClaimRef,
    ReportEvidenceRef,
    ReportQualityReview,
    ReportReviewStatus,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_PG_DSN"), reason="Requires PostgreSQL instance"
)


def _apply_sql(test_dsn: str, filename: str) -> None:
    sql = Path("migrations", filename).read_text(encoding="utf-8")
    with psycopg2.connect(test_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)


@pytest.fixture(autouse=True)
def migrated_db(test_dsn):
    _apply_sql(test_dsn, "001_infrastructure_foundation.sql")
    _apply_sql(test_dsn, "003_competitive_analysis_schema.sql")
    _apply_sql(test_dsn, "004_intel_fact_schema.sql")
    _apply_sql(test_dsn, "005_report_quality_security_schema.sql")
    with psycopg2.connect(test_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE TABLE
                    evidence_refs,
                    report_quality_reviews,
                    report_evidence_refs,
                    report_claims,
                    config_audit_log,
                    api_keys,
                    analysis_audit_log,
                    analysis_reports,
                    insight_claims,
                    intel_fact_products,
                    intel_fact_competitors,
                    intel_facts,
                    competitor_products,
                    competitors,
                    document_vector_points,
                    document_parent_chunks,
                    source_documents,
                    document_blobs,
                    upload_batches
                RESTART IDENTITY CASCADE
                """
            )
    yield


def test_migration_creates_new_schema_and_removes_legacy_objects(test_dsn):
    with psycopg2.connect(test_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'intel_facts', 'intel_fact_competitors',
                      'intel_fact_products', 'evidence_refs', 'insight_claims'
                      , 'report_claims', 'report_evidence_refs',
                      'report_quality_reviews', 'config_audit_log', 'api_keys'
                  )
                """
            )
            tables = {row[0] for row in cur.fetchall()}
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'source_documents'
                  AND column_name IN ('intel_type', 'analysis_notes', 'source_reliability')
                """
            )
            legacy_columns = {row[0] for row in cur.fetchall()}
            cur.execute("SELECT to_regclass('public.intel_competitors')")
            old_competitors = cur.fetchone()[0]
            cur.execute("SELECT to_regclass('public.intel_products')")
            old_products = cur.fetchone()[0]

    assert tables == {
        "intel_facts",
        "intel_fact_competitors",
        "intel_fact_products",
        "evidence_refs",
        "insight_claims",
        "report_claims",
        "report_evidence_refs",
        "report_quality_reviews",
        "config_audit_log",
        "api_keys",
    }
    assert legacy_columns == set()
    assert old_competitors is None
    assert old_products is None


def test_intel_store_crud_filters_links_and_evidence(test_dsn):
    document_store = PostgresDocumentStore(test_dsn)
    competitor_store = PostgresCompetitorStore(test_dsn)
    store = PostgresIntelStore(test_dsn)

    document = document_store.save_document(
        SourceDocument(
            document_id="11111111-1111-1111-1111-111111111111",
            title="Cursor release",
            content="Cursor released a feature.",
            parse_status="vectorized",
        )
    )
    document_store.save_parent_chunks(
        [
            ParentDocumentChunk(
                parent_chunk_id="p-1",
                document_id=document.document_id,
                content="Cursor released a feature.",
                token_count=5,
            )
        ]
    )
    competitor = competitor_store.save_competitor(Competitor(name="Cursor"))
    product = competitor_store.save_product(
        CompetitorProduct(competitor_id=competitor.id, name="Cursor IDE")
    )
    fact = store.save_fact(
        IntelFact(
            source_document_id=document.document_id,
            fact_type=FactType.FEATURE_RELEASE,
            dimension=IntelDimension.PRODUCT,
            subject="Cursor",
            predicate="released",
            object="feature",
            fact_text="Cursor released a feature.",
            event_date=date(2026, 5, 1),
            confidence_score=0.9,
            assertion_key="cursor:released:feature",
        )
    )
    store.link_fact_to_competitor(fact.id, competitor.id)
    store.link_fact_to_product(fact.id, product.id)
    evidence = store.save_evidence(
        EvidenceRef(
            owner_type=EvidenceOwnerType.INTEL_FACT,
            owner_id=fact.id,
            source_document_id=document.document_id,
            parent_chunk_id="p-1",
            snippet="Cursor released a feature.",
        )
    )

    loaded = store.get_fact(fact.id)
    filtered = store.list_facts(
        {
            "competitor_id": competitor.id,
            "product_id": product.id,
            "fact_type": FactType.FEATURE_RELEASE.value,
            "dimension": IntelDimension.PRODUCT.value,
            "status": "draft",
            "event_date_from": "2026-01-01",
            "event_date_to": "2026-12-31",
            "keyword": "feature",
        }
    )
    saved_evidence = store.list_evidence(EvidenceOwnerType.INTEL_FACT.value, fact.id)

    assert loaded is not None
    assert loaded.competitor_ids == [competitor.id]
    assert loaded.product_ids == [product.id]
    assert loaded.evidence_refs == [evidence.id]
    assert [item.id for item in filtered] == [fact.id]
    assert saved_evidence[0].snippet == "Cursor released a feature."

    active = store.update_fact_status(fact.id, "active")
    assert active.status.value == "active"
    store.unlink_fact_from_competitor(fact.id, competitor.id)
    store.delete_fact(fact.id)
    assert store.get_fact(fact.id) is None


def test_insight_store_crud_filters_and_evidence(test_dsn):
    store = PostgresInsightStore(test_dsn)
    claim = store.save_claim(
        InsightClaim(
            claim_text="Cursor is moving faster on product releases.",
            claim_type=ClaimType.TREND,
            dimension="product",
            competitor_ids=[1],
            fact_ids=["fact-1"],
            confidence_score=0.7,
        )
    )
    evidence = store.attach_evidence(
        claim.id,
        EvidenceRef(
            owner_type=EvidenceOwnerType.INSIGHT_CLAIM,
            owner_id=claim.id,
            url="https://example.com",
            snippet="release evidence",
        ),
    )

    loaded = store.get_claim(claim.id)
    filtered = store.list_claims(
        {
            "competitor_id": 1,
            "claim_type": ClaimType.TREND.value,
            "dimension": "product",
            "status": "draft",
            "fact_id": "fact-1",
        }
    )

    assert loaded is not None
    assert loaded.evidence_refs[0]["id"] == evidence.id
    assert [item.id for item in filtered] == [claim.id]
    active = store.update_claim_status(claim.id, "active")
    assert active.status.value == "active"
    store.delete_claim(claim.id)
    assert store.get_claim(claim.id) is None


def test_report_store_phase3_relationships_and_reviews(test_dsn):
    insight_store = PostgresInsightStore(test_dsn)
    report_store = PostgresReportStore(test_dsn)
    claim = insight_store.save_claim(
        InsightClaim(
            claim_text="Cursor is improving product velocity.",
            claim_type=ClaimType.FINDING,
            dimension="product",
            competitor_ids=[1],
            fact_ids=["fact-1"],
        )
    )
    evidence = insight_store.attach_evidence(
        claim.id,
        EvidenceRef(
            owner_type=EvidenceOwnerType.INSIGHT_CLAIM,
            owner_id=claim.id,
            url="https://example.com/cursor",
            title="Cursor release",
            snippet="Cursor shipped a product update.",
        ),
    )
    report = report_store.save_report(
        AnalysisReport(
            title="Cursor report",
            competitor_ids=[1],
            content="# Cursor",
            quality_summary="not reviewed",
        )
    )

    report_store.attach_claims(
        report.id,
        [
            ReportClaimRef(
                report_id=report.id,
                claim_id=claim.id,
                section_key="executive_summary",
                position=1,
                usage_type="key_finding",
            )
        ],
    )
    report_store.attach_evidence_refs(
        report.id,
        [
            ReportEvidenceRef(
                report_id=report.id,
                evidence_ref_id=evidence.id,
                claim_id=claim.id,
                section_key="executive_summary",
                citation_label="[E1]",
                url=evidence.url,
                title=evidence.title,
                snippet=evidence.snippet,
            )
        ],
    )
    review = report_store.save_quality_review(
        ReportQualityReview(
            report_id=report.id,
            review_type="rule",
            status=ReportReviewStatus.PASSED,
            overall_score=0.9,
            dimension_scores={"grounding": 0.9},
            issues=[],
            revision_suggestions=[],
        )
    )
    updated = report_store.update_report_status(
        report.id,
        "waiting_review",
        review_status="passed",
        quality_score=0.9,
        quality_summary="规则门禁通过",
    )

    assert updated.review_status == ReportReviewStatus.PASSED
    assert updated.quality_score == 0.9
    assert report_store.list_report_claims(report.id)[0].claim_id == claim.id
    assert report_store.list_report_evidence_refs(report.id)[0].citation_label == "[E1]"
    assert report_store.list_quality_reviews(report.id)[0].id == review.id
