"""Plan Execute research router 测试。"""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import delivery.api.research_router as research_router
from agent.react.agent import AgentEvent
from models.agent_session import AgentSession, ResearchTodo, SessionStatus


def _build_app():
    app = FastAPI()
    app.include_router(research_router.router)
    return app


def test_create_research_plan(monkeypatch):
    session = AgentSession(
        id="session-1",
        topic="AI",
        status=SessionStatus.PLANNED,
        plan={"goal": "研究AI"},
        todos=[ResearchTodo(id="todo-1", title="检索资料")],
    )
    fake_runner = SimpleNamespace(generate_plan=lambda topic: session)
    monkeypatch.setattr(
        research_router, "_get_plan_execute_runner", lambda: fake_runner
    )

    client = TestClient(_build_app())
    resp = client.post("/api/research/sessions/plan", json={"topic": "AI"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "session-1"
    assert body["todos"][0]["title"] == "检索资料"


def test_update_research_plan(monkeypatch):
    session = AgentSession(
        id="session-1",
        topic="AI",
        plan={"goal": "new"},
        todos=[ResearchTodo(id="todo-1", title="更新资料")],
    )
    fake_store = SimpleNamespace(
        save_plan=lambda session_id, plan, todos: session
    )
    monkeypatch.setattr(research_router, "_get_session_store", lambda: fake_store)

    client = TestClient(_build_app())
    resp = client.put(
        "/api/research/sessions/session-1/plan",
        json={
            "plan": {"goal": "new"},
            "todos": [{"id": "todo-1", "title": "更新资料", "status": "pending"}],
        },
    )

    assert resp.status_code == 200
    assert resp.json()["todos"][0]["title"] == "更新资料"


def test_execute_research_session_stream(monkeypatch):
    session = AgentSession(id="session-1", topic="AI")
    fake_store = SimpleNamespace(get_session=lambda session_id: session)
    fake_runner = SimpleNamespace(
        execute=lambda s: iter([
            AgentEvent(event_type="todo_update", content="todo", run_id=s.id),
            AgentEvent(event_type="answer", content="done", run_id=s.id),
        ])
    )
    monkeypatch.setattr(research_router, "_get_session_store", lambda: fake_store)
    monkeypatch.setattr(
        research_router, "_get_plan_execute_runner", lambda: fake_runner
    )

    client = TestClient(_build_app())
    resp = client.post("/api/research/sessions/session-1/execute/stream")

    assert resp.status_code == 200
    assert '"event_type": "todo_update"' in resp.text
    assert '"event_type": "answer"' in resp.text
    assert "data: [DONE]" in resp.text
