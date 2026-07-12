from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import delivery.api.intel_router as intel_router


def _build_app():
    app = FastAPI()
    app.include_router(intel_router.router)
    return app


class FakeIntelService:
    def __init__(self):
        self.calls = []
        self.created = []

    def list_facts(self, filters, limit=50, offset=0):
        self.calls.append(("list_facts", filters, limit, offset))
        return [
            {
                "id": "f1",
                "fact_type": "feature_release",
                "dimension": "product",
                "fact_text": "Cursor released Composer.",
                "observed_at": datetime(2026, 1, 2, 3, 4, 5),
                "competitor_ids": [1],
                "product_ids": [],
                "evidence_refs": [],
            }
        ]

    def get_fact_detail(self, fact_id):
        self.calls.append(("get_fact_detail", fact_id))
        if fact_id == "missing":
            return None
        return {
            "id": fact_id,
            "fact_text": "Cursor released Composer.",
            "competitor_ids": [1],
            "product_ids": [],
            "evidence_refs": [{"id": "e1", "url": "https://example.com"}],
        }

    def create_fact(self, data, created_by="user"):
        self.calls.append(("create_fact", data, created_by))
        self.created.append(data)
        return SimpleNamespace(id="f-new")

    def update_fact(self, fact_id, data, updated_by="user"):
        self.calls.append(("update_fact", fact_id, data, updated_by))
        if fact_id == "missing":
            return None
        return SimpleNamespace(id=fact_id)

    def link_fact_to_competitor(self, fact_id, competitor_id, relation_type, confidence_score):
        self.calls.append(
            ("link_fact_to_competitor", fact_id, competitor_id, relation_type, confidence_score)
        )

    def link_fact_to_product(self, fact_id, product_id, relation_type, confidence_score):
        self.calls.append(
            ("link_fact_to_product", fact_id, product_id, relation_type, confidence_score)
        )

    def attach_evidence(self, owner_type, owner_id, data):
        self.calls.append(("attach_evidence", owner_type, owner_id, data))
        return {"id": "e-new", **data}


def test_list_facts_passes_filters(monkeypatch):
    service = FakeIntelService()
    monkeypatch.setattr(intel_router, "_get_service", lambda: service)

    client = TestClient(_build_app())
    resp = client.get(
        "/api/intel/facts",
        params=[
            ("fact_type", "feature_release"),
            ("dimension", "product"),
            ("status", "draft"),
            ("competitor_ids", "1"),
            ("competitor_ids", "2"),
            ("product_id", "9"),
            ("date_from", "2026-01-01"),
            ("date_to", "2026-01-31"),
            ("keyword", "Composer"),
            ("limit", "10"),
            ("offset", "5"),
        ],
    )

    assert resp.status_code == 200
    assert resp.json()["facts"][0]["observed_at"] == "2026-01-02T03:04:05"
    assert service.calls[0] == (
        "list_facts",
        {
            "fact_type": "feature_release",
            "dimension": "product",
            "status": "draft",
            "competitor_ids": [1, 2],
            "product_id": 9,
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "keyword": "Composer",
        },
        10,
        5,
    )


def test_get_fact_detail_and_404(monkeypatch):
    service = FakeIntelService()
    monkeypatch.setattr(intel_router, "_get_service", lambda: service)

    client = TestClient(_build_app())
    ok = client.get("/api/intel/facts/f1")
    missing = client.get("/api/intel/facts/missing")

    assert ok.status_code == 200
    assert ok.json()["evidence_refs"][0]["id"] == "e1"
    assert missing.status_code == 404


def test_create_fact_forces_draft(monkeypatch):
    service = FakeIntelService()
    monkeypatch.setattr(intel_router, "_get_service", lambda: service)

    client = TestClient(_build_app())
    resp = client.post(
        "/api/intel/facts",
        json={
            "subject": "Cursor",
            "predicate": "released",
            "object": "Composer",
            "fact_text": "Cursor released Composer.",
            "competitor_ids": [1],
            "evidence": [{"url": "https://example.com", "evidence_type": "url"}],
        },
    )

    assert resp.status_code == 200
    assert service.created[0]["status"] == "draft"
    assert service.calls[0][2] == "api"


def test_create_fact_rejects_active_status(monkeypatch):
    service = FakeIntelService()
    monkeypatch.setattr(intel_router, "_get_service", lambda: service)

    client = TestClient(_build_app())
    resp = client.post(
        "/api/intel/facts",
        json={
            "subject": "Cursor",
            "predicate": "released",
            "fact_text": "Cursor released Composer.",
            "status": "active",
        },
    )

    assert resp.status_code == 400
    assert service.calls == []


def test_update_fact_and_status_reject_active(monkeypatch):
    service = FakeIntelService()
    monkeypatch.setattr(intel_router, "_get_service", lambda: service)
    client = TestClient(_build_app())

    ok = client.put("/api/intel/facts/f1", json={"fact_text": "Updated fact"})
    active = client.put("/api/intel/facts/f1", json={"status": "active"})
    status_ok = client.patch("/api/intel/facts/f1/status", json={"status": "archived"})
    status_active = client.patch("/api/intel/facts/f1/status", json={"status": "active"})
    missing = client.put("/api/intel/facts/missing", json={"fact_text": "Missing"})

    assert ok.status_code == 200
    assert active.status_code == 400
    assert status_ok.status_code == 200
    assert status_active.status_code == 400
    assert missing.status_code == 404
    assert ("update_fact", "f1", {"fact_text": "Updated fact"}, "api") in service.calls
    assert ("update_fact", "f1", {"status": "archived"}, "api") in service.calls


def test_fact_links_and_evidence_endpoints(monkeypatch):
    service = FakeIntelService()
    monkeypatch.setattr(intel_router, "_get_service", lambda: service)
    client = TestClient(_build_app())

    competitor = client.post(
        "/api/intel/facts/f1/competitors",
        json={"competitor_id": 1, "relation_type": "subject", "confidence_score": 0.8},
    )
    product = client.post(
        "/api/intel/facts/f1/products",
        json={"product_id": 10, "relation_type": "object", "confidence_score": 0.7},
    )
    evidence_list = client.get("/api/intel/facts/f1/evidence")
    evidence_post = client.post(
        "/api/intel/facts/f1/evidence",
        json={"url": "https://example.com", "title": "Source"},
    )

    assert competitor.status_code == 200
    assert product.status_code == 200
    assert evidence_list.status_code == 200
    assert evidence_list.json()["total"] == 1
    assert evidence_post.status_code == 200
    assert evidence_post.json()["id"] == "e-new"
    assert service.calls[-1][0] == "attach_evidence"
