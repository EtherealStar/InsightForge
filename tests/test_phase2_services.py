from datetime import date, datetime

import pytest

from models.competitor import Competitor
from models.document import ParentDocumentChunk, SourceDocument
from models.evidence import EvidenceOwnerType, EvidenceRef
from models.insight import InsightClaim
from models.intel import IntelFact
from services.competitor_service import CompetitorService
from services.insight_service import InsightService
from services.intel_service import IntelService
from services.service_registry import ServiceRegistry


class FakeDocumentStore:
    def __init__(self):
        self.documents = {}
        self.parents = []

    def save_document(self, document):
        self.documents[document.document_id] = document
        return document

    def get_document(self, document_id):
        return self.documents.get(document_id)

    def list_documents(self, filters=None, limit=50, offset=0):
        return list(self.documents.values())[offset : offset + limit]

    def update_parse_status(self, document_id, status, error=None):
        self.documents[document_id].parse_status = status

    def save_parent_chunks(self, parent_chunks):
        self.parents.extend(parent_chunks)
        return len(parent_chunks)

    def list_parent_chunks(self, document_id):
        return [p for p in self.parents if p.document_id == document_id]

    def get_parent_chunks_by_ids(self, parent_chunk_ids):
        wanted = set(parent_chunk_ids)
        return [p for p in self.parents if p.parent_chunk_id in wanted]


class FakeIntelStore:
    def __init__(self):
        self.facts = {}
        self.evidence = {}
        self.competitor_links = {}
        self.product_links = {}

    def save_fact(self, fact):
        self.facts[fact.id] = fact
        self._attach(fact)
        return fact

    def get_fact(self, fact_id):
        fact = self.facts.get(fact_id)
        if fact:
            self._attach(fact)
        return fact

    def list_facts(self, filters=None, limit=50, offset=0):
        filters = filters or {}
        facts = list(self.facts.values())
        for key in ("source_document_id", "dedupe_key", "fact_type", "dimension", "status"):
            if filters.get(key):
                facts = [
                    f
                    for f in facts
                    if getattr(getattr(f, key), "value", getattr(f, key)) == filters[key]
                ]
        if filters.get("competitor_id"):
            facts = [
                f
                for f in facts
                if filters["competitor_id"] in self.competitor_links.get(f.id, [])
            ]
        for fact in facts:
            self._attach(fact)
        return facts[offset : offset + limit]

    def update_fact_status(self, fact_id, status):
        self.facts[fact_id].status = status
        return self.facts[fact_id]

    def delete_fact(self, fact_id):
        self.facts.pop(fact_id, None)

    def link_fact_to_competitor(
        self, fact_id, competitor_id, relation_type="subject", confidence_score=1.0
    ):
        self.competitor_links.setdefault(fact_id, [])
        if competitor_id not in self.competitor_links[fact_id]:
            self.competitor_links[fact_id].append(competitor_id)

    def unlink_fact_from_competitor(self, fact_id, competitor_id, relation_type=None):
        self.competitor_links.get(fact_id, []).remove(competitor_id)

    def link_fact_to_product(
        self, fact_id, product_id, relation_type="subject", confidence_score=1.0
    ):
        self.product_links.setdefault(fact_id, [])
        if product_id not in self.product_links[fact_id]:
            self.product_links[fact_id].append(product_id)

    def save_evidence(self, evidence):
        self.evidence[evidence.id] = evidence
        return evidence

    def list_evidence(self, owner_type, owner_id):
        return [
            evidence
            for evidence in self.evidence.values()
            if evidence.owner_type == owner_type and evidence.owner_id == owner_id
        ]

    def _attach(self, fact):
        fact.competitor_ids = list(self.competitor_links.get(fact.id, []))
        fact.product_ids = list(self.product_links.get(fact.id, []))
        fact.evidence_refs = [
            e.id
            for e in self.evidence.values()
            if e.owner_type == EvidenceOwnerType.INTEL_FACT.value and e.owner_id == fact.id
        ]


class FakeCompetitorStore:
    def __init__(self):
        self.competitors = {1: Competitor(id=1, name="Cursor", aliases=["Anysphere"])}

    def save_competitor(self, competitor):
        competitor.id = competitor.id or max(self.competitors) + 1
        self.competitors[competitor.id] = competitor
        return competitor

    def get_competitor(self, competitor_id):
        return self.competitors.get(competitor_id)

    def list_competitors(self, status="active", limit=100):
        return list(self.competitors.values())[:limit]

    def search_competitors(self, query):
        return [c for c in self.competitors.values() if query.lower() in c.name.lower()]

    def delete_competitor(self, competitor_id):
        self.competitors.pop(competitor_id, None)

    def save_product(self, product):
        return product

    def list_products(self, competitor_id):
        return []

    def delete_product(self, product_id):
        pass


class FakeExtractionClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def extract_json(self, system_prompt, user_message, *, schema_name, temperature=0.0):
        self.calls += 1
        return self.payload


class FakeRedis:
    def __init__(self):
        self.data = {}

    def get_json(self, key):
        return self.data.get(key)

    def set_json(self, key, value, ttl_seconds=None):
        self.data[key] = value
        return True


def _intel_service(payload=None):
    document_store = FakeDocumentStore()
    document = SourceDocument(
        document_id="11111111-1111-1111-1111-111111111111",
        title="Cursor release",
        content="Cursor released Composer.",
        parse_status="vectorized",
    )
    document_store.save_document(document)
    document_store.save_parent_chunks(
        [
            ParentDocumentChunk(
                parent_chunk_id="p-1",
                document_id=document.document_id,
                content="Cursor released Composer.",
                token_count=4,
            )
        ]
    )
    intel_store = FakeIntelStore()
    client = FakeExtractionClient(payload or {"facts": []})
    service = IntelService(
        intel_store,
        document_store,
        FakeCompetitorStore(),
        client,
        FakeRedis(),
    )
    return service, intel_store, document_store, client


