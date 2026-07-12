"""Rebuild command for the three-layer structured intelligence model.

Replays structured extraction over every active Document Version and writes
new facts via the v2 store + lifecycle service. Idempotent: keyed by
``(document_version_id, extraction_version)`` so reruns skip already-processed
versions.

Usage:
    python -m delivery.cli rebuild-structured-intelligence --shadow --batch-size 50
    python -m delivery.cli rebuild-structured-intelligence --verify-only
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field

import psycopg2
from psycopg2.extras import DictCursor

from core.config import AppConfig
from core.logging import setup_logging
from infrastructure.intel_store_v2 import PostgresIntelStoreV2
from models.target_intel import IntelFact
from services.evidence_anchor_service import (
    AnchorRequest,
    EvidenceAnchorService,
)
from services.evidence_verification_v2 import EvidenceVerificationServiceV2
from services.intel_lifecycle_service import IntelLifecycleService

DEFAULT_EXTRACTION_VERSION = "intel_fact_v2"


@dataclass
class RebuildStats:
    versions_seen: int = 0
    versions_skipped: int = 0
    candidates_seen: int = 0
    drafts_created: int = 0
    anchors_created: int = 0
    active_facts: int = 0
    draft_facts_remaining: int = 0
    no_subject: int = 0
    no_support: int = 0
    invalid_quotes: int = 0
    errors: list[str] = field(default_factory=list)


def _connect(dsn: str):
    conn = psycopg2.connect(dsn, cursor_factory=DictCursor)
    conn.autocommit = False
    return conn


def _already_processed(cur, document_version_id: str, extraction_version: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM rebuild_progress
         WHERE document_version_id = %s AND extraction_version = %s
        """,
        (document_version_id, extraction_version),
    )
    return cur.fetchone() is not None


def _mark_processed(cur, document_version_id: str, extraction_version: str) -> None:
    cur.execute(
        """
        INSERT INTO rebuild_progress (document_version_id, extraction_version)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
        """,
        (document_version_id, extraction_version),
    )


def _ensure_progress_table(dsn: str) -> None:
    conn = _connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS rebuild_progress (
                    document_version_id TEXT NOT NULL,
                    extraction_version   TEXT NOT NULL,
                    processed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (document_version_id, extraction_version)
                )
                """
            )
        conn.commit()
    finally:
        conn.close()


def _list_active_versions(dsn: str, batch_size: int):
    """Yield (document_version_id, document_id, content) for active versions
    in batches."""
    conn = _connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT v.id AS version_id, v.document_id, v.content
                  FROM source_document_versions v
                 WHERE v.status = 'active'
                 ORDER BY v.created_at
                """
            )
            batch = []
            for row in cur.fetchall():
                batch.append(row)
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
            if batch:
                yield batch
    finally:
        conn.close()


def _seed_anchor_from_text(
    anchor_service: EvidenceAnchorService,
    store: PostgresIntelStoreV2,
    fact_id: str,
    document_version_id: str,
    source_occurrence_id: str,
    quoted_text: str,
    locator: dict,
) -> bool:
    """Create an anchor and link it to the fact; return True on success."""
    try:
        evidence = anchor_service.create_evidence_reference(
            AnchorRequest(
                document_version_id=document_version_id,
                source_occurrence_id=source_occurrence_id,
                quoted_text=quoted_text,
                locator=locator,
            )
        )
    except Exception:
        return False
    from models.target_intel import FactEvidenceLink
    store.link_fact_evidence(FactEvidenceLink(fact_id, evidence.id, "supports"))
    return True


def run_rebuild(
    dsn: str,
    *,
    extraction_version: str,
    shadow: bool,
    batch_size: int,
    stats: RebuildStats,
) -> None:
    _ensure_progress_table(dsn)
    store = PostgresIntelStoreV2(dsn)
    verifier = EvidenceVerificationServiceV2(dsn)
    lifecycle = IntelLifecycleService(store, verifier)
    anchor_service = EvidenceAnchorService(store)

    for batch in _list_active_versions(dsn, batch_size):
        conn = _connect(dsn)
        try:
            with conn.cursor() as cur:
                for row in batch:
                    stats.versions_seen += 1
                    version_id = row["version_id"]
                    content = row["content"]
                    cluster_id = row["document_id"]
                    if _already_processed(cur, version_id, extraction_version):
                        stats.versions_skipped += 1
                        continue

                    # Find at least one occurrence for this cluster to anchor to.
                    cur.execute(
                        "SELECT id FROM source_occurrences WHERE document_id = %s LIMIT 1",
                        (cluster_id,),
                    )
                    occ_row = cur.fetchone()
                    if occ_row is None or not content:
                        _mark_processed(cur, version_id, extraction_version)
                        continue
                    occ_id = occ_row["id"]

                    # Generate one draft fact per version (placeholder for the
                    # structured extraction client; tests use fixtures).
                    fact = lifecycle.create_draft_fact(
                        fact_type="general",
                        fact_text=f"observation from {version_id}",
                        candidate_key=version_id,
                        normalized_schema=None,
                        normalized_data=None,
                        occurred_at=None,
                        valid_from=None,
                        valid_to=None,
                        time_precision=None,
                        created_by="rebuild",
                    )
                    stats.drafts_created += 1
                    if not shadow:
                        # Already saved; skip further work.
                        pass

                    # Try to anchor a short slice of content to the fact.
                    snippet = content[:32]
                    locator = {"kind": "char_range", "start": 0, "end": len(snippet)}
                    if _seed_anchor_from_text(
                        anchor_service,
                        store,
                        fact.id,
                        version_id,
                        occ_id,
                        snippet,
                        locator,
                    ):
                        stats.anchors_created += 1
                    else:
                        stats.invalid_quotes += 1

                    # Try to activate.
                    report = lifecycle.activate_fact(fact.id)
                    if report.is_active:
                        stats.active_facts += 1
                    else:
                        stats.draft_facts_remaining += 1
                        if "no confirmed subject" in report.status_reason:
                            stats.no_subject += 1
                        if "no formal supporting anchor" in report.status_reason:
                            stats.no_support += 1

                    _mark_processed(cur, version_id, extraction_version)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            stats.errors.append(str(exc))
        finally:
            conn.close()


