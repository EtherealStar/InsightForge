"""PostgreSQL InsightStore implementation."""
from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

import psycopg2
from psycopg2.extras import DictCursor

from core.exceptions import StoreError
from models.evidence import EvidenceRef, EvidenceOwnerType, EvidenceType
from models.insight import ClaimStatus, ClaimType, InsightClaim


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _json_dumps(value: Any, default: Any) -> str:
    return json.dumps(default if value is None else value, ensure_ascii=False)


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        if not value:
            return default
        return json.loads(value)
    return value


def _safe_enum(enum_cls, value: Any, fallback):
    try:
        return enum_cls(value)
    except Exception:
        return fallback


class PostgresInsightStore:
    """Insight claim persistence backed by PostgreSQL."""

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=DictCursor)
        conn.autocommit = True
        return conn

    def save_claim(self, claim: InsightClaim) -> InsightClaim:
        now = datetime.now()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO insight_claims (
                        id, claim_text, claim_type, dimension, competitor_ids,
                        product_ids, fact_ids, confidence_score, limitations,
                        status, created_by, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        claim_text = EXCLUDED.claim_text,
                        claim_type = EXCLUDED.claim_type,
                        dimension = EXCLUDED.dimension,
                        competitor_ids = EXCLUDED.competitor_ids,
                        product_ids = EXCLUDED.product_ids,
                        fact_ids = EXCLUDED.fact_ids,
                        confidence_score = EXCLUDED.confidence_score,
                        limitations = EXCLUDED.limitations,
                        status = EXCLUDED.status,
                        created_by = EXCLUDED.created_by,
                        updated_at = NOW()
                    RETURNING *
                    """,
                    (
                        claim.id,
                        claim.claim_text,
                        _enum_value(claim.claim_type),
                        claim.dimension,
                        _json_dumps(claim.competitor_ids, []),
                        _json_dumps(claim.product_ids, []),
                        _json_dumps(claim.fact_ids, []),
                        claim.confidence_score,
                        claim.limitations,
                        _enum_value(claim.status),
                        claim.created_by,
                        claim.created_at or now,
                        claim.updated_at or now,
                    ),
                )
                row = cur.fetchone()
        saved = self._row_to_claim(row)
        saved.evidence_refs = [
            self._evidence_to_dict(e) for e in self._list_evidence(saved.id)
        ]
        return saved

    def get_claim(self, claim_id: str) -> InsightClaim | None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM insight_claims WHERE id = %s", (claim_id,))
                row = cur.fetchone()
        if not row:
            return None
        claim = self._row_to_claim(row)
        claim.evidence_refs = [
            self._evidence_to_dict(e) for e in self._list_evidence(claim.id)
        ]
        return claim

    def list_claims(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InsightClaim]:
        filters = filters or {}
        conditions: list[str] = []
        params: list[Any] = []

        for key in ("claim_type", "dimension", "status"):
            if filters.get(key):
                conditions.append(f"{key} = %s")
                params.append(filters[key])

        competitor_ids = filters.get("competitor_ids")
        if filters.get("competitor_id"):
            competitor_ids = [filters["competitor_id"]]
        if competitor_ids:
            for competitor_id in competitor_ids:
                conditions.append("competitor_ids @> %s::jsonb")
                params.append(json.dumps([competitor_id]))

        fact_ids = filters.get("fact_ids")
        if filters.get("fact_id"):
            fact_ids = [filters["fact_id"]]
        if fact_ids:
            for fact_id in fact_ids:
                conditions.append("fact_ids @> %s::jsonb")
                params.append(json.dumps([fact_id]))

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.extend([limit, offset])
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT * FROM insight_claims
                    {where}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
        claims = [self._row_to_claim(row) for row in rows]
        evidence_by_claim = self._evidence_by_claim([claim.id for claim in claims])
        for claim in claims:
            claim.evidence_refs = [
                self._evidence_to_dict(evidence)
                for evidence in evidence_by_claim.get(claim.id, [])
            ]
        return claims

    def update_claim_status(self, claim_id: str, status: str) -> InsightClaim:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE insight_claims
                    SET status = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (status, claim_id),
                )
                row = cur.fetchone()
        if not row:
            raise StoreError(f"InsightClaim not found: {claim_id}")
        return self._row_to_claim(row)

    def delete_claim(self, claim_id: str) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM evidence_refs WHERE owner_type = %s AND owner_id = %s",
                    (EvidenceOwnerType.INSIGHT_CLAIM.value, claim_id),
                )
                cur.execute("DELETE FROM insight_claims WHERE id = %s", (claim_id,))

    def attach_evidence(self, claim_id: str, evidence: EvidenceRef) -> EvidenceRef:
        evidence.owner_type = EvidenceOwnerType.INSIGHT_CLAIM
        evidence.owner_id = claim_id
        return self._save_evidence(evidence)

    def _save_evidence(self, evidence: EvidenceRef) -> EvidenceRef:
        now = datetime.now()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO evidence_refs (
                        id, owner_type, owner_id, source_document_id, parent_chunk_id,
                        url, title, snippet, quote_hash, evidence_type,
                        relevance_score, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        owner_type = EXCLUDED.owner_type,
                        owner_id = EXCLUDED.owner_id,
                        source_document_id = EXCLUDED.source_document_id,
                        parent_chunk_id = EXCLUDED.parent_chunk_id,
                        url = EXCLUDED.url,
                        title = EXCLUDED.title,
                        snippet = EXCLUDED.snippet,
                        quote_hash = EXCLUDED.quote_hash,
                        evidence_type = EXCLUDED.evidence_type,
                        relevance_score = EXCLUDED.relevance_score
                    RETURNING *
                    """,
                    (
                        evidence.id,
                        _enum_value(evidence.owner_type),
                        evidence.owner_id,
                        evidence.source_document_id,
                        evidence.parent_chunk_id,
                        evidence.url,
                        evidence.title,
                        evidence.snippet,
                        evidence.quote_hash,
                        _enum_value(evidence.evidence_type),
                        evidence.relevance_score,
                        evidence.created_at or now,
                    ),
                )
                row = cur.fetchone()
        return self._row_to_evidence(row)

    def _list_evidence(self, claim_id: str) -> list[EvidenceRef]:
        return self._evidence_by_claim([claim_id]).get(claim_id, [])

    def _evidence_by_claim(self, claim_ids: list[str]) -> dict[str, list[EvidenceRef]]:
        if not claim_ids:
            return {}
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM evidence_refs
                    WHERE owner_type = %s AND owner_id = ANY(%s)
                    ORDER BY created_at ASC
                    """,
                    (EvidenceOwnerType.INSIGHT_CLAIM.value, claim_ids),
                )
                rows = cur.fetchall()
        result: dict[str, list[EvidenceRef]] = {}
        for row in rows:
            result.setdefault(row["owner_id"], []).append(self._row_to_evidence(row))
        return result

    @staticmethod
    def _evidence_to_dict(evidence: EvidenceRef) -> dict[str, Any]:
        return {
            "id": evidence.id,
            "owner_type": _enum_value(evidence.owner_type),
            "owner_id": evidence.owner_id,
            "source_document_id": evidence.source_document_id,
            "parent_chunk_id": evidence.parent_chunk_id,
            "url": evidence.url,
            "title": evidence.title,
            "snippet": evidence.snippet,
            "quote_hash": evidence.quote_hash,
            "evidence_type": _enum_value(evidence.evidence_type),
            "relevance_score": evidence.relevance_score,
            "created_at": evidence.created_at,
        }

    @staticmethod
    def _row_to_claim(row) -> InsightClaim:
        return InsightClaim(
            id=row["id"],
            claim_text=row["claim_text"],
            claim_type=_safe_enum(ClaimType, row["claim_type"], ClaimType.FINDING),
            dimension=row["dimension"] or "general",
            competitor_ids=_json_loads(row["competitor_ids"], []),
            product_ids=_json_loads(row["product_ids"], []),
            fact_ids=_json_loads(row["fact_ids"], []),
            confidence_score=float(row["confidence_score"] or 0.0),
            limitations=row["limitations"] or "",
            status=_safe_enum(ClaimStatus, row["status"], ClaimStatus.DRAFT),
            created_by=row["created_by"] or "system",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_evidence(row) -> EvidenceRef:
        return EvidenceRef(
            id=row["id"],
            owner_type=_safe_enum(
                EvidenceOwnerType,
                row["owner_type"],
                EvidenceOwnerType.INSIGHT_CLAIM,
            ),
            owner_id=row["owner_id"],
            source_document_id=str(row["source_document_id"])
            if row["source_document_id"]
            else None,
            parent_chunk_id=row["parent_chunk_id"],
            url=row["url"] or "",
            title=row["title"] or "",
            snippet=row["snippet"] or "",
            quote_hash=row["quote_hash"] or "",
            evidence_type=_safe_enum(
                EvidenceType, row["evidence_type"], EvidenceType.SOURCE_CHUNK
            ),
            relevance_score=float(row["relevance_score"] or 0.0),
            created_at=row["created_at"],
        )
