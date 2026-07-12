"""PostgreSQL 权威去重存储。"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any
from uuid import uuid4

import psycopg2
import psycopg2.extras

from models.document_governance import (
    DedupCommitResult,
    DedupDecision,
    DocumentVersion,
    DuplicateCandidate,
    SimHashFingerprint,
    SourceOccurrence,
)


def advisory_lock_keys(fingerprint: SimHashFingerprint) -> list[int]:
    """生成稳定且有序的锁键，统一加锁顺序可避免 worker 之间死锁。"""
    tokens = {
        f"{fingerprint.algorithm_version}:h:{index}:{value}"
        for index, value in enumerate(fingerprint.high_bands)
    }
    keys = []
    for token in tokens:
        raw = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        keys.append(int.from_bytes(raw, "big", signed=True))
    return sorted(set(keys))


def _to_pg_bigint(value: int) -> int:
    return value - (1 << 64) if value >= (1 << 63) else value


def _from_pg_bigint(value: int) -> int:
    return value + (1 << 64) if value < 0 else value


class PostgresDocumentDedupStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        return psycopg2.connect(self.dsn)

    def find_exact(self, content_hash: str) -> list[SourceOccurrence]:
        return self._find("content_hash = %s", (content_hash,))

    def find_by_bands(self, fingerprint: SimHashFingerprint) -> list[SourceOccurrence]:
        return self._find(
            "algorithm_version = %s AND (high_bands && %s OR gray_bands && %s)",
            (fingerprint.algorithm_version, list(fingerprint.high_bands), list(fingerprint.gray_bands)),
        )

    def commit_occurrence(self, occurrence: SourceOccurrence) -> DedupCommitResult:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Redis 锁不具备正确性语义；事务锁覆盖候选复查和最终写入。
            for key in advisory_lock_keys(occurrence.simhash):
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
            cur.execute("SELECT * FROM source_occurrences WHERE normalized_url = %s", (occurrence.normalized_url,))
            existing_url = cur.fetchone()
            if existing_url:
                saved = self._occurrence(existing_url)
                return DedupCommitResult(
                    saved,
                    DedupDecision.UNCHANGED,
                    False,
                    self._requires_build(cur, saved.document_id),
                )
            cur.execute(
                "SELECT document_id FROM source_occurrences WHERE content_hash = %s ORDER BY observed_at, id LIMIT 1",
                (occurrence.content_hash,),
            )
            exact = cur.fetchone()
            document_id = str(exact["document_id"]) if exact else (occurrence.document_id or str(uuid4()))
            created_cluster = exact is None
            if created_cluster:
                cur.execute("INSERT INTO document_clusters (id) VALUES (%s)", (document_id,))
            saved = replace(occurrence, document_id=document_id)
            self._insert_occurrence(cur, saved)
            decision = DedupDecision.NEW_CLUSTER if created_cluster else DedupDecision.DUPLICATE
            return DedupCommitResult(
                saved,
                decision,
                created_cluster,
                created_cluster or self._requires_build(cur, document_id),
            )

    def commit_decision(self, decision: DuplicateCandidate) -> DuplicateCandidate:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO duplicate_candidates
                   (id, left_occurrence_id, right_occurrence_id, hamming_distance,
                    shingle_jaccard, shingle_containment, decision, reason)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (left_occurrence_id, right_occurrence_id) DO UPDATE SET
                    hamming_distance=EXCLUDED.hamming_distance,
                    shingle_jaccard=EXCLUDED.shingle_jaccard,
                    shingle_containment=EXCLUDED.shingle_containment,
                    decision=EXCLUDED.decision, reason=EXCLUDED.reason""",
                (decision.id, decision.left_occurrence_id, decision.right_occurrence_id,
                 decision.hamming_distance, decision.shingle_jaccard, decision.shingle_containment,
                 decision.decision.value, decision.reason),
            )
        return decision

    def get_active_version(self, document_id: str) -> DocumentVersion | None:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM source_document_versions WHERE document_id=%s AND status='active'", (document_id,))
            row = cur.fetchone()
        return self._version(row) if row else None

    def create_version(self, document_id: str, content: str, content_hash: str) -> DocumentVersion:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 同一文档簇串行分配版本号，避免并发构建得到相同 version。
            lock_key = int.from_bytes(hashlib.blake2b(document_id.encode("utf-8"), digest_size=8).digest(), "big", signed=True)
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            cur.execute("SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM source_document_versions WHERE document_id=%s", (document_id,))
            next_version = cur.fetchone()["next_version"]
            version_id = str(uuid4())
            cur.execute(
                """INSERT INTO source_document_versions
                   (id, document_id, version, content, content_hash, status)
                   VALUES (%s,%s,%s,%s,%s,'building') RETURNING *""",
                (version_id, document_id, next_version, content, content_hash),
            )
            row = cur.fetchone()
        return self._version(row)

    def activate_version(self, document_id: str, version_id: str) -> DocumentVersion:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("UPDATE source_document_versions SET status='superseded' WHERE document_id=%s AND status='active'", (document_id,))
            cur.execute("UPDATE source_document_versions SET status='active' WHERE id=%s AND document_id=%s RETURNING *", (version_id, document_id))
            row = cur.fetchone()
            if not row:
                raise KeyError(f"document version not found: {version_id}")
            cur.execute("UPDATE document_clusters SET active_version_id=%s WHERE id=%s", (version_id, document_id))
        return self._version(row)

    def fail_version(self, document_id: str, version_id: str) -> DocumentVersion:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """UPDATE source_document_versions SET status='failed'
                   WHERE id=%s AND document_id=%s AND status='building' RETURNING *""",
                (version_id, document_id),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError(f"building document version not found: {version_id}")
        return self._version(row)

    def _find(self, where: str, params: tuple[Any, ...]) -> list[SourceOccurrence]:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM source_occurrences WHERE {where} ORDER BY observed_at, id", params)
            return [self._occurrence(row) for row in cur.fetchall()]

    @staticmethod
    def _requires_build(cur, document_id: str) -> bool:
        # 构建状态必须可从 PostgreSQL 重放，不能依赖一次性的 new_cluster 返回值。
        cur.execute(
            "SELECT parse_status FROM source_documents WHERE document_id = %s",
            (document_id,),
        )
        row = cur.fetchone()
        return not row or row["parse_status"] != "vectorized"

    @staticmethod
    def _insert_occurrence(cur, item: SourceOccurrence) -> None:
        cur.execute(
            """INSERT INTO source_occurrences
               (id, document_id, url, normalized_url, title, content_hash, simhash,
                high_bands, gray_bands, algorithm_version, source_profile_revision_id,
                source_tier, source_kind, observed_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,NOW()))""",
            (item.id, item.document_id, item.url, item.normalized_url, item.title,
             item.content_hash, _to_pg_bigint(item.simhash.value), list(item.simhash.high_bands),
             list(item.simhash.gray_bands), item.simhash.algorithm_version,
             item.source_profile_revision_id, item.source_tier, item.source_kind, item.observed_at),
        )

    @staticmethod
    def _occurrence(row) -> SourceOccurrence:
        return SourceOccurrence(
            id=str(row["id"]), document_id=str(row["document_id"]), url=row["url"],
            normalized_url=row["normalized_url"], title=row["title"], content_hash=row["content_hash"],
            simhash=SimHashFingerprint(_from_pg_bigint(int(row["simhash"])), tuple(row["high_bands"]), tuple(row["gray_bands"]), row["algorithm_version"]),
            source_profile_revision_id=row["source_profile_revision_id"], source_tier=row["source_tier"],
            source_kind=row["source_kind"], observed_at=row["observed_at"],
        )

    @staticmethod
    def _version(row) -> DocumentVersion:
        return DocumentVersion(id=str(row["id"]), document_id=str(row["document_id"]), version=row["version"], content=row["content"], content_hash=row["content_hash"], status=row["status"], created_at=row["created_at"])
