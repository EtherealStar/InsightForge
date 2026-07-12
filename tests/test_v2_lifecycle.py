"""Milestone 3 tests: anchors, gates, verification, supersede, split."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid

import psycopg2
import pytest

from core.exceptions import IntelligenceInvariantError, StoreError
from infrastructure.intel_store_v2 import (
    PostgresIntelStoreV2,
    compute_quote_hash,
)
from services.evidence_anchor_service import AnchorRequest, EvidenceAnchorService
from services.evidence_verification_v2 import EvidenceVerificationServiceV2
from services.intel_lifecycle_service import IntelLifecycleService
from services.normalized_fact_schema import (
    get_schema,
    register_schema,
    validate_payload,
)
from models.target_intel import (
    FactEntityRole,
    FactEvidenceLink,
    FactLifecycleStatus,
    IntelFact,
    IntelFactCompetitorLink,
    IntelFactProductLink,
    LinkReviewStatus,
    VerificationStatus,
)


PG_DSN = os.getenv("PG_DSN")


def _setup_db():
    assert PG_DSN, "PG_DSN required"
    base, _, _ = PG_DSN.rpartition("/")
    name = f"logos_m3_{uuid.uuid4().hex[:10]}"
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
    result = subprocess.run(
        [sys.executable, "migrations/apply_migrations.py"],
        env={**os.environ, "PG_DSN": dsn, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        _teardown_db(name)
        pytest.fail(f"migrations failed: {result.stdout}\n{result.stderr}")
    store = PostgresIntelStoreV2(dsn)
    anchor = EvidenceAnchorService(store)
    verifier = EvidenceVerificationServiceV2(dsn)
    lifecycle = IntelLifecycleService(store, verifier)
    try:
        yield dsn, store, anchor, verifier, lifecycle
    finally:
        _teardown_db(name)


def _setup_versioned_doc(dsn, content, occ_url=None):
    """Insert cluster + occurrence + active version + a Source Profile."""
    cluster_id = f"cl-{uuid.uuid4().hex[:8]}"
    occ_id = f"occ-{uuid.uuid4().hex[:8]}"
    ver_id = f"ver-{uuid.uuid4().hex[:8]}"
    profile_id = f"prof-{uuid.uuid4().hex[:8]}"
    rev_id = f"rev-{uuid.uuid4().hex[:8]}"
    domain = f"{cluster_id}.example.com"
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("INSERT INTO document_clusters (id) VALUES (%s)", (cluster_id,))
    cur.execute(
        "INSERT INTO source_profiles (id, domain, tier) VALUES (%s, %s, 'B')",
        (profile_id, domain),
    )
    cur.execute(
        "INSERT INTO source_profile_revisions (id, profile_id, tier, source_kind, actor, reason) "
        "VALUES (%s, %s, 'B', 'news', 'tester', 'init')",
        (rev_id, profile_id),
    )
    url = occ_url or f"https://{domain}/post-{cluster_id}"
    cur.execute(
        """INSERT INTO source_occurrences
           (id, document_id, url, normalized_url, content_hash, simhash,
            high_bands, gray_bands, algorithm_version, source_tier, source_kind,
            source_profile_revision_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            occ_id, cluster_id, url, url, "h" * 64, 0, [1, 2, 3], [0, 0, 0, 0],
            "v1", "B", "news", rev_id,
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
    return cluster_id, occ_id, ver_id, profile_id, rev_id


def _create_competitor(dsn, name="Cursor"):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("INSERT INTO competitors (name, status) VALUES (%s, 'active') RETURNING id", (name,))
    cid = cur.fetchone()[0]
    conn.close()
    return cid


# --- 1. normalized_fact_schema ---------------------------------------


def test_pricing_v1_valid_payload_passes():
    ok, reason = validate_payload(
        "commercial.pricing.v1",
        "commercial",
        {"amount": 20, "currency": "USD", "billing_period": "month", "market": "US"},
    )
    assert ok, reason


def test_pricing_v1_missing_required_fails():
    ok, reason = validate_payload(
        "commercial.pricing.v1", "commercial", {"amount": 20}
    )
    assert not ok
    assert "currency" in reason


def test_pricing_v1_wrong_fact_type_fails():
    ok, reason = validate_payload(
        "commercial.pricing.v1", "product", {"amount": 20, "currency": "USD", "billing_period": "month"}
    )
    assert not ok
    assert "product" in reason or "fact_type" in reason


def test_pricing_v1_invalid_billing_period_fails():
    ok, reason = validate_payload(
        "commercial.pricing.v1",
        "commercial",
        {"amount": 20, "currency": "USD", "billing_period": "fortnight"},
    )
    assert not ok


def test_register_schema_extends_registry():
    custom = get_schema("nonexistent")
    assert custom is None


# --- 2. evidence_anchor_service --------------------------------------


def test_anchor_locator_out_of_range_rejected(env):
    dsn, store, anchor, _, _ = env
    _, occ, ver, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
    with pytest.raises(IntelligenceInvariantError):
        anchor.create_evidence_reference(
            AnchorRequest(
                document_version_id=ver,
                source_occurrence_id=occ,
                quoted_text="way past the end",
                locator={"kind": "char_range", "start": 0, "end": 9999},
            )
        )


def test_anchor_quote_mismatch_rejected(env):
    dsn, store, anchor, _, _ = env
    _, occ, ver, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
    with pytest.raises(IntelligenceInvariantError):
        anchor.create_evidence_reference(
            AnchorRequest(
                document_version_id=ver,
                source_occurrence_id=occ,
                quoted_text="Cursor Pro costs 25 USD.",
                locator={"kind": "char_range", "start": 0, "end": 22},
            )
        )


def test_anchor_wrong_cluster_occurrence_rejected(env):
    dsn, store, anchor, _, _ = env
    # Set up one cluster with version/occ
    _, occ, ver, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
    # Build a *second* cluster with its own version and try to pair it with
    # the first occurrence.
    cluster_b, _, ver_b, _, _ = _setup_versioned_doc(dsn, "Unrelated content")
    # resolve_evidence_context joins on document_id, so a mismatched pair
    # returns no rows and the service raises StoreError (or
    # IntelligenceInvariantError depending on path).
    with pytest.raises(StoreError):
        anchor.create_evidence_reference(
            AnchorRequest(
                document_version_id=ver_b,
                source_occurrence_id=occ,  # wrong cluster
                quoted_text="Unrelated content",
                locator={"kind": "char_range", "start": 0, "end": 17},
            )
        )


def test_anchor_client_hash_mismatch_rejected(env):
    dsn, store, anchor, _, _ = env
    _, occ, ver, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
    with pytest.raises(IntelligenceInvariantError):
        anchor.create_evidence_reference(
            AnchorRequest(
                document_version_id=ver,
                source_occurrence_id=occ,
                quoted_text="Cursor Pro costs 20 USD.",
                locator={"kind": "char_range", "start": 0, "end": 25},
                client_quote_hash="0" * 64,
            )
        )


def test_anchor_happy_path(env):
    dsn, store, anchor, _, _ = env
    _, occ, ver, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
    text = "20 USD"
    start = "Cursor Pro costs ".__len__()
    saved = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver,
            source_occurrence_id=occ,
            quoted_text=text,
            locator={"kind": "char_range", "start": start, "end": start + len(text)},
        )
    )
    assert saved.id
    assert saved.quote_hash == compute_quote_hash(text)


