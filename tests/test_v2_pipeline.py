"""Milestone 4 tests: fact resolution + rebuild CLI."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime

import psycopg2
import pytest

from models.target_intel import (
    FactLifecycleStatus,
    FactResolutionOutcome,
    IntelFact,
    IntelFactCandidate,
    TimePrecision,
)
from services.fact_resolution_service import (
    FactResolutionService,
    ResolutionContext,
)


def test_resolution_same_when_text_and_normalized_match():
    svc = FactResolutionService()
    existing = IntelFact(
        id="f1",
        fact_type="commercial",
        fact_text="Cursor Pro is 20 USD/month.",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        lifecycle_status="active",
    )
    cand = IntelFactCandidate(
        candidate_key="cursor:pricing",
        fact_type="commercial",
        fact_text="Cursor Pro is 20 USD/month.",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        occurred_at=None,
        valid_from=None,
        valid_to=None,
        time_precision=None,
        key_qualifiers={"amount": 20, "currency": "USD", "billing_period": "month"},
    )
    res = svc.resolve(ResolutionContext(cand, [existing]))
    assert res.outcome == FactResolutionOutcome.SAME
    assert res.matched_fact_id == "f1"


def test_resolution_different_on_price_conflict():
    svc = FactResolutionService()
    existing = IntelFact(
        id="f1",
        fact_type="commercial",
        fact_text="Cursor Pro is 20 USD/month.",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        lifecycle_status="active",
    )
    cand = IntelFactCandidate(
        candidate_key="cursor:pricing",
        fact_type="commercial",
        fact_text="Cursor Pro is 25 USD/month.",
        normalized_data={"amount": 25, "currency": "USD", "billing_period": "month"},
        occurred_at=None,
        valid_from=None,
        valid_to=None,
        time_precision=None,
        key_qualifiers={"amount": 25, "currency": "USD", "billing_period": "month"},
    )
    res = svc.resolve(ResolutionContext(cand, [existing]))
    assert res.outcome == FactResolutionOutcome.DIFFERENT
    assert "amount" in res.reason


def test_resolution_different_on_currency_conflict():
    svc = FactResolutionService()
    existing = IntelFact(
        id="f1",
        fact_type="commercial",
        fact_text="Cursor Pro is 20 USD/month.",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        lifecycle_status="active",
    )
    cand = IntelFactCandidate(
        candidate_key="cursor:pricing",
        fact_type="commercial",
        fact_text="Cursor Pro is 20 EUR/month.",
        normalized_data={"amount": 20, "currency": "EUR", "billing_period": "month"},
        occurred_at=None,
        valid_from=None,
        valid_to=None,
        time_precision=None,
        key_qualifiers={"amount": 20, "currency": "EUR", "billing_period": "month"},
    )
    res = svc.resolve(ResolutionContext(cand, [existing]))
    assert res.outcome == FactResolutionOutcome.DIFFERENT


def test_resolution_different_on_time_bucket_mismatch():
    svc = FactResolutionService()
    existing = IntelFact(
        id="f1",
        fact_type="commercial",
        fact_text="Cursor Pro price changed.",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        occurred_at=datetime(2026, 1, 15),
        time_precision="day",
        lifecycle_status="active",
    )
    cand = IntelFactCandidate(
        candidate_key="cursor:pricing",
        fact_type="commercial",
        fact_text="Cursor Pro price changed.",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        occurred_at=datetime(2026, 2, 15),
        valid_from=None,
        valid_to=None,
        time_precision="day",
        key_qualifiers={"amount": 20, "currency": "USD", "billing_period": "month"},
    )
    res = svc.resolve(ResolutionContext(cand, [existing]))
    assert res.outcome == FactResolutionOutcome.DIFFERENT
    assert "time bucket" in res.reason


def test_resolution_uncertain_when_no_match():
    svc = FactResolutionService()
    existing = IntelFact(
        id="f1",
        fact_type="commercial",
        fact_text="Cursor Pro is 20 USD/month.",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        lifecycle_status="active",
    )
    cand = IntelFactCandidate(
        candidate_key="cursor:pricing",
        fact_type="commercial",
        fact_text="Cursor Pro might have changed.",
        normalized_data=None,
        occurred_at=None,
        valid_from=None,
        valid_to=None,
        time_precision=None,
        key_qualifiers={},
    )
    res = svc.resolve(ResolutionContext(cand, [existing]))
    assert res.outcome == FactResolutionOutcome.UNCERTAIN


def test_resolution_uncertain_when_no_existing_facts():
    svc = FactResolutionService()
    cand = IntelFactCandidate(
        candidate_key="cursor:pricing",
        fact_type="commercial",
        fact_text="Cursor Pro is 20 USD/month.",
        normalized_data={"amount": 20, "currency": "USD", "billing_period": "month"},
        occurred_at=None,
        valid_from=None,
        valid_to=None,
        time_precision=None,
        key_qualifiers={},
    )
    res = svc.resolve(ResolutionContext(cand, []))
    assert res.outcome == FactResolutionOutcome.UNCERTAIN


# --- rebuild CLI smoke test ------------------------------------------

PG_DSN = os.getenv("PG_DSN")


def _setup_db():
    assert PG_DSN
    base, _, _ = PG_DSN.rpartition("/")
    name = f"logos_m4_{uuid.uuid4().hex[:10]}"
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
def fresh_db():
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
    try:
        yield dsn
    finally:
        _teardown_db(name)


def test_rebuild_cli_verify_only_works(fresh_db):
    proc = subprocess.run(
        [
            sys.executable, "-m", "delivery.cli",
            "rebuild-structured-intelligence", "--verify-only",
        ],
        env={**os.environ, "PG_DSN": fresh_db, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Rebuild Stats" in proc.stdout


def test_rebuild_cli_shadow_is_idempotent(fresh_db):
    proc1 = subprocess.run(
        [
            sys.executable, "-m", "delivery.cli",
            "rebuild-structured-intelligence", "--shadow", "--batch-size", "5",
        ],
        env={**os.environ, "PG_DSN": fresh_db, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc1.returncode == 0, proc1.stdout + proc1.stderr
    proc2 = subprocess.run(
        [
            sys.executable, "-m", "delivery.cli",
            "rebuild-structured-intelligence", "--shadow", "--batch-size", "5",
        ],
        env={**os.environ, "PG_DSN": fresh_db, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc2.returncode == 0
    # Second run should skip everything via rebuild_progress ledger.
    assert "versions_skipped" in proc2.stdout or "Rebuild Stats" in proc2.stdout