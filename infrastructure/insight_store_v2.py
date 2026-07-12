"""Target InsightStore implementation (Milestone 2).

Persists only the target contract: claim_text / tags / scope / maturity /
status_reason / approved_by / approved_at / supersedes_claim_id /
created_by / created_at / updated_at. The legacy claim_type / dimension /
fact_ids / competitor_ids / product_ids / confidence_score / status JSONB
columns stay in the schema for the cut-over window but are never read or
written by this store.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

import psycopg2
from psycopg2.extras import DictCursor, Json

from core.exceptions import StoreError
from models.target_insight import ClaimFactLink, ClaimMaturity, InsightClaim


def _enum_value(value):
    return value.value if isinstance(value, Enum) else value


def _now():
    return datetime.now()


class PostgresInsightStoreV2:
    """Target-shape Insight Claim store."""

    def __init__(self, dsn):
        self.dsn = dsn

    def _conn(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=DictCursor)
        conn.autocommit = True
        return conn

    def save_claim(self, claim):
        now = _now()
        if claim.created_at is None:
            claim.created_at = now
        claim.updated_at = now
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO insight_claims (
                        id, claim_text, tags, scope, maturity,
                        status_reason, approved_by, approved_at,
                        supersedes_claim_id, created_by, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        claim_text = EXCLUDED.claim_text,
                        tags = EXCLUDED.tags,
                        scope = EXCLUDED.scope,
                        status_reason = EXCLUDED.status_reason,
                        updated_at = EXCLUDED.updated_at
                    WHERE insight_claims.maturity IS NULL
                       OR insight_claims.maturity = 'draft'
                       OR insight_claims.maturity = 'hypothesis'
                    RETURNING *
                    """,
                    (
                        claim.id,
                        claim.claim_text,
                        Json(claim.tags) if claim.tags is not None else None,
                        Json(claim.scope) if claim.scope is not None else None,
                        _enum_value(claim.maturity),
                        claim.status_reason,
                        claim.approved_by,
                        claim.approved_at,
                        claim.supersedes_claim_id,
                        claim.created_by,
                        claim.created_at,
                        claim.updated_at,
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    raise StoreError(
                        f"claim {claim.id} is locked; use supersede_claim"
                    )
        return self._row_to_claim(row)

    def get_claim(self, claim_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM insight_claims WHERE id = %s", (claim_id,))
                row = cur.fetchone()
        return self._row_to_claim(row) if row else None

    def list_claims(self, filters=None, limit=50, offset=0):
        where, params = self._build_claim_filters(filters or {})
        sql = f"SELECT * FROM insight_claims {where} ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params = [*params, limit, offset]
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [self._row_to_claim(r) for r in rows]

    def update_claim_maturity(
        self, claim_id, maturity, status_reason="", *, approved_by=None, approved_at=None
    ):
        target = _enum_value(maturity)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE insight_claims
                          SET maturity = %s,
                              status_reason = %s,
                              approved_by = COALESCE(%s, approved_by),
                              approved_at = COALESCE(%s, approved_at),
                              updated_at = NOW()
                        WHERE id = %s
                        RETURNING *""",
                    (target, status_reason, approved_by, approved_at, claim_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise StoreError(f"claim {claim_id} not found")
        return self._row_to_claim(row)

    def replace_claim_facts(self, claim_id, links):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM claim_facts WHERE claim_id = %s", (claim_id,))
                for link in links:
                    cur.execute(
                        """INSERT INTO claim_facts (claim_id, fact_id, stance)
                           VALUES (%s, %s, %s)""",
                        (claim_id, link.fact_id, _enum_value(link.stance)),
                    )
        return len(links)

    def list_claim_facts(self, claim_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT claim_id, fact_id, stance, created_at FROM claim_facts WHERE claim_id=%s",
                    (claim_id,),
                )
                rows = cur.fetchall()
        return [
            ClaimFactLink(
                claim_id=r["claim_id"],
                fact_id=r["fact_id"],
                stance=r["stance"],
                created_at=r.get("created_at"),
            )
            for r in rows
        ]

    def find_claims_by_fact(self, fact_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT c.* FROM insight_claims c
                         JOIN claim_facts cf ON cf.claim_id = c.id
                        WHERE cf.fact_id = %s""",
                    (fact_id,),
                )
                rows = cur.fetchall()
        return [self._row_to_claim(r) for r in rows]

    def mark_dependent_supported_claims_needs_review(self, fact_id, status_reason):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE insight_claims c
                          SET maturity = 'needs_review',
                              status_reason = %s,
                              updated_at = NOW()
                        WHERE c.maturity = 'supported'
                          AND EXISTS (
                              SELECT 1 FROM claim_facts cf
                               WHERE cf.claim_id = c.id AND cf.fact_id = %s
                          )
                        RETURNING *""",
                    (status_reason, fact_id),
                )
                rows = cur.fetchall()
        return [self._row_to_claim(r) for r in rows]

    @staticmethod
    def _build_claim_filters(filters):
        clauses = []
        params = []
        target_only = filters.pop("target_only", True)
        if target_only:
            clauses.append("insight_claims.maturity IS NOT NULL")
        for key in ("maturity", "approved_by", "created_by"):
            value = filters.get(key)
            if value is None:
                continue
            clauses.append(f"insight_claims.{key} = %s")
            params.append(value)
        if filters.get("tag"):
            clauses.append("insight_claims.tags @> %s::jsonb")
            params.append(Json([filters["tag"]]))
        if "fact_id" in filters:
            clauses.append(
                "EXISTS (SELECT 1 FROM claim_facts cf "
                " WHERE cf.claim_id = insight_claims.id AND cf.fact_id = %s)"
            )
            params.append(filters["fact_id"])
        if "competitor_id" in filters:
            clauses.append(
                """EXISTS (
                     SELECT 1 FROM claim_facts cf
                       JOIN intel_fact_competitors ifc ON ifc.fact_id = cf.fact_id
                      WHERE cf.claim_id = insight_claims.id
                        AND ifc.competitor_id = %s
                        AND ifc.role = 'subject'
                        AND ifc.review_status = 'confirmed')"""
            )
            params.append(filters["competitor_id"])
        if "product_id" in filters:
            clauses.append(
                """EXISTS (
                     SELECT 1 FROM claim_facts cf
                       JOIN intel_fact_products ifp ON ifp.fact_id = cf.fact_id
                      WHERE cf.claim_id = insight_claims.id
                        AND ifp.product_id = %s
                        AND ifp.role = 'subject'
                        AND ifp.review_status = 'confirmed')"""
            )
            params.append(filters["product_id"])
        if filters.get("keyword"):
            clauses.append("insight_claims.claim_text ILIKE %s")
            params.append(f"%{filters['keyword']}%")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    @staticmethod
    def _row_to_claim(row):
        tags = row.get("tags")
        if isinstance(tags, str):
            import json as _json
            tags = _json.loads(tags)
        scope = row.get("scope")
        if isinstance(scope, str):
            import json as _json
            scope = _json.loads(scope)
        return InsightClaim(
            id=row["id"],
            claim_text=row["claim_text"] or "",
            tags=tags or [],

            scope=scope,
            maturity=row.get("maturity"),
            status_reason=row.get("status_reason") or "",
            approved_by=row.get("approved_by"),
            approved_at=row.get("approved_at"),
            supersedes_claim_id=row.get("supersedes_claim_id"),
            created_by=row.get("created_by") or "system",
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )