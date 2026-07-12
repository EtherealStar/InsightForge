"""Milestone 5 tests: InsightServiceV2 + claim maturity + propagation."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime

import psycopg2
import pytest

from core.exceptions import IntelligenceInvariantError
from infrastructure.insight_store_v2 import PostgresInsightStoreV2
from infrastructure.intel_store_v2 import PostgresIntelStoreV2
from models.target_insight import ClaimFactLink, ClaimMaturity, InsightClaim
from models.target_intel import (
    FactEntityRole,
    FactEvidenceLink,
    FactLifecycleStatus,
    IntelFact,
    IntelFactCompetitorLink,
    LinkReviewStatus,
)
from services.evidence_anchor_service import (
    AnchorRequest,
    EvidenceAnchorService,
)
from services.evidence_verification_v2 import EvidenceVerificationServiceV2
from services.insight_service_v2 import ClaimDraftRequest, InsightServiceV2
from services.intel_lifecycle_service import IntelLifecycleService


PG_DSN = os.getenv("PG_DSN")


def _setup_db():
    assert PG_DSN
    base, _, _ = PG_DSN.rpartition("/")
    name = f"logos_m5_{uuid.uuid4().hex[:10]}"
    admin = psycopg2.connect(PG_DSN)
    admin.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = admin.cursor()
    cur.execute(f"CREATE DATABASE {name}")
    admin.close()
    return f"{base}/{name}", name


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
def env():
    if not PG_DSN:
        pytest.skip("PG_DSN not set")
    dsn, name = _setup_db()
    proc = subprocess.run(
        [sys.executable, "migrations/apply_migrations.py"],
        env={**os.environ, "PG_DSN": dsn, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        _teardown_db(name)
        pytest.fail(f"migrations failed: {proc.stdout}\n{proc.stderr}")
    store = PostgresIntelStoreV2(dsn)
    insight = PostgresInsightStoreV2(dsn)
    anchor = EvidenceAnchorService(store)
    verifier = EvidenceVerificationServiceV2(dsn)
    intel_lifecycle = IntelLifecycleService(store, verifier)
    insight_service = InsightServiceV2(insight, store)
    try:
        yield dsn, store, insight, anchor, intel_lifecycle, insight_service
    finally:
        _teardown_db(name)


def _setup_versioned_doc(dsn, content):
    cluster_id = f"cl-{uuid.uuid4().hex[:8]}"
    occ_id = f"occ-{uuid.uuid4().hex[:8]}"
    ver_id = f"ver-{uuid.uuid4().hex[:8]}"
    domain = f"{cluster_id}.example.com"
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("INSERT INTO document_clusters (id) VALUES (%s)", (cluster_id,))
    cur.execute(
        "INSERT INTO source_profiles (id, domain, tier) VALUES (%s, %s, 'B')",
        (f"prof-{cluster_id}", domain),
    )
    cur.execute(
        "INSERT INTO source_profile_revisions (id, profile_id, tier, source_kind, actor, reason) "
        "VALUES (%s, %s, 'B', 'news', 'tester', 'init')",
        (f"rev-{cluster_id}", f"prof-{cluster_id}"),
    )
    cur.execute(
        """INSERT INTO source_occurrences
           (id, document_id, url, normalized_url, content_hash, simhash,
            high_bands, gray_bands, algorithm_version, source_tier, source_kind,
            source_profile_revision_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            occ_id, cluster_id, f"https://{domain}/post", f"https://{domain}/post",
            "h" * 64, 0, [1, 2, 3], [0, 0, 0, 0],
            "v1", "B", "news", f"rev-{cluster_id}",
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
    cur.execute("INSERT INTO competitors (name, status) VALUES (%s, 'active') RETURNING id", (name,))
    cid = cur.fetchone()[0]
    conn.close()
    return cid


def _make_active_fact(env, fact_text="price is 20 USD."):
    dsn, store, _, anchor, lifecycle, _ = env
    cid = _create_competitor(dsn)
    _, occ, ver = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
    text = "20 USD"
    start = "Cursor Pro costs ".__len__()
    e = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver, source_occurrence_id=occ,
            quoted_text=text,
            locator={"kind": "char_range", "start": start, "end": start + len(text)},
        )
    )
    fact = lifecycle.create_draft_fact(
        fact_type="commercial",
        fact_text=fact_text,
        candidate_key=None,
        normalized_schema="commercial.pricing.v1",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        occurred_at=None, valid_from=None, valid_to=None,
        time_precision="month", created_by="tester",
    )
    store.link_fact_to_competitor(
        IntelFactCompetitorLink(
            fact_id=fact.id, competitor_id=cid, role=FactEntityRole.SUBJECT,
            review_status=LinkReviewStatus.CONFIRMED,
        )
    )
    store.link_fact_evidence(FactEvidenceLink(fact.id, e.id, "supports"))
    lifecycle.activate_fact(fact.id)
    return store.get_fact(fact.id)


# --- 1. create / update ----------------------------------------------


def test_create_hypothesis_sets_hypothesis_maturity(env):
    dsn, store, insight, _, _, svc = env
    claim = svc.create_hypothesis(
        ClaimDraftRequest(
            claim_text="Cursor Pro is the market leader in AI editors.",
            tags=["trend"],
            limitations="based on 2026 Q1 signals",
            created_by="agent",
        )
    )
    assert claim.maturity == "hypothesis"


