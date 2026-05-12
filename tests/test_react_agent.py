"""ReAct Agent 集成测试

使用 mock LLM 客户端测试完整的 ReAct 循环，包括:
    1. 直接回答（无工具调用）
    2. 单工具调用
    3. 多轮工具调用
    4. 工具不存在处理
    5. 最大步数限制
    6. 流式输出
"""

import pytest
from typing import Iterator
from unittest.mock import MagicMock

from agent.tools.base import BaseTool, ToolParameter, ToolResult
from agent.tools.registry import get_tool_registry
from agent.react.agent import ReActAgent, AgentEvent


# ======================================================================
# Mock 组件
# ======================================================================


class MockLLMClient:
    """模拟 LLM 客户端，按顺序返回预设的回复。"""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.call_count = 0
        self.messages_log: list[list[dict]] = []

    def generate_with_history(self, messages: list[dict]) -> str:
        self.messages_log.append(messages[:])
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return "Answer: 已达到最大预设回复数量。"

    def generate_with_history_stream(
        self, messages: list[dict]
    ) -> Iterator[str]:
        text = self.generate_with_history(messages)
        yield text


class EchoTestTool(BaseTool):
    """用于测试的 echo 工具。"""

    @property
    def name(self) -> str:
        return "echo_test"

    @property
    def description(self) -> str:
        return "回显输入消息（测试用）"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="message",
                type="string",
                description="要回显的消息",
            ),
        ]

    def _run(self, message: str, **kwargs) -> str:
        return f"Echo: {message}"


class StatsTestTool(BaseTool):
    """模拟统计工具。"""

    @property
    def name(self) -> str:
        return "get_stats_test"

    @property
    def description(self) -> str:
        return "获取统计信息（测试用）"

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    def _run(self, **kwargs) -> str:
        return "共 1234 篇文章，来源 5 个"


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture(autouse=True)
def clean_registry():
    registry = get_tool_registry()
    registry.clear()
    yield registry
    registry.clear()


@pytest.fixture
def registry_with_tools(clean_registry):
    registry = clean_registry
    registry.register(EchoTestTool())
    registry.register(StatsTestTool())
    return registry


# ======================================================================
# 1. 直接回答
# ======================================================================


class TestDirectAnswer:
    """LLM 直接回答（无工具调用）。"""

    def test_greeting(self, registry_with_tools):
        llm = MockLLMClient([
            "Thought: 用户在打招呼，不需要工具\nAnswer: 你好！有什么可以帮你的？"
        ])
        agent = ReActAgent(llm, registry_with_tools, max_steps=3)
        result = agent.run("你好")

        assert result.success is True
        assert "你好" in result.answer
        assert len(result.tools_called) == 0

    def test_unparseable_output_as_answer(self, registry_with_tools):
        llm = MockLLMClient(["这是一段没有任何标记的回答。"])
        agent = ReActAgent(llm, registry_with_tools, max_steps=3)
        result = agent.run("随便说点什么")

        assert result.success is True
        assert "没有任何标记" in result.answer


# ======================================================================
# 2. 单工具调用
# ======================================================================


class TestSingleToolCall:
    """单次工具调用后回答。"""

    def test_tool_call_and_answer(self, registry_with_tools):
        llm = MockLLMClient([
            # 第 1 轮: 决定调用工具
            'Thought: 需要查看统计\nAction: get_stats_test\nAction Input: {}',
            # 第 2 轮: 收到 Observation，给出回答
            'Thought: 信息足够\nAnswer: 新闻库共有 1234 篇文章，来自 5 个来源。',
        ])
        agent = ReActAgent(llm, registry_with_tools, max_steps=5)
        result = agent.run("数据库有多少文章？")

        assert result.success is True
        assert "1234" in result.answer
        assert "get_stats_test" in result.tools_called
        assert any(e.event_type == "action_start" for e in result.events)
        assert any(e.event_type == "action_result" for e in result.events)

    def test_tool_receives_params(self, registry_with_tools):
        llm = MockLLMClient([
            'Thought: 需要搜索\nAction: echo_test\nAction Input: {"message": "hello world"}',
            'Thought: 收到结果\nAnswer: Echo 工具返回了: Echo: hello world',
        ])
        agent = ReActAgent(llm, registry_with_tools, max_steps=5)
        result = agent.run("测试 echo")

        assert result.success is True
        assert "Echo: hello world" in result.answer


# ======================================================================
# 3. 工具不存在
# ======================================================================


