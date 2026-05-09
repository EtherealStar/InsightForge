"""深度研究 Runner（Agent 层）。

负责：
- 构建深度研究专用 prompt
- 创建并运行 ReActAgent
- 将最终 answer 写入研究报告存储服务
"""

from __future__ import annotations

from typing import Iterator

from agent.react.agent import AgentEvent, ReActAgent
from agent.react.prompts import build_deep_research_prompt, format_tool_descriptions
from agent.tools.registry import ToolRegistry
from core.protocols import LLMClientProtocol
from services.deep_research_service import DeepResearchService


class DeepResearchRunner:
    """执行深度研究流程的 Agent 层编排器。"""

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        tool_registry: ToolRegistry,
        report_service: DeepResearchService,
        max_steps: int = 15,
    ):
        self._llm_client = llm_client
        self._tool_registry = tool_registry
        self._report_service = report_service
        self._max_steps = max_steps

    def run_stream(self, topic: str) -> Iterator[AgentEvent]:
        """流式执行深度研究并在完成后持久化报告。"""
        tools = self._tool_registry.list_tools()
        tool_desc = format_tool_descriptions(tools)
        system_prompt = build_deep_research_prompt(
            tool_descriptions=tool_desc,
            max_steps=self._max_steps,
        )

        agent = ReActAgent(
            llm_client=self._llm_client,
            tool_registry=self._tool_registry,
            max_steps=self._max_steps,
            system_prompt_override=system_prompt,
        )

        answer_content = ""
        for event in agent.run_stream(topic):
            yield event
            if event.event_type == "answer":
                answer_content = event.content

        if answer_content:
            self._report_service.save_report(topic=topic, content=answer_content)
