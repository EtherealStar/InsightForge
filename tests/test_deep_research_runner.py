"""DeepResearchRunner 测试。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from agent.react.deep_research_runner import DeepResearchRunner


def test_runner_stream_and_save_report(monkeypatch):
    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run_stream(self, topic):
            yield SimpleNamespace(event_type="thought", content=f"thinking {topic}")
            yield SimpleNamespace(event_type="answer", content="final report")

    monkeypatch.setattr("agent.react.deep_research_runner.ReActAgent", FakeAgent)

    fake_param = SimpleNamespace(
        name="query",
        type="string",
        required=True,
        default=None,
        description="q",
    )
    fake_tool = SimpleNamespace(
        name="query_knowledge_base",
        description="search",
        parameters=[fake_param],
    )
    fake_registry = SimpleNamespace(list_tools=lambda: [fake_tool])

    report_service = MagicMock()
    runner = DeepResearchRunner(
        llm_client=MagicMock(),
        tool_registry=fake_registry,
        report_service=report_service,
        max_steps=15,
    )

    events = list(runner.run_stream("AI"))
    assert [e.event_type for e in events] == ["thought", "answer"]
    report_service.save_report.assert_called_once_with(
        topic="AI",
        content="final report",
    )
