"""PostgreSQL IntelStore implementation."""
from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

import psycopg2
from psycopg2.extras import DictCursor
import structlog

from core.exceptions import StoreError
from models.evidence import EvidenceRef, EvidenceOwnerType, EvidenceType
from models.intel import (
    FactKind,
    FactStatus,
    FactType,
    IntelDimension,
    IntelFact,
)

logger = structlog.get_logger(__name__)


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


class PostgresIntelStore:
    """Structured facts, fact links, and evidence refs stored in PostgreSQL."""

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=DictCursor)
        conn.autocommit = True
        return conn

    def save_fact(self, fact: IntelFact) -> IntelFact:
        now = datetime.now()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intel_facts (
                        id, source_document_id, fact_kind, fact_type, dimension,
                        subject, predicate, object, fact_text, attributes,
                        event_date, observed_at, importance_score, confidence_score,
                        source_reliability, extraction_method, extraction_version,
                        dedupe_key, status, created_by, created_at, updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        source_document_id = EXCLUDED.source_document_id,
                        fact_kind = EXCLUDED.fact_kind,
                        fact_type = EXCLUDED.fact_type,
                        dimension = EXCLUDED.dimension,
                        subject = EXCLUDED.subject,
                        predicate = EXCLUDED.predicate,
                        object = EXCLUDED.object,
                        fact_text = EXCLUDED.fact_text,
                        attributes = EXCLUDED.attributes,
                        event_date = EXCLUDED.event_date,
                        observed_at = EXCLUDED.observed_at,
                        importance_score = EXCLUDED.importance_score,
                        confidence_score = EXCLUDED.confidence_score,
                        source_reliability = EXCLUDED.source_reliability,
                        extraction_method = EXCLUDED.extraction_method,
                        extraction_version = EXCLUDED.extraction_version,
                        dedupe_key = EXCLUDED.dedupe_key,
                        status = EXCLUDED.status,
                        created_by = EXCLUDED.created_by,
                        updated_at = NOW()
                    RETURNING *
                    """,
                    (
                        fact.id,
                        fact.source_document_id,
                        _enum_value(fact.fact_kind),
                        _enum_value(fact.fact_type),
                        _enum_value(fact.dimension),
                        fact.subject,
                        fact.predicate,
                        fact.object,
                        fact.fact_text,
                        _json_dumps(fact.attributes, {}),
                        fact.event_date,
                        fact.observed_at or now,
                        fact.importance_score,
                        fact.confidence_score,
                        fact.source_reliability,
                        fact.extraction_method,
                        fact.extraction_version,
                        fact.dedupe_key,
                        _enum_value(fact.status),
                        fact.created_by,
                        fact.created_at or now,
                        fact.updated_at or now,
                    ),
                )
                row = cur.fetchone()
        saved = self._row_to_fact(row)
        self._attach_links([saved])
        return saved

    def get_fact(self, fact_id: str) -> IntelFact | None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM intel_facts WHERE id = %s", (fact_id,))
                row = cur.fetchone()
        if not row:
            return None
        fact = self._row_to_fact(row)
        self._attach_links([fact])
        return fact

    def list_facts(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IntelFact]:
        filters = filters or {}
        conditions: list[str] = []
        params: list[Any] = []

        for key in ("fact_type", "dimension", "status", "source_document_id", "dedupe_key"):
            if filters.get(key):
                conditions.append(f"{key} = %s")
                params.append(filters[key])

        competitor_ids = filters.get("competitor_ids")
        if filters.get("competitor_id"):
            competitor_ids = [filters["competitor_id"]]
        if competitor_ids:
            conditions.append(
                """
                EXISTS (
                    SELECT 1 FROM intel_fact_competitors ifc
                    WHERE ifc.fact_id = intel_facts.id
                      AND ifc.competitor_id = ANY(%s)
                )
                """
            )
            params.append(list(competitor_ids))

        product_ids = filters.get("product_ids")
        if filters.get("product_id"):
            product_ids = [filters["product_id"]]
        if product_ids:
            conditions.append(
                """
                EXISTS (
                    SELECT 1 FROM intel_fact_products ifp
                    WHERE ifp.fact_id = intel_facts.id
                      AND ifp.product_id = ANY(%s)
                )
                """
            )
            params.append(list(product_ids))

        date_from = filters.get("event_date_from") or filters.get("date_from")
        date_to = filters.get("event_date_to") or filters.get("date_to")
        if date_from:
            conditions.append("event_date >= %s")
            params.append(date_from)
        if date_to:
            conditions.append("event_date <= %s")
            params.append(date_to)

        keyword = filters.get("keyword")
        if keyword:
            pattern = f"%{keyword}%"
            conditions.append(
                "(fact_text ILIKE %s OR subject ILIKE %s OR object ILIKE %s)"
            )
            params.extend([pattern, pattern, pattern])

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.extend([limit, offset])
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT * FROM intel_facts
                    {where}
                    ORDER BY COALESCE(event_date, observed_at::date) DESC, created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
        facts = [self._row_to_fact(row) for row in rows]
        self._attach_links(facts)
        return facts

    def update_fact_status(self, fact_id: str, status: str) -> IntelFact:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE intel_facts
                    SET status = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (status, fact_id),
                )
                row = cur.fetchone()
        if not row:
            raise StoreError(f"IntelFact not found: {fact_id}")
        fact = self._row_to_fact(row)
        self._attach_links([fact])
        return fact

    def delete_fact(self, fact_id: str) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM evidence_refs WHERE owner_type = %s AND owner_id = %s",
                    (EvidenceOwnerType.INTEL_FACT.value, fact_id),
                )
                cur.execute("DELETE FROM intel_facts WHERE id = %s", (fact_id,))

    def link_fact_to_competitor(
        self,
        fact_id: str,
        competitor_id: int,
        relation_type: str = "subject",
        confidence_score: float = 1.0,
    ) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intel_fact_competitors (
                        fact_id, competitor_id, relation_type, confidence_score
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (fact_id, competitor_id, relation_type)
                    DO UPDATE SET confidence_score = EXCLUDED.confidence_score
                    """,
                    (fact_id, competitor_id, relation_type, confidence_score),
                )

    def unlink_fact_from_competitor(
        self,
        fact_id: str,
        competitor_id: int,
        relation_type: str | None = None,
    ) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                if relation_type:
                    cur.execute(
                        """
                        DELETE FROM intel_fact_competitors
                        WHERE fact_id = %s AND competitor_id = %s AND relation_type = %s
                        """,
                        (fact_id, competitor_id, relation_type),
                    )
                else:
                    cur.execute(
                        """
                        DELETE FROM intel_fact_competitors
                        WHERE fact_id = %s AND competitor_id = %s
                        """,
                        (fact_id, competitor_id),
                    )

    def link_fact_to_product(
        self,
        fact_id: str,
        product_id: int,
        relation_type: str = "subject",
        confidence_score: float = 1.0,
    ) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intel_fact_products (
                        fact_id, product_id, relation_type, confidence_score
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (fact_id, product_id, relation_type)
                    DO UPDATE SET confidence_score = EXCLUDED.confidence_score
                    """,
                    (fact_id, product_id, relation_type, confidence_score),
                )

    def save_evidence(self, evidence: EvidenceRef) -> EvidenceRef:
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

    def list_evidence(self, owner_type: str, owner_id: str) -> list[EvidenceRef]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM evidence_refs
                    WHERE owner_type = %s AND owner_id = %s
                    ORDER BY created_at ASC
                    """,
                    (owner_type, owner_id),
                )
                rows = cur.fetchall()
        return [self._row_to_evidence(row) for row in rows]

    def _attach_links(self, facts: list[IntelFact]) -> None:
        if not facts:
            return
        fact_ids = [fact.id for fact in facts]
        fact_map = {fact.id: fact for fact in facts}
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT fact_id, competitor_id FROM intel_fact_competitors
                    WHERE fact_id = ANY(%s)
                    """,
                    (fact_ids,),
                )
                for row in cur.fetchall():
                    fact_map[row["fact_id"]].competitor_ids.append(row["competitor_id"])
                cur.execute(
                    """
                    SELECT fact_id, product_id FROM intel_fact_products
                    WHERE fact_id = ANY(%s)
                    """,
                    (fact_ids,),
                )
                for row in cur.fetchall():
                    fact_map[row["fact_id"]].product_ids.append(row["product_id"])
                cur.execute(
                    """
                    SELECT owner_id, id FROM evidence_refs
                    WHERE owner_type = %s AND owner_id = ANY(%s)
                    """,
                    (EvidenceOwnerType.INTEL_FACT.value, fact_ids),
                )
                for row in cur.fetchall():
                    fact_map[row["owner_id"]].evidence_refs.append(row["id"])

    @staticmethod
    def _row_to_fact(row) -> IntelFact:
        return IntelFact(
            id=row["id"],
            source_document_id=str(row["source_document_id"]),
            fact_kind=_safe_enum(FactKind, row["fact_kind"], FactKind.FACT),
            fact_type=_safe_enum(FactType, row["fact_type"], FactType.GENERAL),
            dimension=_safe_enum(
                IntelDimension, row["dimension"], IntelDimension.GENERAL
            ),
            subject=row["subject"],
            predicate=row["predicate"],
            object=row["object"] or "",
            fact_text=row["fact_text"],
            attributes=_json_loads(row["attributes"], {}),
            event_date=row["event_date"],
            observed_at=row["observed_at"],
            importance_score=float(row["importance_score"] or 0.0),
            confidence_score=float(row["confidence_score"] or 0.0),
            source_reliability=float(row["source_reliability"] or 0.0),
            extraction_method=row["extraction_method"] or "llm",
            extraction_version=row["extraction_version"] or "",
            dedupe_key=row["dedupe_key"] or "",
            status=_safe_enum(FactStatus, row["status"], FactStatus.DRAFT),
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
                EvidenceOwnerType.INTEL_FACT,
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