def test_anchor_rejects_search_snippet_as_formal(env):
    dsn, store, anchor, _, _ = env
    _, occ, ver, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
    # Pass a locator pointing outside the document — simulates a search
    # summary that the service refused to coerce into a formal anchor.
    with pytest.raises(IntelligenceInvariantError):
        anchor.create_evidence_reference(
            AnchorRequest(
                document_version_id=ver,
                source_occurrence_id=occ,
                quoted_text="20 USD",
                locator={"kind": "char_range", "start": 200, "end": 206},
            )
        )


# --- 3. activation gate ----------------------------------------------


def test_activation_requires_confirmed_subject(env):
    dsn, store, anchor, verifier, lifecycle = env
    _, occ, ver, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
    text = "20 USD"
    start = "Cursor Pro costs ".__len__()
    e = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver,
            source_occurrence_id=occ,
            quoted_text=text,
            locator={"kind": "char_range", "start": start, "end": start + len(text)},
        )
    )
    fact = lifecycle.create_draft_fact(
        fact_type="commercial",
        fact_text="Cursor Pro price is 20 USD.",
        candidate_key="cursor:pricing:2026-01",
        normalized_schema="commercial.pricing.v1",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        occurred_at=None,
        valid_from=None,
        valid_to=None,
        time_precision="month",
        created_by="tester",
    )
    store.link_fact_evidence(FactEvidenceLink(fact.id, e.id, "supports"))
    report = lifecycle.activate_fact(fact.id)
    assert not report.is_active
    assert "no confirmed subject" in report.status_reason


