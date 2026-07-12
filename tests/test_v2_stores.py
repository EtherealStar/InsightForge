"""V2 Intel/Insight store tests against a real PostgreSQL.

Skipped unless TEST_PG_DSN is set. Uses a dedicated database per test.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

import psycopg2
import pytest

from core.exceptions import StoreError
from core.protocols_v2 import (
    InsightStoreV2Protocol,
    IntelStoreV2Protocol,
)
from infrastructure.insight_store_v2 import PostgresInsightStoreV2
from infrastructure.intel_store_v2 import PostgresIntelStoreV2
from models.target_evidence import EvidenceReference
from models.target_insight import ClaimFactLink, ClaimMaturity, InsightClaim
from models.target_intel import (
    FactEntityRole,
    FactEvidenceLink,
    FactLifecycleStatus,
    IntelFact,
    IntelFactCompetitorLink,
    IntelFactProductLink,
    LinkReviewStatus,
    TimePrecision,
    VerificationStatus,
)


PG_DSN = os.getenv("PG_DSN")


def _setup_db():
    """Create a fresh database with migrations applied and return its DSN."""
    assert PG_DSN, "PG_DSN must point to a writable test PostgreSQL"
    base, _, name = PG_DSN.rpartition("/")
    test_name = f"logos_v2_{uuid.uuid4().hex[:10]}"
    admin = psycopg2.connect(PG_DSN)
    admin.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = admin.cursor()
    cur.execute(f"CREATE DATABASE {test_name}")
    admin.close()
    return f"{base}/{test_name}", test_name


def _teardown_db(name):
    admin = psycopg2.connect(PG_DSN)
    admin.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = admin.cursor()
    cur.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = %s AND pid <> pg_backend_pid()",
        (name,),
    )
    cur.execute(f"DROP DATABASE IF EXISTS {name}")
    admin.close()


@pytest.fixture
def stores():
    if not PG_DSN:
        pytest.skip("PG_DSN not set")
    import subprocess
    import sys as _sys

    dsn, name = _setup_db()
    # Apply migrations using the same interpreter that runs pytest so venv
    # packages (psycopg2) are available.
    result = subprocess.run(
        [_sys.executable, "migrations/apply_migrations.py"],
        env={**os.environ, "PG_DSN": dsn, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        _teardown_db(name)
        pytest.fail(f"migrations failed: {result.stdout}\n{result.stderr}")
    intel = PostgresIntelStoreV2(dsn)
    insight = PostgresInsightStoreV2(dsn)
    try:
        yield dsn, intel, insight
    finally:
        _teardown_db(name)


def _create_versioned_document(dsn, content):
    """Helper: insert a minimal cluster + occurrence + active version, return ids."""
    cluster_id = f"cl-{uuid.uuid4().hex[:8]}"
    occ_id = f"occ-{uuid.uuid4().hex[:8]}"
    ver_id = f"ver-{uuid.uuid4().hex[:8]}"
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    # Insert cluster without active_version_id first.
    cur.execute(
        "INSERT INTO document_clusters (id) VALUES (%s)",
        (cluster_id,),
    )
    cur.execute(
        """INSERT INTO source_occurrences
           (id, document_id, url, normalized_url, content_hash, simhash,
            high_bands, gray_bands, algorithm_version, source_tier, source_kind)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            occ_id, cluster_id, "https://example.com/" + cluster_id,
            "https://example.com/" + cluster_id,
            "h" * 64, 0, [1, 2, 3], [0, 0, 0, 0], "v1", "B", "news",
        ),
    )
    cur.execute(
        """INSERT INTO source_document_versions
           (id, document_id, version, content, content_hash, status)
           VALUES (%s,%s,1,%s,%s,'active')""",
        (ver_id, cluster_id, content, "h" * 64),
    )
    cur.execute(
        "UPDATE document_clusters SET active_version_id = %s WHERE id = %s",
        (ver_id, cluster_id),
    )
    conn.close()
    return cluster_id, occ_id, ver_id


def _create_competitor(dsn, name="Cursor"):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO competitors (name, status) VALUES (%s, 'active') RETURNING id",
        (name,),
    )
    cid = cur.fetchone()[0]
    conn.close()
    return cid


def test_intel_store_satisfies_protocol():
    store = PostgresIntelStoreV2("postgresql://example")
    assert isinstance(store, IntelStoreV2Protocol)


def test_insight_store_satisfies_protocol():
    store = PostgresInsightStoreV2("postgresql://example")
    assert isinstance(store, InsightStoreV2Protocol)