def test_update_draft_does_not_affect_supported(env):
    dsn, store, insight, _, _, svc = env
    fact = _make_active_fact(env)
    claim = svc.create_hypothesis(ClaimDraftRequest(claim_text="h", tags=["trend"]))
    svc.replace_facts(
        claim.id, [ClaimFactLink(claim.id, fact.id, "supports")]
    )
    svc.approve_claim(claim.id, "analyst-1")
    with pytest.raises(IntelligenceInvariantError):
        svc.update_draft(claim.id, ClaimDraftRequest(claim_text="new", tags=[]))


def test_replace_facts_rejected_on_supported_claim(env):
    dsn, store, insight, _, _, svc = env
    fact = _make_active_fact(env)
    claim = svc.create_hypothesis(ClaimDraftRequest(claim_text="h", tags=[]))
    svc.replace_facts(
        claim.id, [ClaimFactLink(claim.id, fact.id, "supports")]
    )
    svc.approve_claim(claim.id, "analyst-1")
    with pytest.raises(IntelligenceInvariantError):
        svc.replace_facts(claim.id, [ClaimFactLink(claim.id, fact.id, "contradicts")])


# --- 2. approve ------------------------------------------------------


def test_approve_requires_real_actor(env):
    dsn, store, insight, _, _, svc = env
    fact = _make_active_fact(env)
    claim = svc.create_hypothesis(ClaimDraftRequest(claim_text="h", tags=[]))
    svc.replace_facts(
        claim.id, [ClaimFactLink(claim.id, fact.id, "supports")]
    )
    for forbidden in ("agent", "system", ""):
        with pytest.raises(IntelligenceInvariantError):
            svc.approve_claim(claim.id, forbidden)


def test_approve_requires_supporting_active_fact(env):
    dsn, store, insight, _, _, svc = env
    # Create a fact but never activate it.
    dsn_in = env[0]
    cid = _create_competitor(dsn_in)
    _, occ, ver = _setup_versioned_doc(dsn_in, "Cursor Pro costs 20 USD.")
    text = "20 USD"
    start = "Cursor Pro costs ".__len__()
    anchor = env[3]
    e = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver, source_occurrence_id=occ,
            quoted_text=text,
            locator={"kind": "char_range", "start": start, "end": start + len(text)},
        )
    )
    intel_lifecycle = env[4]
    fact = intel_lifecycle.create_draft_fact(
        fact_type="commercial", fact_text="x", candidate_key=None,
        normalized_schema="commercial.pricing.v1",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        occurred_at=None, valid_from=None, valid_to=None,
        time_precision="month", created_by="tester",
    )
    store.link_fact_to_competitor(
        IntelFactCompetitorLink(
            fact_id=fact.id, competitor_id=cid, role=FactEntityRole.SUBJECT,
            review_status=LinkReviewStatus.CONFIRMED,
        )
    )
    store.link_fact_evidence(FactEvidenceLink(fact.id, e.id, "supports"))
    # fact is draft, not active.
    claim = svc.create_hypothesis(ClaimDraftRequest(claim_text="h", tags=[]))
    svc.replace_facts(
        claim.id, [ClaimFactLink(claim.id, fact.id, "supports")]
    )
    with pytest.raises(IntelligenceInvariantError):
        svc.approve_claim(claim.id, "analyst-1")


def test_approve_succeeds_with_analyst_and_active_fact(env):
    dsn, store, insight, _, _, svc = env
    fact = _make_active_fact(env)
    claim = svc.create_hypothesis(ClaimDraftRequest(claim_text="h", tags=["trend"]))
    svc.replace_facts(
        claim.id, [ClaimFactLink(claim.id, fact.id, "supports")]
    )
    approved = svc.approve_claim(claim.id, "analyst-1")
    assert approved.maturity == "supported"
    assert approved.approved_by == "analyst-1"
    assert approved.approved_at is not None


# --- 3. fact change → dependent claim propagation -------------------


def test_fact_retraction_flips_dependent_claim_to_needs_review(env):
    dsn, store, insight, _, lifecycle, svc = env
    fact = _make_active_fact(env)
    claim = svc.create_hypothesis(ClaimDraftRequest(claim_text="h", tags=[]))
    svc.replace_facts(
        claim.id, [ClaimFactLink(claim.id, fact.id, "supports")]
    )
    svc.approve_claim(claim.id, "analyst-1")
    # Simulate the fact becoming disputed by flipping its lifecycle through the
    # store directly. In production this would happen via activate/retract.
    lifecycle.retract_fact(fact.id, "wrong price")
    flagged = svc.on_fact_lifecycle_changed(fact.id, "fact retracted")
    assert len(flagged) == 1
    assert flagged[0].maturity == "needs_review"


def test_supersede_claim_creates_new_and_marks_old(env):
    dsn, store, insight, _, lifecycle, svc = env
    fact = _make_active_fact(env)
    claim = svc.create_hypothesis(ClaimDraftRequest(claim_text="old", tags=["trend"]))
    svc.replace_facts(
        claim.id, [ClaimFactLink(claim.id, fact.id, "supports")]
    )
    svc.approve_claim(claim.id, "analyst-1")
    new_claim = svc.supersede_claim(
        old_claim_id=claim.id,
        new_request=ClaimDraftRequest(claim_text="new", tags=["trend"]),
        new_fact_links=[ClaimFactLink(claim.id, fact.id, "supports")],
    )
    assert new_claim.supersedes_claim_id == claim.id
    old = insight.get_claim(claim.id)
    assert old.maturity == "superseded"


def test_claim_cannot_receive_direct_evidence_or_score(env):
    """Dataclass shape test: no evidence/score fields."""
    from dataclasses import fields
    names = {f.name for f in fields(InsightClaim)}
    for forbidden in (
        "claim_type", "fact_ids", "competitor_ids", "product_ids",
        "confidence_score", "evidence_refs", "evidence",
    ):
        assert forbidden not in names, forbidden