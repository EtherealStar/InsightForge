"""ReAct Agent — 推理-行动循环核心

实现 ReAct（Reasoning + Acting）Agent，使 LLM 能够在多轮推理中
自主决策并调用工具，最终生成基于事实的回答。

核心组件:
    AgentEvent  — 流式输出的事件数据类
    AgentResult — 完整执行结果
    ReActAgent  — Agent 主循环
"""

import json
import time
import structlog
from dataclasses import dataclass, field
from typing import Any, Iterator, Literal

from agent.react.parser import ReActParser, ReActStep
from agent.react.prompts import (
    build_react_system_prompt,
    format_tool_descriptions,
)
from agent.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)

# 事件类型
EventType = Literal["thought", "action", "observation", "answer", "error"]


@dataclass
class AgentEvent:
    """ReAct 过程中的一个事件，用于流式传输到前端。"""

    event_type: EventType
    content: str = ""
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_result: dict | None = None

    def to_dict(self) -> dict:
        """序列化为字典（用于 JSON 传输）。"""
        d: dict[str, Any] = {
            "event_type": self.event_type,
            "content": self.content,
        }
        if self.tool_name is not None:
            d["tool_name"] = self.tool_name
        if self.tool_input is not None:
            d["tool_input"] = self.tool_input
        if self.tool_result is not None:
            d["tool_result"] = self.tool_result
        return d


@dataclass
class AgentResult:
    """ReAct Agent 的完整执行结果。"""

    answer: str = ""
    events: list[AgentEvent] = field(default_factory=list)
    total_steps: int = 0
    total_time: float = 0.0
    tools_called: list[str] = field(default_factory=list)
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "events": [e.to_dict() for e in self.events],
            "total_steps": self.total_steps,
            "total_time": round(self.total_time, 3),
            "tools_called": self.tools_called,
            "success": self.success,
            "error": self.error,
        }