def test_save_fact_then_get(stores):
    dsn, intel, _insight = stores
    fact = IntelFact(
        fact_type="commercial",
        fact_text="Cursor Pro price changed to 20 USD/month.",
        candidate_key="cursor:pricing:2026-01",
        lifecycle_status=FactLifecycleStatus.DRAFT,
        time_precision=TimePrecision.MONTH,
        created_by="test",
    )
    saved = intel.save_fact(fact)
    assert saved.id == fact.id
    fetched = intel.get_fact(saved.id)
    assert fetched.fact_text == fact.fact_text
    assert fetched.fact_type == "commercial"
    assert fetched.lifecycle_status == "draft"
    assert fetched.candidate_key == "cursor:pricing:2026-01"


def test_save_fact_normalized_data_roundtrip(stores):
    dsn, intel, _ = stores
    payload = {
        "schema": "commercial.pricing.v1",
        "amount": 20,
        "currency": "USD",
        "billing_period": "month",
        "market": "US",
    }
    fact = IntelFact(
        fact_type="commercial",
        fact_text="price",
        normalized_data=payload,
        lifecycle_status="draft",
    )
    saved = intel.save_fact(fact)
    out = intel.get_fact(saved.id)
    assert out.normalized_data == payload


def test_active_fact_is_immutable(stores):
    dsn, intel, _ = stores
    fact = IntelFact(
        fact_type="commercial",
        fact_text="v1",
        lifecycle_status="draft",
    )
    saved = intel.save_fact(fact)
    intel.update_fact_lifecycle(saved.id, FactLifecycleStatus.ACTIVE)
    # Try to mutate the text via save_fact (which uses ON CONFLICT UPDATE).
    mutated = IntelFact(
        id=saved.id,
        fact_type="commercial",
        fact_text="v2",
        lifecycle_status="draft",
    )
    with pytest.raises(StoreError):
        intel.save_fact(mutated)


def test_evidence_anchor_validates_locator(stores):
    dsn, intel, _ = stores
    cluster, occ, ver = _create_versioned_document(
        dsn, "Cursor Pro costs 20 USD/month in the US market."
    )
    quote = "20 USD/month"
    start = dsn and "Cursor Pro costs ".__len__()  # noqa
    anchor = EvidenceReference(
        document_version_id=ver,
        source_occurrence_id=occ,
        quoted_text=quote,
        locator={"kind": "char_range", "start": 16, "end": 16 + len(quote)},
    )
    saved = intel.save_evidence_reference(anchor)
    assert saved.id == anchor.id
    assert saved.quote_hash != ""
    found = intel.find_evidence_by_anchor(ver, occ, saved.quote_hash)
    assert found is not None
    assert found.id == anchor.id


def test_link_fact_evidence_supports_then_contradicts(stores):
    dsn, intel, _ = stores
    cluster, occ, ver = _create_versioned_document(dsn, "Quote A. Quote B.")
    fact = IntelFact(fact_type="commercial", fact_text="x", lifecycle_status="draft")
    fact = intel.save_fact(fact)
    e1 = intel.save_evidence_reference(
        EvidenceReference(
            document_version_id=ver,
            source_occurrence_id=occ,
            quoted_text="Quote A.",
            locator={"kind": "char_range", "start": 0, "end": 8},
        )
    )
    e2 = intel.save_evidence_reference(
        EvidenceReference(
            document_version_id=ver,
            source_occurrence_id=occ,
            quoted_text="Quote B.",
            locator={"kind": "char_range", "start": 9, "end": 17},
        )
    )
    intel.link_fact_evidence(FactEvidenceLink(fact.id, e1.id, "supports"))
    intel.link_fact_evidence(FactEvidenceLink(fact.id, e2.id, "contradicts"))
    links = intel.list_fact_evidence(fact.id)
    assert {l.stance for l in links} == {"supports", "contradicts"}
    # Same evidence cannot create a new row; update stance instead.
    intel.link_fact_evidence(FactEvidenceLink(fact.id, e1.id, "contextual"))
    links = intel.list_fact_evidence(fact.id)
    assert len(links) == 2
    contexts = [l for l in links if l.evidence_ref_id == e1.id][0]
    assert contexts.stance == "contextual"


def test_link_fact_to_competitor_with_role_and_review(stores):
    dsn, intel, _ = stores
    cid = _create_competitor(dsn)
    fact = intel.save_fact(IntelFact(fact_type="corporate", fact_text="x"))
    intel.link_fact_to_competitor(
        IntelFactCompetitorLink(
            fact_id=fact.id,
            competitor_id=cid,
            role=FactEntityRole.SUBJECT,
            review_status=LinkReviewStatus.NEEDS_REVIEW,
        )
    )
    out = intel.list_fact_competitors(fact.id)
    assert len(out) == 1
    assert out[0].role == "subject"
    assert out[0].review_status == "needs_review"


