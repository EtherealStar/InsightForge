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
import uuid
import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, Literal

from agent.react.parser import ReActParser, StreamingReActParser
from agent.react.prompts import (
    build_react_system_prompt,
    format_tool_descriptions,
)
from agent.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)

# 事件类型
EventType = Literal[
    "llm_delta",
    "thought",
    "action_start",
    "action_result",
    "answer_delta",
    "answer",
    "error",
    # Legacy event names accepted for compatibility with stored events/tests.
    "action",
    "observation",
]

MAX_EVENT_CONTENT_CHARS = 4000
MAX_LOG_VALUE_CHARS = 12000
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "token",
    "secret",
    "password",
    "webhook_url",
    "url",
}


@dataclass
class AgentEvent:
    """ReAct 过程中的一个事件，用于流式传输到前端。"""

    event_type: EventType
    content: str = ""
    run_id: str | None = None
    step_index: int | None = None
    sequence: int | None = None
    timestamp: str | None = None
    duration_ms: int | None = None
    raw_content: str | None = None
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_result: dict | None = None
    metadata: dict | None = None

    def to_dict(self) -> dict:
        """序列化为字典（用于 JSON 传输）。"""
        d: dict[str, Any] = {
            "event_type": self.event_type,
            "content": self.content,
        }
        if self.run_id is not None:
            d["run_id"] = self.run_id
        if self.step_index is not None:
            d["step_index"] = self.step_index
        if self.sequence is not None:
            d["sequence"] = self.sequence
        if self.timestamp is not None:
            d["timestamp"] = self.timestamp
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        if self.raw_content is not None:
            d["raw_content"] = self.raw_content
        if self.tool_name is not None:
            d["tool_name"] = self.tool_name
        if self.tool_input is not None:
            d["tool_input"] = self.tool_input
        if self.tool_result is not None:
            d["tool_result"] = self.tool_result
        if self.metadata is not None:
            d["metadata"] = self.metadata
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
        run_id: str | None = None,
    ):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.max_steps = max_steps
        self.system_prompt_override = system_prompt_override
        self.parser = ReActParser()
        self.run_id = run_id or str(uuid.uuid4())
        self._sequence = 0

    def _new_event(
        self,
        event_type: EventType,
        content: str = "",
        *,
        step_index: int | None = None,
        duration_ms: int | None = None,
        raw_content: str | None = None,
        tool_name: str | None = None,
        tool_input: dict | None = None,
        tool_result: dict | None = None,
        metadata: dict | None = None,
    ) -> AgentEvent:
        self._sequence += 1
        return AgentEvent(
            event_type=event_type,
            content=content,
            run_id=self.run_id,
            step_index=step_index,
            sequence=self._sequence,
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
            raw_content=raw_content,
            tool_name=tool_name,
            tool_input=_sanitize_for_log(tool_input) if tool_input else None,
            tool_result=tool_result,
            metadata=metadata,
        )

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
            for event in self._react_loop(question, stream_llm=False):
                result.events.append(event)
                if event.event_type == "answer":
                    result.answer = event.content
                elif event.event_type in ("action_start", "action") and event.tool_name:
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
            yield from self._react_loop(question, stream_llm=True)
        except Exception as e:
            logger.exception(f"ReAct Agent 流式执行异常: {e}")
            yield self._new_event(
                event_type="error",
                content=f"处理问题时发生错误: {e}",
            )

    def _react_loop(
        self, question: str, *, stream_llm: bool
    ) -> Iterator[AgentEvent]:
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

        logger.info(
            "agent.run_start",
            run_id=self.run_id,
            max_steps=self.max_steps,
            question_length=len(question),
        )

        for step_num in range(self.max_steps):
            step_index = step_num + 1
            logger.info(
                "agent.step_start",
                run_id=self.run_id,
                step_index=step_index,
                max_steps=self.max_steps,
            )

            # 调用 LLM
            try:
                llm_output, streamed_answer = yield from self._generate_llm_output(
                    messages=messages,
                    step_index=step_index,
                    stream_llm=stream_llm,
                )
            except Exception as e:
                logger.exception(
                    "agent.llm_error",
                    run_id=self.run_id,
                    step_index=step_index,
                    error=str(e),
                )
                yield self._new_event(
                    event_type="error",
                    content=f"AI 模型调用失败: {e}",
                    step_index=step_index,
                )
                return

            logger.debug(
                "agent.llm_output",
                run_id=self.run_id,
                step_index=step_index,
                output=_truncate_value(llm_output, MAX_LOG_VALUE_CHARS),
            )

            # 解析输出
            steps = self.parser.parse(llm_output)

            if not steps:
                # LLM 输出无法解析，直接作为回答
                yield self._new_event(
                    event_type="answer",
                    content=llm_output,
                    step_index=step_index,
                )
                return

            # 将 LLM 的完整输出追加到消息历史
            messages.append({"role": "assistant", "content": llm_output})

            # 处理解析出的步骤
            has_answer = False
            has_action = False

            for parsed_step in steps:
                if parsed_step.step_type == "thought":
                    yield self._new_event(
                        event_type="thought",
                        content=parsed_step.content,
                        step_index=step_index,
                        raw_content=parsed_step.content,
                    )

                elif parsed_step.step_type == "action":
                    has_action = True
                    tool_name = parsed_step.tool_name
                    tool_input = parsed_step.tool_input or {}

                    yield self._new_event(
                        event_type="action_start",
                        content=parsed_step.content,
                        step_index=step_index,
                        tool_name=tool_name,
                        tool_input=tool_input,
                    )

                    # 执行工具
                    observation, tool_event = self._execute_tool(
                        tool_name, tool_input, step_index
                    )

                    yield self._new_event(
                        event_type="action_result",
                        content=observation,
                        step_index=step_index,
                        tool_name=tool_name,
                        tool_result=tool_event,
                    )

                    # 将工具结果追加到消息历史
                    messages.append({
                        "role": "user",
                        "content": f"Observation: {observation}",
                    })

                elif parsed_step.step_type == "answer":
                    has_answer = True
                    if not streamed_answer:
                        yield self._new_event(
                            event_type="answer_delta",
                            content=parsed_step.content,
                            step_index=step_index,
                        )
                    yield self._new_event(
                        event_type="answer",
                        content=parsed_step.content,
                        step_index=step_index,
                    )

            if has_answer:
                return

            # 如果本轮没有 action 也没有 answer，强制结束
            if not has_action:
                yield self._new_event(
                    event_type="answer",
                    content=llm_output,
                    step_index=step_index,
                )
                return

        # 达到最大步数，要求 LLM 基于已有信息给出回答
        logger.warning(
            "agent.max_steps_reached",
            run_id=self.run_id,
            max_steps=self.max_steps,
        )

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
            yield self._new_event(
                event_type="answer",
                content=answer_content,
                step_index=self.max_steps + 1,
            )
        except Exception as e:
            logger.exception(
                "agent.final_answer_error",
                run_id=self.run_id,
                error=str(e),
            )
            yield self._new_event(
                event_type="error",
                content=f"生成最终回答时失败: {e}",
                step_index=self.max_steps + 1,
            )

    def _generate_llm_output(
        self,
        *,
        messages: list[dict],
        step_index: int,
        stream_llm: bool,
    ) -> Iterator[AgentEvent | tuple[str, bool]]:
        """调用 LLM，流式模式下同时产出 token 事件。"""
        if not stream_llm or not hasattr(self.llm_client, "generate_with_history_stream"):
            output = self.llm_client.generate_with_history(messages)
            return_value = (output, False)
            yield from ()
            return return_value

        parser = StreamingReActParser()
        chunks: list[str] = []
        streamed_answer = False
        started = time.time()

        for token in self.llm_client.generate_with_history_stream(messages):
            chunks.append(token)
            yield self._new_event(
                event_type="llm_delta",
                content=token,
                step_index=step_index,
            )
            for step in parser.feed(token):
                if step.step_type == "answer":
                    streamed_answer = True
                    yield self._new_event(
                        event_type="answer_delta",
                        content=step.content,
                        step_index=step_index,
                    )

        output = "".join(chunks)
        parser.flush()
        logger.info(
            "agent.llm_stream_complete",
            run_id=self.run_id,
            step_index=step_index,
            duration_ms=round((time.time() - started) * 1000),
            output_length=len(output),
        )
        return_value = (output, streamed_answer)
        yield from ()
        return return_value

    def _execute_tool(
        self, tool_name: str | None, tool_input: dict, step_index: int
    ) -> tuple[str, dict]:
        """执行工具并返回观察结果文本。"""
        if not tool_name:
            content = "错误: 未指定工具名称"
            return content, {"success": False, "error": content}

        if not self.tool_registry.has(tool_name):
            available = ", ".join(self.tool_registry.list_names())
            content = (
                f"错误: 工具 '{tool_name}' 不存在。"
                f"可用工具: {available}"
            )
            logger.warning(
                "agent.tool_missing",
                run_id=self.run_id,
                step_index=step_index,
                tool_name=tool_name,
                available_tools=self.tool_registry.list_names(),
            )
            return content, {"success": False, "error": content}

        try:
            tool = self.tool_registry.get(tool_name)
            started = time.time()
            logger.info(
                "agent.tool_start",
                run_id=self.run_id,
                step_index=step_index,
                tool_name=tool_name,
                tool_input=_sanitize_for_log(tool_input),
            )
            result = tool.execute(**tool_input)
            result_dict = _sanitize_for_log(result.to_dict())
            elapsed_ms = round((time.time() - started) * 1000)

            if result.success:
                # 将工具结果转为字符串
                data = result.data
                if isinstance(data, str):
                    observation = data
                else:
                    observation = json.dumps(data, ensure_ascii=False, indent=2)
                logger.info(
                    "agent.tool_result",
                    run_id=self.run_id,
                    step_index=step_index,
                    tool_name=tool_name,
                    duration_ms=elapsed_ms,
                    result=result_dict,
                )
            else:
                observation = f"工具执行失败: {result.error}"
                logger.warning(
                    "agent.tool_error",
                    run_id=self.run_id,
                    step_index=step_index,
                    tool_name=tool_name,
                    duration_ms=elapsed_ms,
                    result=result_dict,
                )

            return _truncate_for_event(observation), {
                "success": result.success,
                "tool_name": result.tool_name,
                "execution_time": result.execution_time,
                "truncated": len(observation) > MAX_EVENT_CONTENT_CHARS,
                "full_length": len(observation),
            }

        except Exception as e:
            logger.exception(
                "agent.tool_exception",
                run_id=self.run_id,
                step_index=step_index,
                tool_name=tool_name,
                error=str(e),
            )
            content = f"工具执行异常: {e}"
            return content, {"success": False, "error": str(e)}


def _truncate_for_event(value: str) -> str:
    if len(value) <= MAX_EVENT_CONTENT_CHARS:
        return value
    return value[:MAX_EVENT_CONTENT_CHARS] + "\n... [truncated]"


def _truncate_value(value: Any, max_chars: int) -> Any:
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        return {
            "value": value[:max_chars],
            "truncated": True,
            "full_length": len(value),
        }
    return value


def _sanitize_for_log(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(sensitive in key_text for sensitive in SENSITIVE_KEYS):
                sanitized[key] = "***"
            else:
                sanitized[key] = _sanitize_for_log(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_for_log(item) for item in value]
    if isinstance(value, str):
        return _truncate_value(value, MAX_LOG_VALUE_CHARS)
    return value