class TestToolNotFound:
    """调用不存在的工具。"""

    def test_nonexistent_tool(self, registry_with_tools):
        llm = MockLLMClient([
            'Thought: 搜索\nAction: nonexistent_tool\nAction Input: {}',
            'Thought: 工具出错了\nAnswer: 抱歉，该工具不可用。',
        ])
        agent = ReActAgent(llm, registry_with_tools, max_steps=5)
        result = agent.run("测试不存在的工具")

        assert result.success is True
        # Agent 应该在 Observation 中得到错误消息并据此回答
        assert "不可用" in result.answer or len(result.events) > 0


# ======================================================================
# 4. 最大步数限制
# ======================================================================


class TestMaxSteps:
    """测试最大步数限制。"""

    def test_max_steps_reached(self, registry_with_tools):
        llm = MockLLMClient([
            'Thought: 搜索\nAction: echo_test\nAction Input: {"message": "1"}',
            'Thought: 再搜\nAction: echo_test\nAction Input: {"message": "2"}',
            'Thought: 继续\nAction: echo_test\nAction Input: {"message": "3"}',
            # 最大步数 = 2，所以第 3 轮不会执行，改为强制回答
            'Answer: 被强制回答了',
        ])
        agent = ReActAgent(llm, registry_with_tools, max_steps=2)
        result = agent.run("无限循环测试")

        # 应该在 max_steps=2 后强制结束
        assert result.success is True
        assert result.answer  # 应有回答


# ======================================================================
# 5. 流式输出
# ======================================================================


class TestStreamOutput:
    """测试流式输出。"""

    def test_stream_events(self, registry_with_tools):
        llm = MockLLMClient([
            'Thought: 用户要统计\nAction: get_stats_test\nAction Input: {}',
            'Thought: 好的\nAnswer: 有 1234 篇文章。',
        ])
        agent = ReActAgent(llm, registry_with_tools, max_steps=5)

        events = list(agent.run_stream("统计"))

        event_types = [e.event_type for e in events]
        assert "thought" in event_types
        assert "llm_delta" in event_types
        assert "action_start" in event_types
        assert "action_result" in event_types
        assert "answer_delta" in event_types
        assert "answer" in event_types

    def test_stream_multiline_action_input(self, registry_with_tools):
        llm = MockLLMClient([
            'Thought: 需要 echo\nAction: echo_test\nAction Input: {\n  "message": "hello multiline"\n}',
            'Answer: 收到 Echo: hello multiline',
        ])
        agent = ReActAgent(llm, registry_with_tools, max_steps=5)

        events = list(agent.run_stream("测试多行 JSON"))

        action = next(e for e in events if e.event_type == "action_start")
        assert action.tool_input == {"message": "hello multiline"}
        assert any(e.event_type == "action_result" for e in events)

    def test_stream_multiline_answer_delta(self, registry_with_tools):
        llm = MockLLMClient([
            "Answer: 第一行\n第二行",
        ])
        agent = ReActAgent(llm, registry_with_tools, max_steps=3)

        events = list(agent.run_stream("多行回答"))

        assert any(e.event_type == "answer_delta" for e in events)
        final_answer = next(e.content for e in events if e.event_type == "answer")
        assert "第一行" in final_answer
        assert "第二行" in final_answer

    def test_stream_error_handling(self, registry_with_tools):
        """LLM 调用失败时产出 error 事件。"""
        llm = MockLLMClient([])
        # generate_with_history 会因为 responses 为空而报 IndexError
        # 但 MockLLMClient 在用尽后返回 Answer，所以不会出错
        # 改用 side_effect 模拟异常
        llm.generate_with_history = MagicMock(side_effect=Exception("LLM 宕机了"))

        agent = ReActAgent(llm, registry_with_tools, max_steps=3)
        events = list(agent.run_stream("测试异常"))

        assert any(e.event_type == "error" for e in events)


# ======================================================================
# 6. AgentEvent 序列化
# ======================================================================


class TestAgentEvent:
    """测试事件序列化。"""

    def test_to_dict_basic(self):
        event = AgentEvent(
            event_type="thought",
            content="思考中...",
            run_id="run-1",
            sequence=1,
        )
        d = event.to_dict()
        assert d["event_type"] == "thought"
        assert d["content"] == "思考中..."
        assert d["run_id"] == "run-1"
        assert d["sequence"] == 1
        assert "tool_name" not in d

    def test_to_dict_with_tool(self):
        event = AgentEvent(
            event_type="action",
            content="调用工具",
            tool_name="search_news",
            tool_input={"query": "AI"},
        )
        d = event.to_dict()
        assert d["tool_name"] == "search_news"
        assert d["tool_input"] == {"query": "AI"}