class ReActAgent:
    """ReAct 架构 Agent — 推理-行动循环。

    在多轮对话中，LLM 分析用户问题 → 决定调用工具 → 接收工具结果
    → 继续推理或给出最终回答。

    Args:
        llm_client: 实现 LLMClientProtocol 的 LLM 客户端。
        tool_registry: 工具注册中心。
        max_steps: 最大推理步数（防止无限循环）。
    """

    def __init__(
        self,
        llm_client: Any,
        tool_registry: ToolRegistry,
        max_steps: int = 5,
        system_prompt_override: str | None = None,
    ):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.max_steps = max_steps
        self.system_prompt_override = system_prompt_override
        self.parser = ReActParser()

    def run(self, question: str) -> AgentResult:
        """同步执行 ReAct 循环，返回完整结果。

        Args:
            question: 用户问题。

        Returns:
            AgentResult: 包含最终答案和所有中间步骤。
        """
        result = AgentResult()
        start_time = time.time()

        try:
            for event in self._react_loop(question):
                result.events.append(event)
                if event.event_type == "answer":
                    result.answer = event.content
                elif event.event_type == "action" and event.tool_name:
                    result.tools_called.append(event.tool_name)
                    result.total_steps += 1
                elif event.event_type == "error":
                    result.success = False
                    result.error = event.content
        except Exception as e:
            logger.exception(f"ReAct Agent 执行异常: {e}")
            result.success = False
            result.error = str(e)
            result.answer = f"抱歉，处理您的问题时发生了错误: {e}"

        result.total_time = time.time() - start_time
        return result

    def run_stream(self, question: str) -> Iterator[AgentEvent]:
        """流式执行 ReAct 循环，逐步 yield AgentEvent。

        Args:
            question: 用户问题。

        Yields:
            AgentEvent: 每个推理/行动/观察/回答步骤。
        """
        try:
            yield from self._react_loop(question)
        except Exception as e:
            logger.exception(f"ReAct Agent 流式执行异常: {e}")
            yield AgentEvent(
                event_type="error",
                content=f"处理问题时发生错误: {e}",
            )

    def _react_loop(self, question: str) -> Iterator[AgentEvent]:
        """ReAct 核心循环。

        1. 构建 system prompt + 用户问题
        2. 循环：LLM 生成 → 解析 → 如果是 Action 则执行工具 → 追加 Observation → 继续
        3. 检测到 Answer 或达到最大步数时退出
        """
        # 构建工具描述和 system prompt
        tools = self.tool_registry.list_tools()
        tool_desc = format_tool_descriptions(tools)

        if self.system_prompt_override:
            system_prompt = self.system_prompt_override
        else:
            system_prompt = build_react_system_prompt(tool_desc, self.max_steps)

        # 消息历史
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        for step_num in range(self.max_steps):
            logger.info(f"ReAct 步骤 {step_num + 1}/{self.max_steps}")

            # 调用 LLM
            try:
                llm_output = self.llm_client.generate_with_history(messages)
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                yield AgentEvent(
                    event_type="error",
                    content=f"AI 模型调用失败: {e}",
                )
                return

            logger.debug(f"LLM 输出:\n{llm_output}")

            # 解析输出
            steps = self.parser.parse(llm_output)

            if not steps:
                # LLM 输出无法解析，直接作为回答
                yield AgentEvent(
                    event_type="answer",
                    content=llm_output,
                )
                return

            # 将 LLM 的完整输出追加到消息历史
            messages.append({"role": "assistant", "content": llm_output})

            # 处理解析出的步骤
            has_answer = False
            has_action = False

            for parsed_step in steps:
                if parsed_step.step_type == "thought":
                    yield AgentEvent(
                        event_type="thought",
                        content=parsed_step.content,
                    )

                elif parsed_step.step_type == "action":
                    has_action = True
                    tool_name = parsed_step.tool_name
                    tool_input = parsed_step.tool_input or {}

                    yield AgentEvent(
                        event_type="action",
                        content=parsed_step.content,
                        tool_name=tool_name,
                        tool_input=tool_input,
                    )

                    # 执行工具
                    observation = self._execute_tool(tool_name, tool_input)

                    yield AgentEvent(
                        event_type="observation",
                        content=observation,
                        tool_name=tool_name,
                    )

                    # 将工具结果追加到消息历史
                    messages.append({
                        "role": "user",
                        "content": f"Observation: {observation}",
                    })

                elif parsed_step.step_type == "answer":
                    has_answer = True
                    yield AgentEvent(
                        event_type="answer",
                        content=parsed_step.content,
                    )

            if has_answer:
                return

            # 如果本轮没有 action 也没有 answer，强制结束
            if not has_action:
                yield AgentEvent(
                    event_type="answer",
                    content=llm_output,
                )
                return

        # 达到最大步数，要求 LLM 基于已有信息给出回答
        logger.warning(f"ReAct 达到最大步数 {self.max_steps}，强制结束")

        messages.append({
            "role": "user",
            "content": (
                "你已经进行了足够多的工具调用。"
                "请根据已经获得的所有 Observation 信息，直接给出最终回答。\n"
                "Answer: "
            ),
        })

        try:
            final_output = self.llm_client.generate_with_history(messages)
            # 尝试解析 Answer
            final_steps = self.parser.parse(final_output)
            answer_content = final_output
            for s in final_steps:
                if s.step_type == "answer":
                    answer_content = s.content
                    break
            yield AgentEvent(
                event_type="answer",
                content=answer_content,
            )
        except Exception as e:
            yield AgentEvent(
                event_type="error",
                content=f"生成最终回答时失败: {e}",
            )

    def _execute_tool(
        self, tool_name: str | None, tool_input: dict
    ) -> str:
        """执行工具并返回观察结果文本。"""
        if not tool_name:
            return "错误: 未指定工具名称"

        if not self.tool_registry.has(tool_name):
            available = ", ".join(self.tool_registry.list_names())
            return (
                f"错误: 工具 '{tool_name}' 不存在。"
                f"可用工具: {available}"
            )

        try:
            tool = self.tool_registry.get(tool_name)
            result = tool.execute(**tool_input)

            if result.success:
                # 将工具结果转为字符串
                data = result.data
                if isinstance(data, str):
                    return data
                return json.dumps(data, ensure_ascii=False, indent=2)
            else:
                return f"工具执行失败: {result.error}"

        except Exception as e:
            logger.error(f"工具 '{tool_name}' 执行异常: {e}")
            return f"工具执行异常: {e}"
