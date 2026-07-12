"""Migration runner tests.

These tests need a real PostgreSQL connection. They are skipped unless
``TEST_PG_DSN`` points to a writable database. Each test uses a dedicated
schema name so concurrent runs do not collide.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import psycopg2
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
RUNNER = MIGRATIONS_DIR / "apply_migrations.py"


def _admin_dsn() -> str | None:
    return os.getenv("TEST_PG_DSN")


def _isolated_database() -> tuple[str, str]:
    """Create a fresh database for a single test and return (dsn, name)."""
    admin_dsn = _admin_dsn()
    assert admin_dsn, "TEST_PG_DSN not set"
    name = f"logos_mig_{uuid.uuid4().hex[:10]}"
    admin = psycopg2.connect(admin_dsn)
    admin.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = admin.cursor()
    cur.execute(f'CREATE DATABASE "{name}"')
    admin.close()
    # Build DSN for the new DB by replacing the database segment after the last '/'.
    head, _ = admin_dsn.rsplit("/", 1)
    dsn = f"{head}/{name}"
    return dsn, name


def _drop_database(name: str) -> None:
    admin = psycopg2.connect(_admin_dsn())
    admin.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = admin.cursor()
    cur.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = %s AND pid <> pg_backend_pid()",
        (name,),
    )
    cur.execute(f'DROP DATABASE IF EXISTS "{name}"')
    admin.close()


def _copy_migrations_to(tmpdir: Path) -> Path:
    """Copy migrations/*.sql to a temp dir so we can mutate one without
    touching the real files. SQL files are placed at the root of tmpdir
    so a co-located apply_migrations.py finds them via its own __file__."""
    for f in MIGRATIONS_DIR.glob("*.sql"):
        shutil.copy2(f, tmpdir / f.name)
    return tmpdir


def _run_runner(tmpdir: Path, dsn: str, *args: str) -> subprocess.CompletedProcess:
    """Run the migration script using the *copied* migrations dir as cwd so
    file edits in tmpdir are picked up (the runner reads SQL files relative
    to its own location, which is hard-coded to the real ``migrations/``)."""
    env = os.environ.copy()
    env["PG_DSN"] = dsn
    env["PYTHONIOENCODING"] = "utf-8"
    # The runner script reads files relative to its own __file__ location,
    # so we cannot rely on cwd. Use a small wrapper that loads the runner
    # module from the temp copy.
    wrapper = tmpdir / "_run.py"
    if not wrapper.exists():
        # Copy the runner itself into the tmpdir alongside the SQL files.
        shutil.copy2(RUNNER, tmpdir / "apply_migrations.py")
    return subprocess.run(
        [sys.executable, str(tmpdir / "apply_migrations.py"), *args],
        cwd=str(tmpdir),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _list_tables(dsn: str) -> list[str]:
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' ORDER BY table_name"
    )
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def _ledger(dsn: str) -> list[str]:
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(
        "SELECT filename FROM schema_migrations ORDER BY filename"
    )
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


@pytest.mark.skipif(
    not _admin_dsn(), reason="TEST_PG_DSN not set; migration tests need PG"
)
def test_first_run_applies_all_migrations(tmp_path):
    dsn, name = _isolated_database()
    try:
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            _copy_migrations_to(tmpdir)
            proc = _run_runner(tmpdir, dsn)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        tables = _list_tables(dsn)
        assert "schema_migrations" in tables
        assert "intel_facts" in tables
        assert "fact_evidence" in tables
        assert "claim_facts" in tables
        assert "source_profile_competitors" in tables
        ledger = _ledger(dsn)
        assert "011_three_layer_structured_intelligence_expand.sql" in ledger
        assert set(ledger) == {path.name for path in MIGRATIONS_DIR.glob("*.sql")}
    finally:
        _drop_database(name)


@pytest.mark.skipif(
    not _admin_dsn(), reason="TEST_PG_DSN not set; migration tests need PG"
)
def test_second_run_is_noop(tmp_path):
    dsn, name = _isolated_database()
    try:
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            _copy_migrations_to(tmpdir)
            proc1 = _run_runner(tmpdir, dsn)
            assert proc1.returncode == 0, proc1.stdout + proc1.stderr
            proc2 = _run_runner(tmpdir, dsn)
            assert proc2.returncode == 0, proc2.stdout + proc2.stderr
            assert "没有待执行迁移" in proc2.stdout
    finally:
        _drop_database(name)


@pytest.mark.skipif(
    not _admin_dsn(), reason="TEST_PG_DSN not set; migration tests need PG"
)
def test_checksum_drift_rejected(tmp_path):
    dsn, name = _isolated_database()
    try:
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            migrations = _copy_migrations_to(tmpdir)
            proc1 = _run_runner(tmpdir, dsn)
            assert proc1.returncode == 0
            # Mutate an already-applied migration to simulate drift.
            target = migrations / "001_infrastructure_foundation.sql"
            original = target.read_text(encoding="utf-8")
            target.write_text(original + "\n-- drift", encoding="utf-8")
            proc2 = _run_runner(tmpdir, dsn)
            assert proc2.returncode == 4
            assert "checksum" in proc2.stdout
            assert "001_infrastructure_foundation.sql" in proc2.stdout
    finally:
        _drop_database(name)


@pytest.mark.skipif(
    not _admin_dsn(), reason="TEST_PG_DSN not set; migration tests need PG"
)
def test_failure_stops_run_and_rolls_back(tmp_path):
    """A failing migration must abort the run, leave no orphan ledger row."""
    dsn, name = _isolated_database()
    try:
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            migrations = _copy_migrations_to(tmpdir)
            # Create a fake 999 that always fails (must sort after 011).
            (migrations / "999_always_fail.sql").write_text(
                "BEGIN; CREATE TABLE should_not_exist(x INT); "
                "DO $$ BEGIN RAISE EXCEPTION 'simulated failure'; END $$; "
                "COMMIT;",
                encoding="utf-8",
            )
            proc1 = _run_runner(tmpdir, dsn)
            assert proc1.returncode == 5, proc1.stdout + proc1.stderr
            assert "迁移失败" in proc1.stdout
            # 999 must NOT be in ledger.
            assert "999_always_fail.sql" not in _ledger(dsn)
            # The fake table must not exist.
            assert "should_not_exist" not in _list_tables(dsn)
    finally:
        _drop_database(name)


@pytest.mark.skipif(
    not _admin_dsn(), reason="TEST_PG_DSN not set; migration tests need PG"
)
def test_bootstrap_rejects_when_ledger_present(tmp_path):
    dsn, name = _isolated_database()
    try:
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            _copy_migrations_to(tmpdir)
            proc1 = _run_runner(tmpdir, dsn)
            assert proc1.returncode == 0
            proc2 = _run_runner(tmpdir, dsn, "--bootstrap-existing")
            assert proc2.returncode == 2
            assert "bootstrap" in proc2.stdout
    finally:
        _drop_database(name)


def test_compute_checksum_is_deterministic():
    """Without PG, exercise the checksum helper directly."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from migrations.apply_migrations import _compute_checksum

    a = _compute_checksum("foo.sql", "SELECT 1;")
    b = _compute_checksum("foo.sql", "SELECT 1;")
    c = _compute_checksum("foo.sql", "SELECT 2;")
    assert a == b
    assert a != c
    assert len(a) == 64  # SHA-256 hex digest
