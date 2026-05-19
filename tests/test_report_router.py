from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import delivery.api.report_router as report_router
from delivery.auth import hash_api_key
from models.auth import ActorRole, ApiKeyRecord


def _build_app():
    app = FastAPI()
    app.include_router(report_router.router)
    return app


class FakeReportStore:
    def __init__(self):
        self.report = SimpleNamespace(
            id=1,
            title="Cursor report",
            report_type="overview",
            competitor_ids=[1],
            content="# Cursor report",
            source_refs=[],
            audit_trail=[],
            status="draft",
            review_status="not_reviewed",
            quality_score=None,
            quality_summary="",
            session_id=None,
            created_at=None,
            updated_at=None,
        )
        self.reviews = []

    def list_reports(self, report_type=None, status=None, limit=30, offset=0):
        return [self.report]

    def get_report(self, report_id):
        return self.report if report_id == 1 else None

    def delete_report(self, report_id):
        return None

    def get_audit_trail(self, report_id):
        return []

    def list_quality_reviews(self, report_id):
        return self.reviews


class FakeAuthStore:
    def __init__(self, records=None):
        self.records = records or {}
        self.last_used = []

    def get_api_key_by_hash(self, key_hash):
        return self.records.get(key_hash)

    def update_last_used(self, key_id):
        self.last_used.append(key_id)


class FakeReportService:
    def __init__(self):
        self.calls = []

    def generate_analysis_report(self, competitor_ids, **kwargs):
        self.calls.append((competitor_ids, kwargs))
        return {
            "report_id": 1,
            "status": "waiting_review",
            "review_status": "passed",
            "quality_score": 0.9,
            "quality_summary": "ok",
            "blocking_issues_count": 0,
            "content": "# Generated",
            "issues": [],
        }

    def get_report_detail(self, report_id):
        if report_id != 1:
            return None
        return {
            "id": 1,
            "title": "Cursor report",
            "content": "# Cursor report",
            "claims": [],
            "evidence_refs": [],
            "quality_reviews": [],
            "status": "waiting_review",
            "review_status": "passed",
            "quality_score": 0.9,
        }

    def review_existing_report(self, report_id, **kwargs):
        return {
            "report_id": report_id,
            "status": "waiting_review",
            "review_status": "passed",
            "quality_score": 0.9,
            "quality_summary": "ok",
            "blocking_issues_count": 0,
            "content": "# Cursor report",
            "issues": [],
        }

    def approve_report(self, report_id, **kwargs):
        return {"id": report_id, "status": "approved", "review_status": "passed"}

    def reject_report(self, report_id, **kwargs):
        return {"id": report_id, "status": "revision_required", "review_status": "passed"}

    def publish_report(self, report_id, **kwargs):
        return {"id": report_id, "status": "published", "review_status": "passed"}


def _auth_record(key, role, key_id=None):
    return ApiKeyRecord(
        id=key_id or f"{role.value}-key",
        name=f"{role.value}-actor",
        key_hash=hash_api_key(key),
        role=role,
    )


def _production_client(monkeypatch, report_service=None, auth_records=None):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    report_service = report_service or FakeReportService()
    mgr = SimpleNamespace(
        report_service=report_service,
        report_store=FakeReportStore(),
        auth_store=FakeAuthStore(auth_records),
        config=SimpleNamespace(app_env="production", auth_enabled=True),
    )
    monkeypatch.setattr(report_router, "get_config_manager", lambda: mgr)

    import core.config_manager as config_manager

    monkeypatch.setattr(config_manager, "get_config_manager", lambda: mgr)
    return TestClient(_build_app()), report_service


def test_report_generate_uses_report_service(monkeypatch):
    report_service = FakeReportService()
    mgr = SimpleNamespace(report_service=report_service, report_store=FakeReportStore())
    monkeypatch.setattr(report_router, "get_config_manager", lambda: mgr)
    client = TestClient(_build_app())

    resp = client.post(
        "/api/reports/generate",
        json={
            "competitor_ids": [1, 2],
            "report_type": "comparison",
            "focus": "pricing",
            "dimensions": ["product"],
        },
    )

    assert resp.status_code == 200
    assert resp.json()["content"] == "# Generated"
    assert resp.json()["status"] == "waiting_review"
    assert resp.json()["blocking_issues_count"] == 0
    assert report_service.calls[0][0] == [1, 2]
    assert report_service.calls[0][1]["report_type"] == "comparison"


