"""Target IntelStore implementation for the three-layer model (Milestone 2).

Persists only the target contract:
  * IntelFact with lifecycle_status / verification_status / normalized_data /
    occurred_at / valid_from / valid_to / time_precision / candidate_key /
    supersedes_fact_id / status_reason / created_by
  * EvidenceReference with immutable anchor fields (document_version_id,
    source_occurrence_id, quoted_text, quote_hash, locator)
  * fact_evidence relations carrying stance
  * intel_fact_competitors / intel_fact_products with target role /
    review_status (no confidence_score)

Legacy columns remain on the table to keep the cut-over window cheap, but
the v2 store never reads or writes them.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Any

import psycopg2
from psycopg2.extras import DictCursor, Json

from core.exceptions import StoreError
from models.target_evidence import EvidenceReference
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


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _coerce_ts(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _now() -> datetime:
    return datetime.now()


def compute_quote_hash(quoted_text: str) -> str:
    return hashlib.sha256(quoted_text.encode("utf-8")).hexdigest()


class PostgresIntelStoreV2:
    """Target-shape Intel Fact store."""

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=DictCursor)
        conn.autocommit = True
        return conn

    # ---- facts -------------------------------------------------------

    def save_fact(self, fact: IntelFact) -> IntelFact:
        now = _now()
        if fact.created_at is None:
            fact.created_at = now
        fact.updated_at = now
        lifecycle = (
            _enum_value(fact.lifecycle_status)
            or FactLifecycleStatus.DRAFT.value
        )
        verification = (
            _enum_value(fact.verification_status) or "single_source"
        )
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intel_facts (
                        id, fact_type, fact_text, normalized_data,
                        occurred_at, valid_from, valid_to, time_precision,
                        candidate_key, lifecycle_status, verification_status,
                        status_reason, supersedes_fact_id, created_by,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        fact_text = EXCLUDED.fact_text,
                        normalized_data = EXCLUDED.normalized_data,
                        occurred_at = EXCLUDED.occurred_at,
                        valid_from = EXCLUDED.valid_from,
                        valid_to = EXCLUDED.valid_to,
                        time_precision = EXCLUDED.time_precision,
                        candidate_key = EXCLUDED.candidate_key,
                        status_reason = EXCLUDED.status_reason,
                        supersedes_fact_id = EXCLUDED.supersedes_fact_id,
                        updated_at = EXCLUDED.updated_at
                    WHERE intel_facts.lifecycle_status IS NULL
                       OR intel_facts.lifecycle_status = 'draft'
                    RETURNING *
                    """,
                    (
                        fact.id,
                        _enum_value(fact.fact_type),
                        fact.fact_text,
                        Json(fact.normalized_data)
                        if fact.normalized_data is not None
                        else None,
                        _coerce_ts(fact.occurred_at),
                        _coerce_ts(fact.valid_from),
                        _coerce_ts(fact.valid_to),
                        _enum_value(fact.time_precision),
                        fact.candidate_key,
                        lifecycle,
                        verification,
                        fact.status_reason,
                        fact.supersedes_fact_id,
                        fact.created_by,
                        fact.created_at,
                        fact.updated_at,
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    raise StoreError(
                        f"fact {fact.id} cannot be mutated "
                        f"(current lifecycle is not draft)"
                    )
        return self._row_to_fact(row)

    def get_fact(self, fact_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM intel_facts WHERE id = %s", (fact_id,))
                row = cur.fetchone()
        return self._row_to_fact(row) if row else None

    def list_facts(self, filters=None, limit=50, offset=0):
        where, params = self._build_fact_filters(filters or {})
        sql = f"SELECT * FROM intel_facts {where} ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params = [*params, limit, offset]
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [self._row_to_fact(r) for r in rows]

    def find_fact_candidates(self, candidate_key, limit=20):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM intel_facts WHERE candidate_key = %s AND lifecycle_status IS NOT NULL ORDER BY created_at DESC LIMIT %s",
                    (candidate_key, limit),
                )
                rows = cur.fetchall()
        return [self._row_to_fact(r) for r in rows]

    def update_fact_lifecycle(self, fact_id, lifecycle_status, status_reason=""):
        target = _enum_value(lifecycle_status)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE intel_facts SET lifecycle_status=%s, status_reason=%s, updated_at=NOW() WHERE id=%s RETURNING *",
                    (target, status_reason, fact_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise StoreError(f"fact {fact_id} not found")
        return self._row_to_fact(row)

    def update_fact_verification(self, fact_id, verification_status, status_reason=""):
        target = _enum_value(verification_status)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE intel_facts SET verification_status=%s, status_reason=%s, updated_at=NOW() WHERE id=%s RETURNING *",
                    (target, status_reason, fact_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise StoreError(f"fact {fact_id} not found")
        return self._row_to_fact(row)

    @staticmethod
    def _build_fact_filters(filters):
        clauses = []
        params = []
        target_only = filters.pop("target_only", True)
        if target_only:
            clauses.append("intel_facts.lifecycle_status IS NOT NULL")
        for key in ("lifecycle_status", "verification_status", "fact_type", "time_precision", "candidate_key"):
            value = filters.get(key)
            if value is None:
                continue
            column = "verification_status" if key == "verification_status" else key
            clauses.append(f"intel_facts.{column} = %s")
            params.append(_enum_value(value))
        if "subject_competitor_id" in filters:
            clauses.append("EXISTS (SELECT 1 FROM intel_fact_competitors c WHERE c.fact_id = intel_facts.id AND c.competitor_id = %s AND c.role = 'subject' AND c.review_status = 'confirmed')")
            params.append(filters["subject_competitor_id"])
        if "subject_product_id" in filters:
            clauses.append("EXISTS (SELECT 1 FROM intel_fact_products p WHERE p.fact_id = intel_facts.id AND p.product_id = %s AND p.role = 'subject' AND p.review_status = 'confirmed')")
            params.append(filters["subject_product_id"])
        if "occurred_from" in filters:
            clauses.append("intel_facts.occurred_at >= %s")
            params.append(filters["occurred_from"])
        if "occurred_to" in filters:
            clauses.append("intel_facts.occurred_at <= %s")
            params.append(filters["occurred_to"])
        if filters.get("keyword"):
            clauses.append("intel_facts.fact_text ILIKE %s")
            params.append(f"%{filters['keyword']}%")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    @staticmethod
    def _row_to_fact(row):
        return IntelFact(
            id=row["id"],
            fact_type=row["fact_type"],
            fact_text=row["fact_text"] or "",
            normalized_data=row.get("normalized_data"),
            occurred_at=row.get("occurred_at"),
            valid_from=row.get("valid_from"),
            valid_to=row.get("valid_to"),
            time_precision=row.get("time_precision"),
            candidate_key=row.get("candidate_key"),
            lifecycle_status=row.get("lifecycle_status"),
            verification_status=row.get("verification_status"),
            status_reason=row.get("status_reason") or "",
            supersedes_fact_id=row.get("supersedes_fact_id"),
            created_by=row.get("created_by") or "system",
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


    # ---- evidence anchor ---------------------------------------------

    def save_evidence_reference(self, evidence):
        quote_hash = evidence.quote_hash or compute_quote_hash(evidence.quoted_text)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO evidence_refs (
                        id, document_version_id, source_occurrence_id,
                        quoted_text, quote_hash, locator, parent_chunk_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        quoted_text = EXCLUDED.quoted_text,
                        quote_hash = EXCLUDED.quote_hash,
                        locator = EXCLUDED.locator
                    WHERE evidence_refs.quoted_text IS NULL
                    RETURNING *
                    """,
                    (
                        evidence.id,
                        evidence.document_version_id,
                        evidence.source_occurrence_id,
                        evidence.quoted_text,
                        quote_hash,
                        Json(evidence.locator) if evidence.locator is not None else None,
                        evidence.parent_chunk_id,
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    raise StoreError(f"evidence {evidence.id} is already anchored")
        return self._row_to_evidence(row)

    def get_evidence_reference(self, evidence_ref_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM evidence_refs WHERE id = %s", (evidence_ref_id,))
                row = cur.fetchone()
        return self._row_to_evidence(row) if row else None

    def find_evidence_by_anchor(self, document_version_id, source_occurrence_id, quote_hash):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM evidence_refs WHERE document_version_id=%s AND source_occurrence_id=%s AND quote_hash=%s",
                    (document_version_id, source_occurrence_id, quote_hash),
                )
                row = cur.fetchone()
        return self._row_to_evidence(row) if row else None

    @staticmethod
    def _row_to_evidence(row):
        return EvidenceReference(
            id=row["id"],
            document_version_id=row["document_version_id"] or "",
            source_occurrence_id=row["source_occurrence_id"] or "",
            quoted_text=row["quoted_text"] or "",
            quote_hash=row["quote_hash"] or "",
            locator=row.get("locator"),
            parent_chunk_id=row.get("parent_chunk_id"),
            created_at=row.get("created_at"),
        )

    # ---- fact ↔ evidence ----------------------------------------------

    def link_fact_evidence(self, link):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO fact_evidence (fact_id, evidence_ref_id, stance)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (fact_id, evidence_ref_id) DO UPDATE SET stance = EXCLUDED.stance
                       RETURNING fact_id, evidence_ref_id, stance, created_at""",
                    (link.fact_id, link.evidence_ref_id, _enum_value(link.stance)),
                )
                row = cur.fetchone()
        if row is None:
            raise StoreError("failed to insert fact_evidence")
        return FactEvidenceLink(
            fact_id=row["fact_id"],
            evidence_ref_id=row["evidence_ref_id"],
            stance=row["stance"],
            created_at=row.get("created_at"),
        )

    def list_fact_evidence(self, fact_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT fact_id, evidence_ref_id, stance, created_at FROM fact_evidence WHERE fact_id = %s",
                    (fact_id,),
                )
                rows = cur.fetchall()
        return [
            FactEvidenceLink(
                fact_id=r["fact_id"],
                evidence_ref_id=r["evidence_ref_id"],
                stance=r["stance"],
                created_at=r.get("created_at"),
            )
            for r in rows
        ]

    def move_fact_evidence(self, source_fact_id, target_fact_id, evidence_ref_ids):
        if not evidence_ref_ids:
            return 0
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE fact_evidence SET fact_id = %s WHERE fact_id = %s AND evidence_ref_id = ANY(%s)",
                    (target_fact_id, source_fact_id, evidence_ref_ids),
                )
                return cur.rowcount

    def delete_fact_evidence(self, fact_id, evidence_ref_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM fact_evidence WHERE fact_id=%s AND evidence_ref_id=%s",
                    (fact_id, evidence_ref_id),
                )

    # ---- fact ↔ competitor / product ---------------------------------

    def link_fact_to_competitor(self, link):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO intel_fact_competitors
                       (fact_id, competitor_id, relation_type, role, review_status)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (fact_id, competitor_id, relation_type) DO UPDATE SET
                         role = EXCLUDED.role,
                         review_status = EXCLUDED.review_status""",
                    (
                        link.fact_id,
                        link.competitor_id,
                        _enum_value(link.role),
                        _enum_value(link.role),
                        _enum_value(link.review_status),
                    ),
                )
        return link

    def unlink_fact_from_competitor(self, fact_id, competitor_id, role=None):
        sql = "DELETE FROM intel_fact_competitors WHERE fact_id=%s AND competitor_id=%s"
        params = [fact_id, competitor_id]
        if role is not None:
            sql += " AND role=%s"
            params.append(role)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)

    def list_fact_competitors(self, fact_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT fact_id, competitor_id, role, review_status, created_at FROM intel_fact_competitors WHERE fact_id=%s",
                    (fact_id,),
                )
                rows = cur.fetchall()
        return [
            IntelFactCompetitorLink(
                fact_id=r["fact_id"],
                competitor_id=r["competitor_id"],
                role=r["role"],
                review_status=r["review_status"],
                created_at=r.get("created_at"),
            )
            for r in rows
        ]

    def link_fact_to_product(self, link):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO intel_fact_products
                       (fact_id, product_id, relation_type, role, review_status)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (fact_id, product_id, relation_type) DO UPDATE SET
                         role = EXCLUDED.role,
                         review_status = EXCLUDED.review_status""",
                    (
                        link.fact_id,
                        link.product_id,
                        _enum_value(link.role),
                        _enum_value(link.role),
                        _enum_value(link.review_status),
                    ),
                )
        return link

    def unlink_fact_from_product(self, fact_id, product_id, role=None):
        sql = "DELETE FROM intel_fact_products WHERE fact_id=%s AND product_id=%s"
        params = [fact_id, product_id]
        if role is not None:
            sql += " AND role=%s"
            params.append(role)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)

    def list_fact_products(self, fact_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT fact_id, product_id, role, review_status, created_at FROM intel_fact_products WHERE fact_id=%s",
                    (fact_id,),
                )
                rows = cur.fetchall()
        return [
            IntelFactProductLink(
                fact_id=r["fact_id"],
                product_id=r["product_id"],
                role=r["role"],
                review_status=r["review_status"],
                created_at=r.get("created_at"),
            )
            for r in rows
        ]

    def resolve_evidence_context(self, *, document_version_id, source_occurrence_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT v.id AS document_version_id,
                              v.document_id AS document_cluster_id,
                              o.id AS source_occurrence_id,
                              o.source_profile_revision_id,
                              o.source_tier,
                              o.source_kind,
                              v.content
                         FROM source_document_versions v
                         JOIN source_occurrences o ON o.document_id = v.document_id
                        WHERE v.id = %s AND o.id = %s""",
                    (document_version_id, source_occurrence_id),
                )
                row = cur.fetchone()
        if row is None:
            raise StoreError(
                f"no active document version {document_version_id} for occurrence {source_occurrence_id}"
            )
        return dict(row)