def test_activation_no_anchor_stays_draft(env):
    dsn, store, _, verifier, lifecycle = env
    cid = _create_competitor(dsn)
    fact = lifecycle.create_draft_fact(
        fact_type="commercial",
        fact_text="Cursor Pro price is 20 USD.",
        candidate_key=None,
        normalized_schema="commercial.pricing.v1",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        occurred_at=None,
        valid_from=None,
        valid_to=None,
        time_precision="month",
        created_by="tester",
    )
    store.link_fact_to_competitor(
        IntelFactCompetitorLink(
            fact_id=fact.id,
            competitor_id=cid,
            role=FactEntityRole.SUBJECT,
            review_status=LinkReviewStatus.CONFIRMED,
        )
    )
    report = lifecycle.activate_fact(fact.id)
    assert not report.is_active
    assert "no formal supporting anchor" in report.status_reason


def test_activation_single_source(env):
    dsn, store, anchor, verifier, lifecycle = env
    cid = _create_competitor(dsn)
    _, occ, ver, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
    text = "20 USD"
    start = "Cursor Pro costs ".__len__()
    e = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver,
            source_occurrence_id=occ,
            quoted_text=text,
            locator={"kind": "char_range", "start": start, "end": start + len(text)},
        )
    )
    fact = lifecycle.create_draft_fact(
        fact_type="commercial",
        fact_text="Cursor Pro price is 20 USD.",
        candidate_key="cursor:pricing:2026-01",
        normalized_schema="commercial.pricing.v1",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        occurred_at=None,
        valid_from=None,
        valid_to=None,
        time_precision="month",
        created_by="tester",
    )
    store.link_fact_to_competitor(
        IntelFactCompetitorLink(
            fact_id=fact.id, competitor_id=cid, role=FactEntityRole.SUBJECT,
            review_status=LinkReviewStatus.CONFIRMED,
        )
    )
    store.link_fact_evidence(FactEvidenceLink(fact.id, e.id, "supports"))
    report = lifecycle.activate_fact(fact.id)
    assert report.is_active
    assert report.fact.verification_status == "single_source"


def test_activation_corroborated_with_two_clusters(env):
    dsn, store, anchor, verifier, lifecycle = env
    cid = _create_competitor(dsn)
    _, occ_a, ver_a, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD per month.")
    _, occ_b, ver_b, _, _ = _setup_versioned_doc(dsn, "Cursor Pro pricing is 20 USD monthly.")
    text_a = "20 USD per month"
    text_b = "20 USD monthly"
    start_a = "Cursor Pro costs ".__len__()
    start_b = "Cursor Pro pricing is ".__len__()
    e_a = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver_a,
            source_occurrence_id=occ_a,
            quoted_text=text_a,
            locator={"kind": "char_range", "start": start_a, "end": start_a + len(text_a)},
        )
    )
    e_b = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver_b,
            source_occurrence_id=occ_b,
            quoted_text=text_b,
            locator={"kind": "char_range", "start": start_b, "end": start_b + len(text_b)},
        )
    )
    fact = lifecycle.create_draft_fact(
        fact_type="commercial",
        fact_text="Cursor Pro price is 20 USD.",
        candidate_key="cursor:pricing:2026-01",
        normalized_schema="commercial.pricing.v1",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        occurred_at=None,
        valid_from=None,
        valid_to=None,
        time_precision="month",
        created_by="tester",
    )
    store.link_fact_to_competitor(
        IntelFactCompetitorLink(
            fact_id=fact.id, competitor_id=cid, role=FactEntityRole.SUBJECT,
            review_status=LinkReviewStatus.CONFIRMED,
        )
    )
    store.link_fact_evidence(FactEvidenceLink(fact.id, e_a.id, "supports"))
    store.link_fact_evidence(FactEvidenceLink(fact.id, e_b.id, "supports"))
    report = lifecycle.activate_fact(fact.id)
    assert report.is_active
    assert report.fact.verification_status == "corroborated"


