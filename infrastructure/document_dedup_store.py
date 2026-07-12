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
from services.document_fingerprint_service import hamming_distance, shingle_similarity


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
            matched = exact
            assessment = None
            if not exact:
                matched, assessment = self._find_near_duplicate(cur, occurrence)
            auto_duplicate = exact is not None or (assessment and assessment[0] is DedupDecision.DUPLICATE)
            document_id = str(matched["document_id"]) if auto_duplicate else (occurrence.document_id or str(uuid4()))
            created_cluster = not auto_duplicate
            if created_cluster:
                cur.execute("INSERT INTO document_clusters (id) VALUES (%s)", (document_id,))
            saved = replace(occurrence, document_id=document_id)
            self._insert_occurrence(cur, saved)
            decision = DedupDecision.NEW_CLUSTER if created_cluster else DedupDecision.DUPLICATE
            promoted = False
            if created_cluster:
                cur.execute(
                    "UPDATE document_clusters SET canonical_occurrence_id=%s WHERE id=%s",
                    (saved.id, document_id),
                )
            elif auto_duplicate and self._should_promote(cur, saved):
                cur.execute(
                    "UPDATE document_clusters SET canonical_occurrence_id=%s WHERE id=%s",
                    (saved.id, document_id),
                )
                decision = DedupDecision.CANONICAL_PROMOTED
                promoted = True
            if assessment and assessment[0] is DedupDecision.REVIEW_REQUIRED:
                decision = DedupDecision.REVIEW_REQUIRED
                self._insert_candidate(cur, saved.id, str(matched["id"]), assessment)
            return DedupCommitResult(
                saved,
                decision,
                created_cluster,
                promoted or created_cluster or self._requires_build(cur, document_id),
            )

    @staticmethod
    def _should_promote(cur, incoming: SourceOccurrence) -> bool:
        cur.execute(
            """SELECT occurrence.source_tier, occurrence.content_length
               FROM document_clusters cluster
               JOIN source_occurrences occurrence ON occurrence.id=cluster.canonical_occurrence_id
               WHERE cluster.id=%s""",
            (incoming.document_id,),
        )
        current = cur.fetchone()
        if not current:
            return True
        tier_rank = {"A": 4, "B": 3, "C": 2, "D": 1, "unknown": 0}
        current_length = int(current.get("content_length") or 0)
        complete_enough = current_length == 0 or incoming.content_length >= current_length * 0.7
        return complete_enough and tier_rank.get(incoming.source_tier, 0) > tier_rank.get(current["source_tier"], 0)

    @staticmethod
    def _find_near_duplicate(cur, occurrence: SourceOccurrence):
        cur.execute(
            """SELECT * FROM source_occurrences
               WHERE algorithm_version=%s AND (high_bands && %s OR gray_bands && %s)
               ORDER BY observed_at, id""",
            (occurrence.simhash.algorithm_version, list(occurrence.simhash.high_bands), list(occurrence.simhash.gray_bands)),
        )
        best = None
        for row in cur.fetchall():
            candidate_value = _from_pg_bigint(int(row["simhash"]))
            distance = hamming_distance(occurrence.simhash.value, candidate_value)
            if distance > 6 or len(occurrence.shingles) < 3 or len(row.get("shingles") or ()) < 3:
                continue
            jaccard, containment = shingle_similarity(set(occurrence.shingles), set(row["shingles"]))
            decision = DedupDecision.DUPLICATE if jaccard >= 0.72 or containment >= 0.86 else DedupDecision.REVIEW_REQUIRED
            score = (decision is DedupDecision.DUPLICATE, jaccard, containment, -distance)
            if best is None or score > best[0]:
                best = (score, row, (decision, distance, jaccard, containment))
        return (best[1], best[2]) if best else (None, None)

    @staticmethod
    def _insert_candidate(cur, left_id: str, right_id: str, assessment) -> None:
        decision, distance, jaccard, containment = assessment
        left, right = sorted((left_id, right_id))
        cur.execute(
            """INSERT INTO duplicate_candidates
               (id, left_occurrence_id, right_occurrence_id, hamming_distance,
                shingle_jaccard, shingle_containment, decision, reason)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (left_occurrence_id, right_occurrence_id) DO NOTHING""",
            (str(uuid4()), left, right, distance, jaccard, containment, decision.value, "gray_candidate_requires_review"),
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

    def list_occurrences(self, *, limit: int = 1000, offset: int = 0) -> list[SourceOccurrence]:
        """按稳定顺序枚举权威 occurrence，供可重建缓存分批恢复。"""
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM source_occurrences ORDER BY observed_at, id LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [self._occurrence(row) for row in cur.fetchall()]

    def list_candidates(self, *, limit: int = 100, offset: int = 0) -> list[DuplicateCandidate]:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM duplicate_candidates ORDER BY created_at DESC, id LIMIT %s OFFSET %s", (limit, offset))
            return [DuplicateCandidate(
                left_occurrence_id=str(row["left_occurrence_id"]),
                right_occurrence_id=str(row["right_occurrence_id"]),
                hamming_distance=row["hamming_distance"],
                shingle_jaccard=row["shingle_jaccard"],
                shingle_containment=row["shingle_containment"],
                decision=DedupDecision(row["decision"]), reason=row.get("reason", ""), id=str(row["id"]),
            ) for row in cur.fetchall()]

    def set_canonical(self, document_id: str, occurrence_id: str, *, actor: str, reason: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT canonical_occurrence_id FROM document_clusters WHERE id=%s FOR UPDATE", (document_id,))
            row = cur.fetchone()
            if not row:
                raise KeyError(f"document cluster not found: {document_id}")
            cur.execute("SELECT 1 FROM source_occurrences WHERE id=%s AND document_id=%s", (occurrence_id, document_id))
            if not cur.fetchone():
                raise ValueError("occurrence does not belong to document cluster")
            cur.execute("UPDATE document_clusters SET canonical_occurrence_id=%s WHERE id=%s", (occurrence_id, document_id))
            cur.execute(
                "INSERT INTO governance_audit_log(action, entity_type, entity_id, actor, reason, before_state, after_state) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                ("promote_source", "document_cluster", document_id, actor, reason,
                 psycopg2.extras.Json({"canonical_occurrence_id": row[0]}),
                 psycopg2.extras.Json({"canonical_occurrence_id": occurrence_id})),
            )

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
                source_tier, source_kind, shingles, content_length, observed_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,NOW()))""",
            (item.id, item.document_id, item.url, item.normalized_url, item.title,
             item.content_hash, _to_pg_bigint(item.simhash.value), list(item.simhash.high_bands),
             list(item.simhash.gray_bands), item.simhash.algorithm_version,
             item.source_profile_revision_id, item.source_tier, item.source_kind,
             list(item.shingles), item.content_length, item.observed_at),
        )

    @staticmethod
    def _occurrence(row) -> SourceOccurrence:
        return SourceOccurrence(
            id=str(row["id"]), document_id=str(row["document_id"]), url=row["url"],
            normalized_url=row["normalized_url"], title=row["title"], content_hash=row["content_hash"],
            simhash=SimHashFingerprint(_from_pg_bigint(int(row["simhash"])), tuple(row["high_bands"]), tuple(row["gray_bands"]), row["algorithm_version"]),
            source_profile_revision_id=row["source_profile_revision_id"], source_tier=row["source_tier"],
            source_kind=row["source_kind"], observed_at=row["observed_at"],
            shingles=tuple(row.get("shingles") or ()), content_length=int(row.get("content_length") or 0),
        )

    @staticmethod
    def _version(row) -> DocumentVersion:
        return DocumentVersion(id=str(row["id"]), document_id=str(row["document_id"]), version=row["version"], content=row["content"], content_hash=row["content_hash"], status=row["status"], created_at=row["created_at"])
