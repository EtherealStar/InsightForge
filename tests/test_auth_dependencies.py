from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import delivery.api.config_router as config_router
from delivery.auth import hash_api_key, require_admin, require_analyst
from models.auth import ActorRole, ApiKeyRecord, ApiKeyStatus


class FakeAuthStore:
    def __init__(self, record=None):
        self.record = record
        self.last_used = []

    def get_api_key_by_hash(self, key_hash):
        if self.record and self.record.key_hash == key_hash:
            return self.record
        return None

    def update_last_used(self, key_id):
        self.last_used.append(key_id)


def _client(monkeypatch, store):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_ENABLED", "true")

    import core.config_manager as config_manager

    monkeypatch.setattr(config_manager, "get_config_manager", lambda: SimpleNamespace(
        auth_store=store,
        config=SimpleNamespace(app_env="production", auth_enabled=True),
    ))
    app = FastAPI()

    @app.get("/admin")
    def admin_route(_ctx=Depends(require_admin)):
        return {"ok": True}

    @app.get("/analyst")
    def analyst_route(_ctx=Depends(require_analyst)):
        return {"ok": True}

    return TestClient(app)


def test_missing_api_key_returns_401(monkeypatch):
    client = _client(monkeypatch, FakeAuthStore())

    resp = client.get("/admin")

    assert resp.status_code == 401


def test_viewer_cannot_call_analyst_route(monkeypatch):
    key = "if_viewer"
    store = FakeAuthStore(
        ApiKeyRecord(
            id="k1",
            name="viewer-key",
            key_hash=hash_api_key(key),
            role=ActorRole.VIEWER,
        )
    )
    client = _client(monkeypatch, store)

    resp = client.get("/analyst", headers={"Authorization": f"Bearer {key}"})

    assert resp.status_code == 403


def test_admin_key_is_accepted_and_last_used_updates(monkeypatch):
    key = "if_admin"
    store = FakeAuthStore(
        ApiKeyRecord(
            id="k2",
            name="admin-key",
            key_hash=hash_api_key(key),
            role=ActorRole.ADMIN,
        )
    )
    client = _client(monkeypatch, store)

    resp = client.get("/admin", headers={"X-API-Key": key})

    assert resp.status_code == 200
    assert store.last_used == ["k2"]


def test_revoked_key_returns_401(monkeypatch):
    key = "if_revoked"
    store = FakeAuthStore(
        ApiKeyRecord(
            id="k3",
            name="revoked-key",
            key_hash=hash_api_key(key),
            role=ActorRole.ADMIN,
            status=ApiKeyStatus.REVOKED,
        )
    )
    client = _client(monkeypatch, store)

    resp = client.get("/admin", headers={"Authorization": f"Bearer {key}"})

    assert resp.status_code == 401


class FakeConfigAuditStore:
    def __init__(self):
        self.logs = []

    def append_config_audit(self, log):
        self.logs.append(log)
        return log

    def list_config_audit(self, target=None, limit=50, offset=0):
        items = [log for log in self.logs if target is None or log.target == target]
        return items[offset : offset + limit]


def _config_client(monkeypatch, env):
    key = "if_config_admin"
    auth_store = FakeAuthStore(
        ApiKeyRecord(
            id="config-admin",
            name="config-admin",
            key_hash=hash_api_key(key),
            role=ActorRole.ADMIN,
        )
    )
    audit_store = FakeConfigAuditStore()
    manager = SimpleNamespace(
        auth_store=auth_store,
        config_audit_store=audit_store,
        config=SimpleNamespace(app_env=env.get("APP_ENV", "development"), auth_enabled=True),
        reload=lambda: {"reloaded": True, "rebuilt": []},
    )
    captured_updates = []
    current_env = dict(env)

    def fake_write_env_file(updates):
        captured_updates.append(dict(updates))
        current_env.update(updates)

    import core.config_manager as config_manager

    monkeypatch.setenv("APP_ENV", env.get("APP_ENV", "development"))
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setattr(config_manager, "get_config_manager", lambda: manager)
    monkeypatch.setattr(config_router, "get_config_manager", lambda: manager)
    monkeypatch.setattr(config_router, "_read_env_file", lambda: dict(current_env))
    monkeypatch.setattr(config_router, "_write_env_file", fake_write_env_file)

    app = FastAPI()
    app.include_router(config_router.router)
    return TestClient(app), {"Authorization": f"Bearer {key}"}, audit_store, captured_updates


def test_config_get_masks_secret_values(monkeypatch):
    client, headers, _audit_store, _updates = _config_client(
        monkeypatch,
        {
            "APP_ENV": "production",
            "AUTH_ENABLED": "true",
            "LLM_API_KEY": "sk-live-secret-value",
            "JUDGE_API_KEY": "judge-secret-value",
            "REPORT_QUALITY_MIN_SCORE": "0.8",
        },
    )

    resp = client.get("/api/config", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_api_key"] == "sk-l************alue"
    assert body["judge_api_key"] == "judg**********alue"
    assert "sk-live-secret-value" not in str(body)
    assert body["production_readonly_fields"]


def test_config_update_writes_audit_with_masked_secret(monkeypatch):
    client, headers, audit_store, updates = _config_client(
        monkeypatch,
        {
            "APP_ENV": "development",
            "AUTH_ENABLED": "true",
            "LLM_API_KEY": "old-secret-value",
            "LLM_PROVIDER": "openai_compatible",
        },
    )

    resp = client.put(
        "/api/config",
        headers={**headers, "X-Request-ID": "req-123"},
        json={
            "llm_provider": "openai_compatible",
            "llm_api_key": "new-secret-value",
            "app_env": "development",
            "auth_enabled": True,
        },
    )

    assert resp.status_code == 200
    assert updates[-1]["LLM_API_KEY"] == "new-secret-value"
    assert audit_store.logs[-1].actor == "config-admin"
    assert audit_store.logs[-1].action == "config_updated"
    assert audit_store.logs[-1].request_id == "req-123"
    assert "old-secret-value" not in str(audit_store.logs[-1].before_masked)
    assert "new-secret-value" not in str(audit_store.logs[-1].after_masked)
