from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import delivery.api.insight_router as insight_router


def _build_app():
    app = FastAPI()
    app.include_router(insight_router.router)
    return app


class FakeInsightService:
    def __init__(self):
        self.calls = []
        self.created = []

    def list_claims(self, filters, limit=50, offset=0):
        self.calls.append(("list_claims", filters, limit, offset))
        return [
            {
                "id": "c1",
                "claim_text": "Cursor is shipping faster.",
                "claim_type": "finding",
                "dimension": "product",
                "competitor_ids": [1],
                "fact_ids": ["f1"],
                "created_at": datetime(2026, 1, 2, 3, 4, 5),
                "evidence_refs": [],
            }
        ]

    def get_claim_detail(self, claim_id):
        self.calls.append(("get_claim_detail", claim_id))
        if claim_id == "missing":
            return None
        return {
            "id": claim_id,
            "claim_text": "Cursor is shipping faster.",
            "fact_ids": ["f1"],
            "evidence_refs": [{"id": "e1", "url": "https://example.com"}],
        }

    def create_claim(self, data, created_by="user"):
        self.calls.append(("create_claim", data, created_by))
        if data.get("fact_ids") == ["missing-fact"]:
            raise ValueError("IntelFact not found: missing-fact")
        self.created.append(data)
        return SimpleNamespace(id="c-new")

    def update_claim(self, claim_id, data, updated_by="user"):
        self.calls.append(("update_claim", claim_id, data, updated_by))
        if claim_id == "missing":
            return None
        return SimpleNamespace(id=claim_id)

    def validate_claim_evidence(self, claim_id):
        self.calls.append(("validate_claim_evidence", claim_id))
        if claim_id == "missing":
            return {"valid": False, "errors": [f"InsightClaim not found: {claim_id}"]}
        if claim_id == "invalid":
            return {"valid": False, "errors": ["claim requires evidence"]}
        return {"valid": True, "errors": []}


def test_list_claims_passes_filters(monkeypatch):
    service = FakeInsightService()
    monkeypatch.setattr(insight_router, "_get_service", lambda: service)

    client = TestClient(_build_app())
    resp = client.get(
        "/api/insights/claims",
        params=[
            ("claim_type", "finding"),
            ("dimension", "product"),
            ("status", "draft"),
            ("competitor_ids", "1"),
            ("competitor_ids", "2"),
            ("fact_ids", "f1"),
            ("fact_ids", "f2"),
            ("limit", "10"),
            ("offset", "3"),
        ],
    )

    assert resp.status_code == 200
    assert resp.json()["claims"][0]["created_at"] == "2026-01-02T03:04:05"
    assert service.calls[0] == (
        "list_claims",
        {
            "claim_type": "finding",
            "dimension": "product",
            "status": "draft",
            "competitor_ids": [1, 2],
            "fact_ids": ["f1", "f2"],
        },
        10,
        3,
    )


def test_get_claim_detail_and_404(monkeypatch):
    service = FakeInsightService()
    monkeypatch.setattr(insight_router, "_get_service", lambda: service)

    client = TestClient(_build_app())
    ok = client.get("/api/insights/claims/c1")
    missing = client.get("/api/insights/claims/missing")

    assert ok.status_code == 200
    assert ok.json()["evidence_refs"][0]["id"] == "e1"
    assert missing.status_code == 404


def test_create_claim_forces_draft_and_validates_fact_ids(monkeypatch):
    service = FakeInsightService()
    monkeypatch.setattr(insight_router, "_get_service", lambda: service)

    client = TestClient(_build_app())
    ok = client.post(
        "/api/insights/claims",
        json={
            "claim_text": "Cursor is shipping faster.",
            "claim_type": "finding",
            "dimension": "product",
            "competitor_ids": [1],
            "fact_ids": ["f1"],
            "status": "draft",
        },
    )
    bad_fact = client.post(
        "/api/insights/claims",
        json={"claim_text": "Bad claim", "fact_ids": ["missing-fact"]},
    )

    assert ok.status_code == 200
    assert service.created[0]["status"] == "draft"
    assert service.calls[0][2] == "api"
    assert bad_fact.status_code == 400
    assert "IntelFact not found" in bad_fact.json()["detail"]


def test_create_claim_rejects_active_status(monkeypatch):
    service = FakeInsightService()
    monkeypatch.setattr(insight_router, "_get_service", lambda: service)

    client = TestClient(_build_app())
    resp = client.post(
        "/api/insights/claims",
        json={"claim_text": "Cursor is shipping faster.", "status": "active"},
    )

    assert resp.status_code == 400
    assert service.calls == []


def test_update_claim_and_validate(monkeypatch):
    service = FakeInsightService()
    monkeypatch.setattr(insight_router, "_get_service", lambda: service)
    client = TestClient(_build_app())

    ok = client.put("/api/insights/claims/c1", json={"claim_text": "Updated claim"})
    active = client.put("/api/insights/claims/c1", json={"status": "active"})
    missing = client.put("/api/insights/claims/missing", json={"claim_text": "Missing"})
    valid = client.post("/api/insights/claims/c1/validate")
    invalid = client.post("/api/insights/claims/invalid/validate")
    validate_missing = client.post("/api/insights/claims/missing/validate")

    assert ok.status_code == 200
    assert active.status_code == 400
    assert missing.status_code == 404
    assert valid.status_code == 200
    assert invalid.status_code == 400
    assert validate_missing.status_code == 404
    assert ("update_claim", "c1", {"claim_text": "Updated claim"}, "api") in service.calls