def test_intel_service_rejects_active_fact_without_evidence():
    service, _, _, _ = _intel_service()
    with pytest.raises(ValueError, match="requires at least one evidence"):
        service.create_fact(
            {
                "source_document_id": "11111111-1111-1111-1111-111111111111",
                "subject": "Cursor",
                "predicate": "released",
                "object": "Composer",
                "fact_text": "Cursor released Composer.",
                "competitor_ids": [1],
                "status": "active",
            }
        )


def test_extract_facts_uses_structured_client_and_dedupes_with_cache():
    payload = {
        "facts": [
            {
                "fact_type": "feature_release",
                "dimension": "product",
                "subject": "Cursor",
                "predicate": "released",
                "object": "Composer",
                "fact_text": "Cursor released Composer.",
                "parent_chunk_ids": ["p-1"],
                "confidence_score": 0.9,
            }
        ]
    }
    service, intel_store, _, client = _intel_service(payload)

    first = service.extract_facts_from_document("11111111-1111-1111-1111-111111111111")
    second = service.extract_facts_from_document("11111111-1111-1111-1111-111111111111")

    assert first["created"] == 1
    assert second["updated"] == 1
    assert len(intel_store.facts) == 1
    assert client.calls == 1


def test_extract_facts_skips_items_without_valid_parent_evidence():
    payload = {
        "facts": [
            {
                "subject": "Cursor",
                "predicate": "released",
                "object": "Composer",
                "fact_text": "Cursor released Composer.",
                "parent_chunk_ids": ["missing"],
            }
        ]
    }
    service, intel_store, _, _ = _intel_service(payload)

    result = service.extract_facts_from_document("11111111-1111-1111-1111-111111111111")

    assert result["skipped"] == 1
    assert intel_store.facts == {}


class FakeInsightStore:
    def __init__(self):
        self.claims = {}
        self.evidence = {}

    def save_claim(self, claim):
        self.claims[claim.id] = claim
        return claim

    def get_claim(self, claim_id):
        claim = self.claims.get(claim_id)
        if claim:
            claim.evidence_refs = [
                {"id": e.id, "parent_chunk_id": e.parent_chunk_id, "url": e.url}
                for e in self.evidence.values()
                if e.owner_id == claim_id
            ]
        return claim

    def list_claims(self, filters=None, limit=50, offset=0):
        return list(self.claims.values())[offset : offset + limit]

    def update_claim_status(self, claim_id, status):
        self.claims[claim_id].status = status
        return self.claims[claim_id]

    def delete_claim(self, claim_id):
        self.claims.pop(claim_id, None)

    def attach_evidence(self, claim_id, evidence):
        self.evidence[evidence.id] = evidence
        return evidence


def test_insight_service_rejects_active_claim_without_fact_or_evidence():
    document_store = FakeDocumentStore()
    service = InsightService(
        FakeInsightStore(),
        FakeIntelStore(),
        FakeCompetitorStore(),
        document_store,
    )

    with pytest.raises(ValueError, match="requires at least one fact or evidence"):
        service.create_claim({"claim_text": "Cursor is shipping faster.", "status": "active"})


def test_competitor_service_fact_profile_uses_fact_store():
    intel_store = FakeIntelStore()
    fact = intel_store.save_fact(
        IntelFact(
            source_document_id="11111111-1111-1111-1111-111111111111",
            subject="Cursor",
            predicate="released",
            object="Composer",
            fact_text="Cursor released Composer.",
        )
    )
    intel_store.link_fact_to_competitor(fact.id, 1)
    service = CompetitorService(FakeCompetitorStore(), intel_store)

    profile = service.get_competitor_fact_profile(1)

    assert profile["aggregates"]["total"] == 1
    assert profile["facts"][0].fact_text == "Cursor released Composer."


def test_competitor_service_timeline_keeps_events_and_dated_facts():
    intel_store = FakeIntelStore()
    dated_fact = intel_store.save_fact(
        IntelFact(
            source_document_id="11111111-1111-1111-1111-111111111111",
            fact_kind="fact",
            subject="Cursor",
            predicate="released",
            object="Composer",
            fact_text="Cursor released Composer.",
            event_date=date(2026, 1, 3),
        )
    )
    event_fact = intel_store.save_fact(
        IntelFact(
            source_document_id="11111111-1111-1111-1111-111111111111",
            fact_kind="event",
            subject="Cursor",
            predicate="launched",
            object="Program",
            fact_text="Cursor launched a program.",
        )
    )
    plain_fact = intel_store.save_fact(
        IntelFact(
            source_document_id="11111111-1111-1111-1111-111111111111",
            fact_kind="fact",
            subject="Cursor",
            predicate="mentioned",
            fact_text="Cursor was mentioned.",
        )
    )
    for fact in (dated_fact, event_fact, plain_fact):
        intel_store.link_fact_to_competitor(fact.id, 1)
    service = CompetitorService(FakeCompetitorStore(), intel_store)

    timeline = service.get_competitor_timeline(1)

    assert [fact.id for fact in timeline["timeline"]] == [dated_fact.id, event_fact.id]


def test_service_registry_only_exposes_service_whitelist():
    registry = ServiceRegistry({"intel_service": object()})

    assert registry.has("intel_service")
    assert registry.get("llm_client") is None
    with pytest.raises(KeyError):
        registry.require("postgres_store")
    with pytest.raises(ValueError):
        ServiceRegistry({"llm_client": object()})