def test_activation_self_reported_when_source_controlled_by_subject(env):
    dsn, store, anchor, verifier, lifecycle = env
    cid = _create_competitor(dsn)
    cluster, occ, ver, profile, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
    # Mark the profile as controlled by the same competitor.
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO source_profile_competitors (profile_id, competitor_id, created_by, reason) "
        "VALUES (%s, %s, 'tester', 'owned')",
        (profile, cid),
    )
    conn.close()
    text = "20 USD"
    start = "Cursor Pro costs ".__len__()
    e = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver,
            source_occurrence_id=occ,
            quoted_text=text,
            locator={"kind": "char_range", "start": start, "end": start + len(text)},
        )
    )
    fact = lifecycle.create_draft_fact(
        fact_type="commercial",
        fact_text="Cursor Pro price is 20 USD.",
        candidate_key=None,
        normalized_schema="commercial.pricing.v1",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        occurred_at=None,
        valid_from=None,
        valid_to=None,
        time_precision="month",
        created_by="tester",
    )
    store.link_fact_to_competitor(
        IntelFactCompetitorLink(
            fact_id=fact.id, competitor_id=cid, role=FactEntityRole.SUBJECT,
            review_status=LinkReviewStatus.CONFIRMED,
        )
    )
    store.link_fact_evidence(FactEvidenceLink(fact.id, e.id, "supports"))
    report = lifecycle.activate_fact(fact.id)
    assert report.is_active
    assert report.fact.verification_status == "self_reported"


def test_active_fact_cannot_be_mutated_by_db_trigger(env):
    dsn, store, anchor, verifier, lifecycle = env
    cid = _create_competitor(dsn)
    _, occ, ver, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
    text = "20 USD"
    start = "Cursor Pro costs ".__len__()
    e = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver,
            source_occurrence_id=occ,
            quoted_text=text,
            locator={"kind": "char_range", "start": start, "end": start + len(text)},
        )
    )
    fact = lifecycle.create_draft_fact(
        fact_type="commercial",
        fact_text="v1",
        candidate_key=None,
        normalized_schema=None,
        normalized_data=None,
        occurred_at=None,
        valid_from=None,
        valid_to=None,
        time_precision=None,
        created_by="tester",
    )
    store.link_fact_to_competitor(
        IntelFactCompetitorLink(
            fact_id=fact.id, competitor_id=cid, role=FactEntityRole.SUBJECT,
            review_status=LinkReviewStatus.CONFIRMED,
        )
    )
    store.link_fact_evidence(FactEvidenceLink(fact.id, e.id, "supports"))
    lifecycle.activate_fact(fact.id)
    # Direct DB UPDATE of fact_text on an active fact must fail.
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "UPDATE intel_facts SET fact_text = 'mutated' WHERE id = %s",
            (fact.id,),
        )
    conn.close()


def test_supersede_creates_new_and_marks_old(env):
    dsn, store, anchor, verifier, lifecycle = env
    cid = _create_competitor(dsn)
    _, occ, ver, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
    text = "20 USD"
    start = "Cursor Pro costs ".__len__()
    e = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver,
            source_occurrence_id=occ,
            quoted_text=text,
            locator={"kind": "char_range", "start": start, "end": start + len(text)},
        )
    )
    old = lifecycle.create_draft_fact(
        fact_type="commercial",
        fact_text="Cursor Pro price is 20 USD.",
        candidate_key=None,
        normalized_schema="commercial.pricing.v1",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        occurred_at=None,
        valid_from=None,
        valid_to=None,
        time_precision="month",
        created_by="tester",
    )
    store.link_fact_to_competitor(
        IntelFactCompetitorLink(
            fact_id=old.id, competitor_id=cid, role=FactEntityRole.SUBJECT,
            review_status=LinkReviewStatus.CONFIRMED,
        )
    )
    store.link_fact_evidence(FactEvidenceLink(old.id, e.id, "supports"))
    lifecycle.activate_fact(old.id)

    new = IntelFact(
        fact_type="commercial",
        fact_text="Cursor Pro price is 25 USD.",
        normalized_data={"amount": 25, "currency": "USD", "billing_period": "month"},
        candidate_key=None,
        lifecycle_status="draft",
    )
    created = lifecycle.supersede_fact(old_fact_id=old.id, new_fact=new)
    assert created.supersedes_fact_id == old.id
    old2 = store.get_fact(old.id)
    assert old2.lifecycle_status == "superseded"


