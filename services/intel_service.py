"""Structured intel fact service."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any

import structlog

from core.protocols import (
    CompetitorStoreProtocol,
    DocumentStoreProtocol,
    IntelStoreProtocol,
    RedisStateStoreProtocol,
    StructuredExtractionClientProtocol,
)
from models.document import ParentDocumentChunk, SourceDocument
from models.evidence import EvidenceOwnerType, EvidenceRef, EvidenceType
from models.intel import FactKind, FactStatus, FactType, IntelDimension, IntelFact

logger = structlog.get_logger(__name__)


FACT_EXTRACTION_SYSTEM_PROMPT = """You extract auditable competitor intelligence facts.
Return JSON object {"facts":[...]} only. Each fact must include fact_type, dimension,
subject, predicate, object, fact_text, confidence_score, importance_score,
source_reliability, and parent_chunk_ids. Use only provided parent chunks as evidence."""


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def _safe_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _safe_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


class IntelService:
    """Business rules for fact extraction, persistence, links, and evidence."""

    def __init__(
        self,
        intel_store: IntelStoreProtocol,
        document_store: DocumentStoreProtocol,
        competitor_store: CompetitorStoreProtocol,
        structured_extraction_client: StructuredExtractionClientProtocol | None,
        redis_state_store: RedisStateStoreProtocol | None = None,
    ):
        self.intel_store = intel_store
        self.document_store = document_store
        self.competitor_store = competitor_store
        self.structured_extraction_client = structured_extraction_client
        self.redis_state_store = redis_state_store

    def extract_facts_from_document(
        self,
        document_id: str,
        *,
        extraction_version: str = "intel_fact_v1",
        force: bool = False,
    ) -> dict:
        document = self.document_store.get_document(document_id)
        if not document:
            raise ValueError(f"SourceDocument not found: {document_id}")

        parent_chunks = self.document_store.list_parent_chunks(document_id)
        if not parent_chunks:
            return {
                "document_id": document_id,
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "reason": "no_parent_chunks",
            }

        payload = None
        cache_key = f"logos:intel_extract:{document_id}:{extraction_version}"
        if not force:
            payload = self._cache_get(cache_key)

        if payload is None:
            if self.structured_extraction_client is None:
                raise RuntimeError("structured extraction client is not configured")
            payload = self.structured_extraction_client.extract_json(
                FACT_EXTRACTION_SYSTEM_PROMPT,
                self._build_extraction_message(document, parent_chunks),
                schema_name="intel_fact_extraction",
                temperature=0.0,
            )
            self._cache_set(cache_key, payload)

        facts_payload = payload.get("facts", [])
        if not isinstance(facts_payload, list):
            raise ValueError("intel_fact_extraction.facts must be a list")

        parent_map = {chunk.parent_chunk_id: chunk for chunk in parent_chunks}
        created = updated = skipped = 0
        fact_ids: list[str] = []
        for item in facts_payload:
            if not isinstance(item, dict):
                skipped += 1
                continue
            parent_ids = self._valid_parent_ids(item, parent_map)
            if not parent_ids:
                skipped += 1
                continue
            data = self._fact_data_from_extraction(
                item,
                document=document,
                parent_ids=parent_ids,
                parent_map=parent_map,
                extraction_version=extraction_version,
            )
            existing = self.intel_store.list_facts(
                {
                    "source_document_id": document_id,
                    "dedupe_key": data["dedupe_key"],
                },
                limit=1,
            )
            if existing:
                fact = self.update_fact(existing[0].id, data, updated_by="system")
                updated += 1
            else:
                fact = self.create_fact(data, created_by="system")
                created += 1
            if fact:
                fact_ids.append(fact.id)

        return {
            "document_id": document_id,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "fact_ids": fact_ids,
        }

    def create_fact(self, data: dict, *, created_by: str = "user") -> IntelFact:
        evidence_data = list(data.get("evidence") or data.get("evidence_refs") or [])
        competitor_ids = [int(v) for v in data.get("competitor_ids", []) if v is not None]
        product_ids = [int(v) for v in data.get("product_ids", []) if v is not None]
        requested_status = _enum_value(data.get("status", FactStatus.DRAFT))
        status = FactStatus.DRAFT.value if requested_status == FactStatus.ACTIVE.value else requested_status

        if requested_status == FactStatus.ACTIVE.value and not evidence_data:
            raise ValueError("active IntelFact requires at least one evidence reference")
        self._validate_competitors(competitor_ids)

        fact = IntelFact(
            id=data.get("id") or data.get("fact_id") or IntelFact.__dataclass_fields__["id"].default_factory(),
            source_document_id=data["source_document_id"],
            fact_kind=data.get("fact_kind", FactKind.FACT),
            fact_type=data.get("fact_type", FactType.GENERAL),
            dimension=data.get("dimension", IntelDimension.GENERAL),
            subject=str(data.get("subject", "")).strip(),
            predicate=str(data.get("predicate", "")).strip(),
            object=str(data.get("object", "")).strip(),
            fact_text=str(data.get("fact_text", "")).strip(),
            attributes=dict(data.get("attributes") or {}),
            event_date=_safe_date(data.get("event_date")),
            observed_at=_safe_datetime(data.get("observed_at")),
            importance_score=_safe_float(data.get("importance_score")),
            confidence_score=_safe_float(data.get("confidence_score")),
            source_reliability=_safe_float(data.get("source_reliability")),
            extraction_method=str(data.get("extraction_method", "llm")),
            extraction_version=str(data.get("extraction_version", "")),
            dedupe_key=data.get("dedupe_key") or self.build_dedupe_key(data),
            status=status,
            created_by=created_by,
        )
        if not fact.subject or not fact.predicate or not fact.fact_text:
            raise ValueError("IntelFact requires subject, predicate, and fact_text")

        saved = self.intel_store.save_fact(fact)
        for competitor_id in competitor_ids:
            self.link_fact_to_competitor(saved.id, competitor_id)
        for product_id in product_ids:
            self.link_fact_to_product(saved.id, product_id)
        existing_evidence = self._existing_evidence_keys(saved.id)
        for evidence in evidence_data:
            evidence_key = (
                evidence.get("source_document_id"),
                evidence.get("parent_chunk_id"),
                evidence.get("url", ""),
            )
            if evidence_key in existing_evidence:
                continue
            self.attach_evidence(EvidenceOwnerType.INTEL_FACT.value, saved.id, evidence)
            existing_evidence.add(evidence_key)

        if requested_status == FactStatus.ACTIVE.value:
            self._validate_fact_can_be_active(saved.id, competitor_ids)
            saved = self.intel_store.update_fact_status(saved.id, FactStatus.ACTIVE.value)
        return saved

    def update_fact(
        self,
        fact_id: str,
        data: dict,
        *,
        updated_by: str = "user",
    ) -> IntelFact | None:
        current = self.intel_store.get_fact(fact_id)
        if not current:
            return None
        merged = {
            "id": current.id,
            "source_document_id": data.get("source_document_id", current.source_document_id),
            "fact_kind": data.get("fact_kind", current.fact_kind),
            "fact_type": data.get("fact_type", current.fact_type),
            "dimension": data.get("dimension", current.dimension),
            "subject": data.get("subject", current.subject),
            "predicate": data.get("predicate", current.predicate),
            "object": data.get("object", current.object),
            "fact_text": data.get("fact_text", current.fact_text),
            "attributes": data.get("attributes", current.attributes),
            "event_date": data.get("event_date", current.event_date),
            "observed_at": data.get("observed_at", current.observed_at),
            "importance_score": data.get("importance_score", current.importance_score),
            "confidence_score": data.get("confidence_score", current.confidence_score),
            "source_reliability": data.get("source_reliability", current.source_reliability),
            "extraction_method": data.get("extraction_method", current.extraction_method),
            "extraction_version": data.get("extraction_version", current.extraction_version),
            "dedupe_key": data.get("dedupe_key", current.dedupe_key),
            "status": data.get("status", current.status),
            "created_by": current.created_by,
        }
        requested_status = _enum_value(merged["status"])
        if requested_status == FactStatus.ACTIVE.value:
            evidence = self.intel_store.list_evidence(EvidenceOwnerType.INTEL_FACT.value, fact_id)
            incoming_evidence = data.get("evidence") or data.get("evidence_refs") or []
            if not evidence and not incoming_evidence:
                raise ValueError("active IntelFact requires at least one evidence reference")
            merged["status"] = FactStatus.DRAFT.value

        saved = self.create_fact(
            {
                **merged,
                "competitor_ids": data.get("competitor_ids", current.competitor_ids),
                "product_ids": data.get("product_ids", current.product_ids),
                "evidence": data.get("evidence") or data.get("evidence_refs") or [],
            },
            created_by=updated_by,
        )
        if requested_status == FactStatus.ACTIVE.value:
            self._validate_fact_can_be_active(saved.id, saved.competitor_ids)
            saved = self.intel_store.update_fact_status(saved.id, FactStatus.ACTIVE.value)
        return saved

    def get_fact_detail(self, fact_id: str) -> dict | None:
        fact = self.intel_store.get_fact(fact_id)
        if not fact:
            return None
        return self._fact_to_dict(fact)

    def list_facts(
        self,
        filters: dict[str, Any],
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        return [
            self._fact_to_dict(fact)
            for fact in self.intel_store.list_facts(filters, limit=limit, offset=offset)
        ]

    def link_fact_to_competitor(
        self,
        fact_id: str,
        competitor_id: int,
        relation_type: str = "subject",
        confidence_score: float = 1.0,
    ) -> None:
        if self.intel_store.get_fact(fact_id) is None:
            raise ValueError(f"IntelFact not found: {fact_id}")
        if self.competitor_store.get_competitor(competitor_id) is None:
            raise ValueError(f"Competitor not found: {competitor_id}")
        self.intel_store.link_fact_to_competitor(
            fact_id, competitor_id, relation_type, _safe_float(confidence_score, 1.0)
        )

    def link_fact_to_product(
        self,
        fact_id: str,
        product_id: int,
        relation_type: str = "subject",
        confidence_score: float = 1.0,
    ) -> None:
        if self.intel_store.get_fact(fact_id) is None:
            raise ValueError(f"IntelFact not found: {fact_id}")
        self.intel_store.link_fact_to_product(
            fact_id, product_id, relation_type, _safe_float(confidence_score, 1.0)
        )

    def attach_evidence(
        self,
        owner_type: str,
        owner_id: str,
        evidence_data: dict,
    ) -> EvidenceRef:
        evidence = EvidenceRef(
            owner_type=owner_type,
            owner_id=owner_id,
            source_document_id=evidence_data.get("source_document_id"),
            parent_chunk_id=evidence_data.get("parent_chunk_id"),
            url=evidence_data.get("url", ""),
            title=evidence_data.get("title", ""),
            snippet=evidence_data.get("snippet", ""),
            quote_hash=evidence_data.get("quote_hash", ""),
            evidence_type=evidence_data.get("evidence_type", EvidenceType.SOURCE_CHUNK),
            relevance_score=_safe_float(evidence_data.get("relevance_score"), 1.0),
        )
        self._validate_evidence(evidence)
        if owner_type != EvidenceOwnerType.INTEL_FACT.value:
            raise ValueError("IntelService only attaches intel_fact evidence")
        return self.intel_store.save_evidence(evidence)

    @staticmethod
    def build_dedupe_key(data: dict) -> str:
        parts = [
            data.get("source_document_id", ""),
            _enum_value(data.get("fact_type", FactType.GENERAL)),
            data.get("subject", ""),
            data.get("predicate", ""),
            data.get("object", ""),
            data.get("event_date", ""),
        ]
        normalized = "|".join(_normalize_text(part) for part in parts)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _build_extraction_message(
        self,
        document: SourceDocument,
        parent_chunks: list[ParentDocumentChunk],
    ) -> str:
        chunks = [
            {
                "parent_chunk_id": chunk.parent_chunk_id,
                "title": chunk.doc_name or document.title,
                "content": chunk.content[:3000],
            }
            for chunk in parent_chunks
        ]
        return json.dumps(
            {
                "document": {
                    "id": document.document_id,
                    "title": document.title,
                    "url": document.url,
                    "published_at": document.published_at.isoformat()
                    if document.published_at
                    else None,
                },
                "parent_chunks": chunks,
            },
            ensure_ascii=False,
        )

    def _fact_data_from_extraction(
        self,
        item: dict,
        *,
        document: SourceDocument,
        parent_ids: list[str],
        parent_map: dict[str, ParentDocumentChunk],
        extraction_version: str,
    ) -> dict:
        event_date = item.get("event_date")
        fact_data = {
            "source_document_id": document.document_id,
            "fact_kind": item.get("fact_kind", FactKind.FACT.value),
            "fact_type": item.get("fact_type", FactType.GENERAL.value),
            "dimension": item.get("dimension", IntelDimension.GENERAL.value),
            "subject": item.get("subject", ""),
            "predicate": item.get("predicate", ""),
            "object": item.get("object", ""),
            "fact_text": item.get("fact_text") or item.get("text") or "",
            "attributes": item.get("attributes") or {},
            "event_date": event_date,
            "observed_at": item.get("observed_at"),
            "importance_score": item.get("importance_score", 0.0),
            "confidence_score": item.get("confidence_score", 0.0),
            "source_reliability": item.get("source_reliability", 0.0),
            "extraction_method": "llm",
            "extraction_version": extraction_version,
            "status": FactStatus.DRAFT.value,
            "competitor_ids": item.get("competitor_ids") or [],
            "product_ids": item.get("product_ids") or [],
        }
        fact_data["dedupe_key"] = self.build_dedupe_key(fact_data)
        fact_data["evidence"] = [
            {
                "source_document_id": document.document_id,
                "parent_chunk_id": parent_id,
                "url": document.url,
                "title": document.title,
                "snippet": item.get("snippet") or parent_map[parent_id].content[:500],
                "evidence_type": EvidenceType.SOURCE_CHUNK.value,
                "relevance_score": 1.0,
            }
            for parent_id in parent_ids
        ]
        return fact_data

    @staticmethod
    def _valid_parent_ids(
        item: dict,
        parent_map: dict[str, ParentDocumentChunk],
    ) -> list[str]:
        candidates: list[Any] = []
        if item.get("parent_chunk_id"):
            candidates.append(item["parent_chunk_id"])
        if isinstance(item.get("parent_chunk_ids"), list):
            candidates.extend(item["parent_chunk_ids"])
        for evidence in item.get("evidence", []) or item.get("evidence_refs", []) or []:
            if isinstance(evidence, dict) and evidence.get("parent_chunk_id"):
                candidates.append(evidence["parent_chunk_id"])
        result = []
        for candidate in candidates:
            if candidate in parent_map and candidate not in result:
                result.append(candidate)
        return result

    def _fact_to_dict(self, fact: IntelFact) -> dict:
        evidence = self.intel_store.list_evidence(EvidenceOwnerType.INTEL_FACT.value, fact.id)
        return {
            "id": fact.id,
            "source_document_id": fact.source_document_id,
            "fact_kind": _enum_value(fact.fact_kind),
            "fact_type": _enum_value(fact.fact_type),
            "dimension": _enum_value(fact.dimension),
            "subject": fact.subject,
            "predicate": fact.predicate,
            "object": fact.object,
            "fact_text": fact.fact_text,
            "attributes": fact.attributes,
            "event_date": fact.event_date.isoformat() if fact.event_date else None,
            "observed_at": fact.observed_at.isoformat() if fact.observed_at else None,
            "importance_score": fact.importance_score,
            "confidence_score": fact.confidence_score,
            "source_reliability": fact.source_reliability,
            "extraction_method": fact.extraction_method,
            "extraction_version": fact.extraction_version,
            "dedupe_key": fact.dedupe_key,
            "status": _enum_value(fact.status),
            "created_by": fact.created_by,
            "competitor_ids": fact.competitor_ids,
            "product_ids": fact.product_ids,
            "evidence_refs": [self._evidence_to_dict(item) for item in evidence],
        }

    @staticmethod
    def _evidence_to_dict(evidence: EvidenceRef) -> dict:
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
            "created_at": evidence.created_at.isoformat() if evidence.created_at else None,
        }

    def _validate_competitors(self, competitor_ids: list[int]) -> None:
        for competitor_id in competitor_ids:
            if self.competitor_store.get_competitor(competitor_id) is None:
                raise ValueError(f"Competitor not found: {competitor_id}")

    def _validate_fact_can_be_active(
        self,
        fact_id: str,
        competitor_ids: list[int],
    ) -> None:
        evidence = self.intel_store.list_evidence(EvidenceOwnerType.INTEL_FACT.value, fact_id)
        if not evidence:
            raise ValueError("active IntelFact requires at least one evidence reference")
        self._validate_competitors(competitor_ids)

    def _existing_evidence_keys(self, fact_id: str) -> set[tuple[str | None, str | None, str]]:
        return {
            (evidence.source_document_id, evidence.parent_chunk_id, evidence.url)
            for evidence in self.intel_store.list_evidence(
                EvidenceOwnerType.INTEL_FACT.value,
                fact_id,
            )
        }

    def _validate_evidence(self, evidence: EvidenceRef) -> None:
        if evidence.parent_chunk_id:
            chunks = self.document_store.get_parent_chunks_by_ids([evidence.parent_chunk_id])
            if not chunks:
                raise ValueError(f"Parent chunk not found: {evidence.parent_chunk_id}")
            if evidence.source_document_id and chunks[0].document_id != evidence.source_document_id:
                raise ValueError("Evidence parent_chunk_id does not match source_document_id")
        elif not evidence.url:
            raise ValueError("Evidence requires parent_chunk_id or url")

    def _cache_get(self, key: str) -> Any | None:
        if not self.redis_state_store:
            return None
        try:
            return self.redis_state_store.get_json(key)
        except Exception as exc:
            logger.warning("intel_extract.cache_get_failed", key=key, error=str(exc))
            return None

    def _cache_set(self, key: str, payload: dict) -> None:
        if not self.redis_state_store:
            return
        try:
            self.redis_state_store.set_json(key, payload, ttl_seconds=86400)
        except Exception as exc:
            logger.warning("intel_extract.cache_set_failed", key=key, error=str(exc))
