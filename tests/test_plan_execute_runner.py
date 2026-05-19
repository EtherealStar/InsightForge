"""PlanExecuteRunner 测试。"""

from types import SimpleNamespace

from agent.react.agent import AgentEvent
from agent.react.plan_execute_runner import (
    PlanExecuteRunner,
    _extract_todos,
    _parse_plan,
)
from models.agent_session import AgentSession, ResearchTodo, SessionStatus


def test_parse_plan_json_and_extract_todos():
    plan = _parse_plan(
        '{"goal":"研究AI","todos":[{"id":"todo-1","title":"检索资料","status":"pending"}]}'
    )
    todos = _extract_todos(plan)

    assert plan["goal"] == "研究AI"
    assert todos[0].id == "todo-1"
    assert todos[0].title == "检索资料"


def test_parse_plan_markdown_fallback():
    plan = _parse_plan("# 研究计划\n1. 检索本地新闻\n2. 阅读关键文章")
    todos = _extract_todos(plan)

    assert "raw" in plan
    assert todos[0].title == "研究计划"
    assert todos[1].title == "检索本地新闻"


class FakeStore:
    def __init__(self):
        self.sessions = {}
        self.events = []
        self.completed = None

    def create_session(self, topic, plan, todos, messages=None):
        session = AgentSession(
            id="session-1",
            topic=topic,
            status=SessionStatus.PLANNED,
            plan=plan,
            todos=todos,
            messages=messages or [],
        )
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def update_status(self, session_id, status, error=None):
        session = self.sessions[session_id]
        session.status = status
        session.error = error
        return session

    def append_event(self, session_id, event):
        self.events.append(event)
        self.sessions[session_id].events.append(event)

    def update_todos(self, session_id, todos):
        self.sessions[session_id].todos = todos
        return self.sessions[session_id]

    def complete_session(self, session_id, final_answer, report_filename):
        session = self.sessions[session_id]
        session.status = SessionStatus.COMPLETED
        session.final_answer = final_answer
        session.report_filename = report_filename
        self.completed = session
        return session

    def fail_session(self, session_id, error):
        session = self.sessions[session_id]
        session.status = SessionStatus.FAILED
        session.error = error
        return session


def test_generate_plan_creates_session():
    llm = SimpleNamespace(
        generate=lambda system, user: (
            '{"goal":"研究AI","todos":[{"id":"todo-1","title":"检索资料","status":"pending"}]}'
        )
    )
    store = FakeStore()
    runner = PlanExecuteRunner(
        llm_client=llm,
        tool_registry=SimpleNamespace(list_tools=lambda: []),
        session_store=store,
        report_service=SimpleNamespace(save_report=lambda topic, content: "x.md"),
    )

    session = runner.generate_plan("AI")

    assert session.status == SessionStatus.PLANNED
    assert session.todos[0].title == "检索资料"
    assert session.messages[-1]["role"] == "assistant"


def test_execute_updates_todos_and_saves_report(monkeypatch):
    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run_stream(self, question):
            yield AgentEvent(
                event_type="action_start",
                content="search",
                tool_name="search_evidence",
                run_id=self.kwargs["run_id"],
            )
            yield AgentEvent(
                event_type="action_result",
                content="ok",
                run_id=self.kwargs["run_id"],
            )
            yield AgentEvent(
                event_type="answer",
                content="final report",
                run_id=self.kwargs["run_id"],
            )

    monkeypatch.setattr("agent.react.plan_execute_runner.ReActAgent", FakeAgent)
    store = FakeStore()
    session = AgentSession(
        id="session-1",
        topic="AI",
        plan={"goal": "研究AI"},
        todos=[ResearchTodo(id="todo-1", title="检索资料")],
    )
    store.sessions[session.id] = session
    runner = PlanExecuteRunner(
        llm_client=SimpleNamespace(),
        tool_registry=SimpleNamespace(list_tools=lambda: []),
        session_store=store,
        report_service=SimpleNamespace(
            save_report=lambda topic, content: "output/research/report.md"
        ),
    )

    events = list(runner.execute(session))

    assert "todo_update" in [event.event_type for event in events]
    assert store.completed.status == SessionStatus.COMPLETED
    assert store.completed.report_filename == "report.md"