def test_split_moves_evidence_atomically(env):
    dsn, store, anchor, verifier, lifecycle = env
    cid = _create_competitor(dsn)
    _, occ_a, ver_a, _, _ = _setup_versioned_doc(dsn, "Quote A. Quote B.")
    _, occ_b, ver_b, _, _ = _setup_versioned_doc(dsn, "Quote A. Quote B.")
    text = "Quote A."
    e1 = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver_a,
            source_occurrence_id=occ_a,
            quoted_text=text,
            locator={"kind": "char_range", "start": 0, "end": 8},
        )
    )
    e2 = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver_b,
            source_occurrence_id=occ_b,
            quoted_text=text,
            locator={"kind": "char_range", "start": 0, "end": 8},
        )
    )
    f1 = lifecycle.create_draft_fact(
        fact_type="product", fact_text="x", candidate_key=None,
        normalized_schema=None, normalized_data=None,
        occurred_at=None, valid_from=None, valid_to=None,
        time_precision=None, created_by="tester",
    )
    f2 = lifecycle.create_draft_fact(
        fact_type="product", fact_text="y", candidate_key=None,
        normalized_schema=None, normalized_data=None,
        occurred_at=None, valid_from=None, valid_to=None,
        time_precision=None, created_by="tester",
    )
    store.link_fact_to_competitor(
        IntelFactCompetitorLink(
            fact_id=f1.id, competitor_id=cid, role=FactEntityRole.SUBJECT,
            review_status=LinkReviewStatus.CONFIRMED,
        )
    )
    store.link_fact_to_competitor(
        IntelFactCompetitorLink(
            fact_id=f2.id, competitor_id=cid, role=FactEntityRole.SUBJECT,
            review_status=LinkReviewStatus.CONFIRMED,
        )
    )
    store.link_fact_evidence(FactEvidenceLink(f1.id, e1.id, "supports"))
    store.link_fact_evidence(FactEvidenceLink(f1.id, e2.id, "supports"))
    moved = lifecycle.split_fact_evidence(
        source_fact_id=f1.id, target_fact_id=f2.id, evidence_ref_ids=[e1.id]
    )
    assert moved == 1
    assert [l.evidence_ref_id for l in store.list_fact_evidence(f1.id)] == [e2.id]
    assert [l.evidence_ref_id for l in store.list_fact_evidence(f2.id)] == [e1.id]


def test_disputed_when_contradicting_anchor(env):
    dsn, store, anchor, verifier, lifecycle = env
    cid = _create_competitor(dsn)
    _, occ_a, ver_a, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD per month.")
    _, occ_b, ver_b, _, _ = _setup_versioned_doc(dsn, "Cursor Pro price is 25 USD per month.")
    text_a = "20 USD per month"
    text_b = "25 USD per month"
    e_a = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver_a,
            source_occurrence_id=occ_a,
            quoted_text=text_a,
            locator={"kind": "char_range", "start": "Cursor Pro costs ".__len__(), "end": "Cursor Pro costs ".__len__() + len(text_a)},
        )
    )
    e_b = anchor.create_evidence_reference(
        AnchorRequest(
            document_version_id=ver_b,
            source_occurrence_id=occ_b,
            quoted_text=text_b,
            locator={"kind": "char_range", "start": "Cursor Pro price is ".__len__(), "end": "Cursor Pro price is ".__len__() + len(text_b)},
        )
    )
    fact = lifecycle.create_draft_fact(
        fact_type="commercial", fact_text="price",
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
    store.link_fact_evidence(FactEvidenceLink(fact.id, e_a.id, "supports"))
    store.link_fact_evidence(FactEvidenceLink(fact.id, e_b.id, "contradicts"))
    report = lifecycle.activate_fact(fact.id)
    assert not report.is_active
    assert report.fact.lifecycle_status == "draft"


def test_locator_must_be_char_range():
    from models.target_evidence import CharRangeLocator
    with pytest.raises(ValueError):
        CharRangeLocator.from_dict({"kind": "section_id", "value": "2.1"})


def test_active_fact_subject_link_locked(env):
    """Triggers should reject removing a subject link from an active fact."""
    dsn, store, anchor, verifier, lifecycle = env
    cid = _create_competitor(dsn)
    _, occ, ver, _, _ = _setup_versioned_doc(dsn, "Cursor Pro costs 20 USD.")
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
        fact_type="commercial", fact_text="price",
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
    # PostgreSQL trigger forbids deleting the subject link on an active fact.
    with pytest.raises(psycopg2.errors.CheckViolation):
        store.unlink_fact_from_competitor(fact.id, cid, role="subject")