def test_move_fact_evidence(stores):
    dsn, intel, _ = stores
    cluster, occ, ver = _create_versioned_document(dsn, "abc def ghi")
    f1 = intel.save_fact(IntelFact(fact_type="product", fact_text="x"))
    f2 = intel.save_fact(IntelFact(fact_type="product", fact_text="y"))
    e1 = intel.save_evidence_reference(
        EvidenceReference(
            document_version_id=ver, source_occurrence_id=occ,
            quoted_text="abc",
            locator={"kind": "char_range", "start": 0, "end": 3},
        )
    )
    intel.link_fact_evidence(FactEvidenceLink(f1.id, e1.id, "supports"))
    moved = intel.move_fact_evidence(f1.id, f2.id, [e1.id])
    assert moved == 1
    assert intel.list_fact_evidence(f1.id) == []
    assert len(intel.list_fact_evidence(f2.id)) == 1


def test_save_claim_only_links_via_claim_facts(stores):
    dsn, _intel, insight = stores
    claim = InsightClaim(
        claim_text="Cursor dominates the AI editor market.",
        tags=["trend"],
        maturity=ClaimMaturity.HYPOTHESIS,
        limitations="based on Q1 signals only",
    )
    saved = insight.save_claim(claim)
    fact = _intel_save_fact(_intel := PostgresIntelStoreV2(dsn))
    insight.replace_claim_facts(saved.id, [ClaimFactLink(saved.id, fact.id, "supports")])
    out = insight.list_claim_facts(saved.id)
    assert len(out) == 1
    assert out[0].stance == "supports"


def _intel_save_fact(store):
    return store.save_fact(IntelFact(fact_type="product", fact_text="x"))


def test_approve_claim_requires_supported_target(stores):
    dsn, intel, insight = stores
    fact = intel.save_fact(IntelFact(fact_type="product", fact_text="x"))
    intel.update_fact_lifecycle(fact.id, FactLifecycleStatus.ACTIVE)
    claim = insight.save_claim(
        InsightClaim(claim_text="hypothesis", maturity="hypothesis")
    )
    insight.replace_claim_facts(
        claim.id, [ClaimFactLink(claim.id, fact.id, "supports")]
    )
    # approved claim must carry approved_by + approved_at
    with pytest.raises(psycopg2.errors.CheckViolation):
        insight.update_claim_maturity(
            claim.id, ClaimMaturity.SUPPORTED, "ok", approved_by=None, approved_at=None
        )


def test_mark_dependent_supported_claims_needs_review(stores):
    dsn, intel, insight = stores
    fact = intel.save_fact(IntelFact(fact_type="product", fact_text="x"))
    intel.update_fact_lifecycle(fact.id, FactLifecycleStatus.ACTIVE)
    claim = insight.save_claim(
        InsightClaim(claim_text="hyp", maturity="hypothesis")
    )
    insight.replace_claim_facts(
        claim.id, [ClaimFactLink(claim.id, fact.id, "supports")]
    )
    insight.update_claim_maturity(
        claim.id,
        ClaimMaturity.SUPPORTED,
        "approved",
        approved_by="analyst-1",
        approved_at=datetime.now(),
    )
    # now the fact becomes disputed -> dependent claim must flip to needs_review
    flagged = insight.mark_dependent_supported_claims_needs_review(
        fact.id, "fact under review"
    )
    assert len(flagged) == 1
    assert flagged[0].maturity == "needs_review"


def test_locator_char_range_shape():
    from models.target_evidence import CharRangeLocator
    loc = CharRangeLocator(start=10, end=20)
    payload = loc.to_dict()
    assert payload == {"kind": "char_range", "start": 10, "end": 20}
    back = CharRangeLocator.from_dict(payload)
    assert (back.start, back.end) == (10, 20)
    with pytest.raises(ValueError):
        CharRangeLocator.from_dict({"kind": "wrong"})


def test_dataclass_shape_has_no_legacy_score():
    from dataclasses import fields
    intel_fact_fields = {f.name for f in fields(IntelFact)}
    for forbidden in (
        "importance_score", "confidence_score",
        "fact_kind", "dimension", "assertion_key",
    ):
        assert forbidden not in intel_fact_fields, forbidden

    insight_claim_fields = {f.name for f in fields(InsightClaim)}
    for forbidden in (
        "claim_type", "fact_ids", "competitor_ids", "product_ids",
        "confidence_score",
    ):
        assert forbidden not in insight_claim_fields, forbidden

    evidence_fields = {f.name for f in fields(EvidenceReference)}
    for forbidden in (
        "owner_type", "owner_id", "url", "title", "snippet",
        "evidence_type", "relevance_score", "role", "stance",
        "source_tier", "source_kind",
    ):
        assert forbidden not in evidence_fields, forbidden