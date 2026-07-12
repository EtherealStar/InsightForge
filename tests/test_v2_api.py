"""Smoke test for the v2 intelligence API router."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid

import psycopg2
import pytest


@pytest.fixture(scope="module")
def server():
    if not os.getenv("PG_DSN"):
        pytest.skip("PG_DSN not set")
    # Use a dedicated test database.
    base, _, _ = os.environ["PG_DSN"].rpartition("/")
    name = f"logos_v2api_{uuid.uuid4().hex[:10]}"
    admin = psycopg2.connect(os.environ["PG_DSN"])
    admin.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = admin.cursor()
    cur.execute(f"CREATE DATABASE {name}")
    admin.close()
    # Apply migrations.
    proc = subprocess.run(
        [sys.executable, "migrations/apply_migrations.py"],
        env={**os.environ, "PG_DSN": f"{base}/{name}", "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # Start uvicorn.
    env = {**os.environ, "PG_DSN": f"{base}/{name}", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "delivery.server:app",
            "--host", "127.0.0.1",
            "--port", "8765",
            "--log-level", "warning",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for /health.
    import time
    import urllib.request
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate()
        pytest.fail("server did not start")
    yield f"{base}/{name}"
    proc.terminate()
    proc.wait(timeout=5)
    admin = psycopg2.connect(os.environ["PG_DSN"])
    admin.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = admin.cursor()
    cur.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = %s AND pid <> pg_backend_pid()",
        (name,),
    )
    cur.execute(f"DROP DATABASE {name}")
    admin.close()


def _setup_versioned_doc(dsn):
    cluster = f"cl-{uuid.uuid4().hex[:8]}"
    occ = f"occ-{uuid.uuid4().hex[:8]}"
    ver = f"ver-{uuid.uuid4().hex[:8]}"
    domain = f"{cluster}.example.com"
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("INSERT INTO document_clusters (id) VALUES (%s)", (cluster,))
    cur.execute(
        "INSERT INTO source_profiles (id, domain, tier) VALUES (%s, %s, 'B')",
        (f"prof-{cluster}", domain),
    )
    cur.execute(
        "INSERT INTO source_profile_revisions (id, profile_id, tier, source_kind, actor, reason) "
        "VALUES (%s, %s, 'B', 'news', 'tester', 'init')",
        (f"rev-{cluster}", f"prof-{cluster}"),
    )
    cur.execute(
        """INSERT INTO source_occurrences
           (id, document_id, url, normalized_url, content_hash, simhash,
            high_bands, gray_bands, algorithm_version, source_tier, source_kind,
            source_profile_revision_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            occ, cluster, f"https://{domain}/post", f"https://{domain}/post",
            "h" * 64, 0, [1, 2, 3], [0, 0, 0, 0],
            "v1", "B", "news", f"rev-{cluster}",
        ),
    )
    cur.execute(
        """INSERT INTO source_document_versions
           (id, document_id, version, content, content_hash, status)
           VALUES (%s,%s,1,%s,%s,'active')""",
        (ver, cluster, "Cursor Pro costs 20 USD.", "h" * 64),
    )
    cur.execute(
        "UPDATE document_clusters SET active_version_id = %s WHERE id = %s",
        (ver, cluster),
    )
    conn.close()
    return cluster, occ, ver


def _create_competitor(dsn, name="Cursor"):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("INSERT INTO competitors (name, status) VALUES (%s, 'active') RETURNING id", (name,))
    cid = cur.fetchone()[0]
    conn.close()
    return cid


def _post(url, payload):
    import urllib.request, json
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def _get(url):
    import urllib.request, json
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def test_v2_create_evidence_and_fact(server):
    import urllib.request, json
    dsn = server
    cluster, occ, ver = _setup_versioned_doc(dsn)
    cid = _create_competitor(dsn)
    base = "http://127.0.0.1:8765/api/v2"

    # 1. Create evidence anchor.
    payload = {
        "document_version_id": ver,
        "source_occurrence_id": occ,
        "quoted_text": "20 USD",
        "locator": {"kind": "char_range", "start": 17, "end": 23},
    }
    status, body = _post(f"{base}/intel/evidence", payload)
    assert status == 201, body
    assert body["quote_hash"]
    evidence_id = body["id"]

    # 2. Create draft fact.
    payload = {
        "fact_type": "commercial",
        "fact_text": "Cursor Pro price is 20 USD.",
        "normalized_schema": "commercial.pricing.v1",
        "normalized_data": {"amount": 20, "currency": "USD", "billing_period": "month"},
        "time_precision": "month",
        "candidate_key": "cursor:pricing:2026-01",
    }
    status, body = _post(f"{base}/intel/facts?created_by=tester", payload)
    assert status == 201, body
    assert body["lifecycle_status"] == "draft"
    fact_id = body["id"]

    # 3. Add subject link.
    status, body = _post(
        f"{base}/intel/facts/{fact_id}/subjects",
        {"competitor_id": cid, "role": "subject", "review_status": "confirmed"},
    )
    assert status == 200, body

    # 3b. Link evidence to fact.
    status, body = _post(
        f"{base}/intel/facts/{fact_id}/evidence",
        {"evidence_ref_id": evidence_id, "stance": "supports"},
    )
    assert status == 200, body

    # 4. Activate.
    status, body = _post(f"{base}/intel/facts/{fact_id}/activate", {})
    assert status == 200, body
    if not body["is_active"]:
        raise AssertionError(f"activation failed: {body}")

    # 5. Get the fact.
    status, body = _get(f"{base}/intel/facts/{fact_id}")
    assert status == 200
    assert body["lifecycle_status"] == "active"


def test_v2_activate_without_subject_fails(server):
    dsn = server
    cluster, occ, ver = _setup_versioned_doc(dsn)
    base = "http://127.0.0.1:8765/api/v2"
    payload = {
        "fact_type": "commercial",
        "fact_text": "no subject",
        "normalized_schema": "commercial.pricing.v1",
        "normalized_data": {"amount": 20, "currency": "USD", "billing_period": "month"},
        "time_precision": "month",
    }
    status, body = _post(f"{base}/intel/facts?created_by=tester", payload)
    assert status == 201
    fact_id = body["id"]
    status, body = _post(f"{base}/intel/facts/{fact_id}/activate", {})
    assert status == 200
    assert body["is_active"] is False
    assert "no confirmed subject" in body["status_reason"]


def test_v2_create_claim_requires_fact(server):
    import urllib.error
    dsn = server
    base = "http://127.0.0.1:8765/api/v2"
    payload = {
        "claim_text": "no fact links",
        "tags": ["trend"],
    }
    try:
        _post(f"{base}/intel/claims", payload)
    except urllib.error.HTTPError as exc:
        assert exc.code == 422
        return
    raise AssertionError("expected 422")