def test_report_generate_requires_competitor_ids(monkeypatch):
    mgr = SimpleNamespace(report_service=FakeReportService(), report_store=FakeReportStore())
    monkeypatch.setattr(report_router, "get_config_manager", lambda: mgr)
    client = TestClient(_build_app())

    resp = client.post("/api/reports/generate", json={"competitor_ids": []})

    assert resp.status_code == 400


def test_report_detail_includes_quality_payload(monkeypatch):
    mgr = SimpleNamespace(report_service=FakeReportService(), report_store=FakeReportStore())
    monkeypatch.setattr(report_router, "get_config_manager", lambda: mgr)
    client = TestClient(_build_app())

    resp = client.get("/api/reports/1")

    assert resp.status_code == 200
    assert resp.json()["claims"] == []
    assert resp.json()["evidence_refs"] == []
    assert resp.json()["review_status"] == "passed"


def test_report_quality_review_endpoint(monkeypatch):
    mgr = SimpleNamespace(report_service=FakeReportService(), report_store=FakeReportStore())
    monkeypatch.setattr(report_router, "get_config_manager", lambda: mgr)
    client = TestClient(_build_app())

    resp = client.post("/api/reports/1/quality/review")

    assert resp.status_code == 200
    assert resp.json()["report_id"] == 1
    assert resp.json()["review_status"] == "passed"


def test_report_approval_endpoints_use_report_service(monkeypatch):
    service = FakeReportService()
    mgr = SimpleNamespace(report_service=service, report_store=FakeReportStore())
    monkeypatch.setattr(report_router, "get_config_manager", lambda: mgr)
    client = TestClient(_build_app())

    assert client.post("/api/reports/1/approve").json()["status"] == "approved"
    assert client.post("/api/reports/1/reject", json={"reason": "fix"}).json()["status"] == "revision_required"
    assert client.post("/api/reports/1/publish").json()["status"] == "published"


def test_report_generate_requires_api_key_in_production(monkeypatch):
    client, _service = _production_client(monkeypatch)

    resp = client.post("/api/reports/generate", json={"competitor_ids": [1]})

    assert resp.status_code == 401


def test_viewer_cannot_generate_or_publish_report(monkeypatch):
    viewer_key = "if_viewer_report"
    records = {hash_api_key(viewer_key): _auth_record(viewer_key, ActorRole.VIEWER)}
    client, _service = _production_client(monkeypatch, auth_records=records)
    headers = {"Authorization": f"Bearer {viewer_key}"}

    assert client.post("/api/reports/generate", json={"competitor_ids": [1]}, headers=headers).status_code == 403
    assert client.post("/api/reports/1/publish", headers=headers).status_code == 403


def test_analyst_can_generate_but_cannot_publish_report(monkeypatch):
    analyst_key = "if_analyst_report"
    service = FakeReportService()
    records = {hash_api_key(analyst_key): _auth_record(analyst_key, ActorRole.ANALYST)}
    client, _service = _production_client(monkeypatch, report_service=service, auth_records=records)
    headers = {"Authorization": f"Bearer {analyst_key}"}

    generate_resp = client.post("/api/reports/generate", json={"competitor_ids": [1]}, headers=headers)
    publish_resp = client.post("/api/reports/1/publish", headers=headers)

    assert generate_resp.status_code == 200
    assert generate_resp.json()["status"] == "waiting_review"
    assert publish_resp.status_code == 403
    assert service.calls[0][1]["actor"] == "analyst-actor"


def test_admin_can_approve_and_publish_report(monkeypatch):
    admin_key = "if_admin_report"
    records = {hash_api_key(admin_key): _auth_record(admin_key, ActorRole.ADMIN)}
    client, _service = _production_client(monkeypatch, auth_records=records)
    headers = {"X-API-Key": admin_key}

    assert client.post("/api/reports/1/approve", headers=headers).json()["status"] == "approved"
    assert client.post("/api/reports/1/publish", headers=headers).json()["status"] == "published"