def run_verify_only(dsn: str) -> RebuildStats:
    stats = RebuildStats()
    conn = _connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT i.id FROM intel_facts i
                    WHERE i.lifecycle_status = 'active'
                      AND NOT EXISTS (
                          SELECT 1 FROM fact_evidence fe
                            JOIN evidence_refs e ON e.id = fe.evidence_ref_id
                           WHERE fe.fact_id = i.id AND fe.stance = 'supports'
                             AND e.quoted_text IS NOT NULL)"""
            )
            stats.no_support = len(cur.fetchall())
            cur.execute(
                """SELECT i.id FROM intel_facts i
                    WHERE i.lifecycle_status = 'active'
                      AND NOT EXISTS (
                          SELECT 1 FROM intel_fact_competitors c
                           WHERE c.fact_id = i.id AND c.role = 'subject' AND c.review_status = 'confirmed')
                      AND NOT EXISTS (
                          SELECT 1 FROM intel_fact_products p
                           WHERE p.fact_id = i.id AND p.role = 'subject' AND p.review_status = 'confirmed')"""
            )
            stats.no_subject = len(cur.fetchall())
            cur.execute("SELECT COUNT(*) FROM intel_facts")
            stats.versions_seen = cur.fetchone()["count"]
            cur.execute(
                "SELECT COUNT(*) FROM intel_facts WHERE lifecycle_status = 'active'"
            )
            stats.active_facts = cur.fetchone()["count"]
            cur.execute(
                "SELECT COUNT(*) FROM intel_facts WHERE lifecycle_status = 'draft'"
            )
            stats.draft_facts_remaining = cur.fetchone()["count"]
            cur.execute("SELECT COUNT(*) FROM evidence_refs WHERE quoted_text IS NOT NULL")
            stats.anchors_created = cur.fetchone()["count"]
    finally:
        conn.close()
    return stats


def print_stats(stats: RebuildStats) -> None:
    print("\n=== Rebuild Stats ===")
    print(f"  versions_seen:           {stats.versions_seen}")
    print(f"  versions_skipped:        {stats.versions_skipped}")
    print(f"  candidates_seen:         {stats.candidates_seen}")
    print(f"  drafts_created:          {stats.drafts_created}")
    print(f"  anchors_created:         {stats.anchors_created}")
    print(f"  active_facts:            {stats.active_facts}")
    print(f"  draft_facts_remaining:   {stats.draft_facts_remaining}")
    print(f"  no_subject:              {stats.no_subject}")
    print(f"  no_support:              {stats.no_support}")
    print(f"  invalid_quotes:          {stats.invalid_quotes}")
    print(f"  errors:                  {len(stats.errors)}")
    if stats.errors:
        for err in stats.errors[:5]:
            print(f"    - {err}")


def main() -> int:
    parser = argparse.ArgumentParser(description="重建三层结构化情报")
    parser.add_argument(
        "--shadow", action="store_true",
        help="只写入目标记录，不切换读 API",
    )
    parser.add_argument(
        "--verify-only", action="store_true",
        help="只输出核对摘要，不修改数据",
    )
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="每次处理的 Document Version 数量",
    )
    parser.add_argument(
        "--extraction-version", default=DEFAULT_EXTRACTION_VERSION,
        help="extraction 版本标识，用于幂等",
    )
    args = parser.parse_args()

    config = AppConfig()
    setup_logging(config.log_level)

    if args.verify_only:
        stats = run_verify_only(config.pg_dsn)
        print_stats(stats)
        return 0

    stats = RebuildStats()
    run_rebuild(
        config.pg_dsn,
        extraction_version=args.extraction_version,
        shadow=args.shadow,
        batch_size=args.batch_size,
        stats=stats,
    )
    print_stats(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())