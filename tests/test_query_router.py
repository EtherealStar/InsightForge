"""Query Router 测试。"""

from types import SimpleNamespace
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

import delivery.api.query_router as query_router


def _build_app():
    app = FastAPI()
    app.include_router(query_router.router)
    return app


def test_query_non_stream(monkeypatch):
    fake_result = SimpleNamespace(
        answer="ok",
        events=[SimpleNamespace(to_dict=lambda: {"event_type": "answer", "content": "ok"})],
    )
    fake_service = SimpleNamespace(answer_agent=lambda q, run_id=None: fake_result)
    monkeypatch.setattr(query_router, "_get_query_service", lambda: fake_service)

    client = TestClient(_build_app())
    resp = client.post("/api/query", json={"question": "hi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "ok"
    assert body["events"][0]["event_type"] == "answer"


def test_query_stream_sse_format(monkeypatch):
    fake_events = [
        SimpleNamespace(to_dict=lambda: {"event_type": "thought", "content": "t"}),
        SimpleNamespace(to_dict=lambda: {"event_type": "answer", "content": "a"}),
    ]
    fake_service = SimpleNamespace(
        answer_agent_stream=lambda q, run_id=None: iter(fake_events)
    )
    monkeypatch.setattr(query_router, "_get_query_service", lambda: fake_service)

    client = TestClient(_build_app())
    resp = client.post("/api/query/stream", json={"question": "hi"})
    assert resp.status_code == 200
    text = resp.text
    assert 'data: {"event_type": "thought", "content": "t"}' in text
    assert 'data: {"event_type": "answer", "content": "a"}' in text
    assert "data: [DONE]" in text


def test_query_stream_error_event(monkeypatch):
    def fail_stream(q, run_id=None):
        raise RuntimeError("stream failed")
        yield

    fake_service = SimpleNamespace(answer_agent_stream=fail_stream)
    monkeypatch.setattr(query_router, "_get_query_service", lambda: fake_service)

    client = TestClient(_build_app())
    resp = client.post("/api/query/stream", json={"question": "hi"})
    assert resp.status_code == 200
    text = resp.text
    assert '"event_type": "error"' in text
    assert "stream failed" in text
    assert "data: [DONE]" in text


def test_list_query_sessions(monkeypatch):
    session = SimpleNamespace(
        id="s1",
        topic="hello",
        status=SimpleNamespace(value="active"),
        session_type="general_query",
        messages=[{"role": "user", "content": "hi"}],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    fake_store = SimpleNamespace(list_sessions=lambda session_type, limit, offset: [session])
    monkeypatch.setattr(query_router, "_get_session_store", lambda: fake_store)

    client = TestClient(_build_app())
    resp = client.get("/api/query/sessions")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["session_id"] == "s1"
    assert body["items"][0]["last_message_preview"] == "hi"


def test_get_query_session_404_for_missing(monkeypatch):
    fake_store = SimpleNamespace(get_session=lambda session_id: None)
    monkeypatch.setattr(query_router, "_get_session_store", lambda: fake_store)

    client = TestClient(_build_app())
    resp = client.get("/api/query/sessions/missing")

    assert resp.status_code == 404
