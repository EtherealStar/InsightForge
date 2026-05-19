from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

import delivery.api.competitor_router as competitor_router
from models.competitor import Competitor, CompetitorProduct
from models.intel import FactKind, IntelFact


def _build_app():
    app = FastAPI()
    app.include_router(competitor_router.router)
    return app


class ForbiddenLegacyStore:
    def __getattr__(self, name):
        raise AssertionError(f"Legacy store should not be used by Phase 2 competitor API: {name}")


class FakeCompetitorService:
    def __init__(self):
        self.legacy_store = ForbiddenLegacyStore()
        self.competitor = Competitor(id=1, name="Cursor", aliases=["Anysphere"])
        self.products = [CompetitorProduct(id=10, competitor_id=1, name="Composer")]
        self.fact = IntelFact(
            id="f1",
            source_document_id="doc1",
            fact_kind=FactKind.FACT,
            fact_type="feature_release",
            dimension="product",
            subject="Cursor",
            predicate="released",
            object="Composer",
            fact_text="Cursor released Composer.",
            event_date=date(2026, 1, 2),
            competitor_ids=[1],
            product_ids=[10],
            evidence_refs=["e1"],
        )
        self.signal = IntelFact(
            id="f2",
            source_document_id="doc1",
            fact_kind=FactKind.FACT,
            subject="Cursor",
            predicate="mentioned",
            fact_text="Cursor was mentioned.",
            competitor_ids=[1],
        )
        self.calls = []

    def get_competitor(self, competitor_id):
        self.calls.append(("get_competitor", competitor_id))
        if competitor_id != 1:
            return None
        return {
            "competitor": self.competitor,
            "products": self.products,
            "fact_count": 1,
            "intel_count": 99,
        }

    def get_competitor_fact_profile(self, competitor_id, filters=None):
        self.calls.append(("get_competitor_fact_profile", competitor_id, filters))
        if competitor_id != 1:
            return None
        return {
            "competitor": self.competitor,
            "products": self.products,
            "facts": [self.fact],
            "aggregates": {
                "by_dimension": {"product": 1},
                "by_type": {"feature_release": 1},
                "total": 1,
            },
        }

    def get_competitor_timeline(self, competitor_id, filters=None):
        self.calls.append(("get_competitor_timeline", competitor_id, filters))
        if competitor_id != 1:
            return None
        event_fact = IntelFact(
            id="f3",
            source_document_id="doc1",
            fact_kind=FactKind.EVENT,
            subject="Cursor",
            predicate="launched",
            fact_text="Cursor launched a program.",
            competitor_ids=[1],
        )
        return {
            "competitor": self.competitor,
            "products": self.products,
            "timeline": [self.fact, event_fact],
        }

    def compare_competitor_facts(self, competitor_ids, dimensions=None, time_window=None):
        self.calls.append(
            ("compare_competitor_facts", competitor_ids, dimensions, time_window)
        )
        return {
            "competitors": competitor_ids,
            "dimensions": dimensions or [],
            "time_window": time_window or {},
            "items": [],
        }


def test_get_competitor_returns_fact_count_not_legacy_intel_count(monkeypatch):
    service = FakeCompetitorService()
    monkeypatch.setattr(competitor_router, "_get_service", lambda: service)

    client = TestClient(_build_app())
    resp = client.get("/api/competitors/1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["fact_count"] == 1
    assert "intel_count" not in body


def test_get_competitor_facts_returns_aggregates_and_filters(monkeypatch):
    service = FakeCompetitorService()
    monkeypatch.setattr(competitor_router, "_get_service", lambda: service)

    client = TestClient(_build_app())
    resp = client.get(
        "/api/competitors/1/facts",
        params={
            "fact_type": "feature_release",
            "dimension": "product",
            "status": "draft",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "keyword": "Composer",
            "limit": "10",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["aggregates"]["by_dimension"] == {"product": 1}
    assert body["facts"][0]["event_date"] == "2026-01-02"
    assert service.calls[0] == (
        "get_competitor_fact_profile",
        1,
        {
            "limit": 10,
            "fact_type": "feature_release",
            "dimension": "product",
            "status": "draft",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "keyword": "Composer",
        },
    )


def test_get_competitor_timeline_uses_fact_timeline(monkeypatch):
    service = FakeCompetitorService()
    monkeypatch.setattr(competitor_router, "_get_service", lambda: service)

    client = TestClient(_build_app())
    resp = client.get("/api/competitors/1/timeline")

    assert resp.status_code == 200
    body = resp.json()
    assert [item["id"] for item in body["timeline"]] == ["f1", "f3"]
    assert service.calls[0][0] == "get_competitor_timeline"


def test_compare_competitor_facts_and_legacy_intel_route_missing(monkeypatch):
    service = FakeCompetitorService()
    monkeypatch.setattr(competitor_router, "_get_service", lambda: service)
    client = TestClient(_build_app())

    compare = client.post(
        "/api/competitors/compare/facts",
        json={
            "competitor_ids": [1, 2],
            "dimensions": ["product"],
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        },
    )
    legacy = client.get("/api/competitors/1/intel")

    assert compare.status_code == 200
    assert compare.json()["competitors"] == [1, 2]
    assert service.calls[-1] == (
        "compare_competitor_facts",
        [1, 2],
        ["product"],
        {"date_from": "2026-01-01", "date_to": "2026-01-31"},
    )
    assert legacy.status_code == 404
