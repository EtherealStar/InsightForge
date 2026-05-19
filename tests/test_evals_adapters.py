from __future__ import annotations

from types import SimpleNamespace


def test_agent_events_to_multi_turn_normalizes_reference_tool_calls():
    from evals.adapters import agent_events_to_multi_turn

    events = [
        SimpleNamespace(
            event_type="thought",
            content="先检索一下",
            tool_name=None,
            tool_input=None,
        ),
        SimpleNamespace(
            event_type="action_start",
            content="调用工具",
            tool_name="search_evidence",
            tool_input={"query": "AI"},
        ),
        SimpleNamespace(
            event_type="action_result",
            content="检索结果",
            tool_name="search_evidence",
            tool_input=None,
        ),
        SimpleNamespace(
            event_type="answer",
            content="最终回答",
            tool_name=None,
            tool_input=None,
        ),
    ]

    sample = agent_events_to_multi_turn(
        question="最近有什么 AI 新闻？",
        events=events,
        reference="参考答案",
        reference_tool_calls=[
            "search_evidence",
            {"name": "query_intel_facts", "args": {"keyword": "today"}},
        ],
    )

    assert sample.reference == "参考答案"
    assert sample.reference_tool_calls is not None
    assert [call.name for call in sample.reference_tool_calls] == [
        "search_evidence",
        "query_intel_facts",
    ]
    assert sample.reference_tool_calls[1].args == {"keyword": "today"}
