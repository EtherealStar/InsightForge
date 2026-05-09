"""ReAct 输出解析器

将 LLM 的文本输出解析为结构化的 ReActStep 列表。
支持 Thought / Action / Action Input / Observation / Answer 格式。
"""

import json
import re
import structlog
from dataclasses import dataclass, field
from typing import Literal, Any

logger = structlog.get_logger(__name__)

StepType = Literal["thought", "action", "answer"]


@dataclass
class ReActStep:
    """ReAct 循环中的一个步骤。"""

    step_type: StepType
    content: str = ""
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None


class ReActParser:
    """解析 LLM 输出为 ReActStep 列表。

    支持解析以下格式：
        Thought: ...
        Action: tool_name
        Action Input: {"key": "value"}
        Answer: ...
    """

    # 正则模式  — 使用 DOTALL 使 . 匹配换行
    _THOUGHT_RE = re.compile(
        r"Thought:\s*(.+?)(?=\n(?:Action:|Answer:)|$)", re.DOTALL
    )
    _ACTION_RE = re.compile(r"Action:\s*(\S+)")
    _ACTION_INPUT_RE = re.compile(
        r"Action Input:\s*(.+?)(?=\n(?:Thought:|Answer:)|\Z)", re.DOTALL
    )
    _ANSWER_RE = re.compile(r"Answer:\s*(.+)", re.DOTALL)

    def parse(self, llm_output: str) -> list[ReActStep]:
        """解析完整的 LLM 输出为步骤列表。

        Args:
            llm_output: LLM 生成的原始文本。

        Returns:
            解析出的步骤列表。
        """
        steps: list[ReActStep] = []
        text = llm_output.strip()

        if not text:
            return steps

        # 检查是否包含 Answer
        answer_match = self._ANSWER_RE.search(text)

        # 提取 Thought
        thought_match = self._THOUGHT_RE.search(text)
        if thought_match:
            thought_content = thought_match.group(1).strip()
            if thought_content:
                steps.append(ReActStep(
                    step_type="thought",
                    content=thought_content,
                ))

        # 提取 Action + Action Input
        action_match = self._ACTION_RE.search(text)
        if action_match:
            tool_name = action_match.group(1).strip()
            tool_input = {}

            input_match = self._ACTION_INPUT_RE.search(text)
            if input_match:
                raw_input = input_match.group(1).strip()
                tool_input = self._parse_json_input(raw_input)

            steps.append(ReActStep(
                step_type="action",
                content=f"调用 {tool_name}",
                tool_name=tool_name,
                tool_input=tool_input,
            ))

        # 提取 Answer
        if answer_match:
            answer_content = answer_match.group(1).strip()
            if answer_content:
                steps.append(ReActStep(
                    step_type="answer",
                    content=answer_content,
                ))

        # 如果完全无法解析，将整个输出视为 answer
        if not steps:
            steps.append(ReActStep(
                step_type="answer",
                content=text,
            ))

        return steps

    @staticmethod
    def _parse_json_input(raw: str) -> dict:
        """尝试解析 JSON 格式的工具输入。

        支持容错：如果 JSON 不合法，尝试修复常见问题。
        """
        # 清理可能的 markdown 代码块标记
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # 去掉 ```json 和 ```
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        try:
            result = json.loads(cleaned)
            if isinstance(result, dict):
                return result
            return {"value": result}
        except json.JSONDecodeError:
            logger.warning(f"JSON 解析失败，尝试容错处理: {cleaned[:100]}")

            # 尝试提取花括号内容
            brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if brace_match:
                try:
                    return json.loads(brace_match.group())
                except json.JSONDecodeError:
                    pass

            # 最后回退：如果内容看起来是单个字符串值
            if cleaned and not cleaned.startswith("{"):
                return {"query": cleaned}

            return {}


class StreamingReActParser:
    """流式 ReAct 解析器 — 逐 token 解析。

    维护内部状态机，在接收到完整的一行时判断步骤类型。
    """

    def __init__(self):
        self._buffer = ""
        self._current_step_type: StepType | None = None
        self._current_content = ""
        self._action_name: str | None = None

    def reset(self):
        """重置解析器状态。"""
        self._buffer = ""
        self._current_step_type = None
        self._current_content = ""
        self._action_name = None

    def feed(self, token: str) -> list[ReActStep]:
        """输入一个 token，返回解析完成的步骤列表（可能为空）。

        Args:
            token: 新的 token。

        Returns:
            在本次 token 后识别完成的步骤列表。
        """
        self._buffer += token
        completed_steps: list[ReActStep] = []

        # 按行检查
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()

            if not line:
                continue

            step = self._process_line(line)
            if step:
                completed_steps.append(step)

        return completed_steps

    def flush(self) -> list[ReActStep]:
        """处理缓冲区中剩余的内容。"""
        steps: list[ReActStep] = []
        remaining = self._buffer.strip()
        if remaining:
            step = self._process_line(remaining)
            if step:
                steps.append(step)
        # 如果还有未完成的答案内容
        if self._current_step_type == "answer" and self._current_content:
            steps.append(ReActStep(
                step_type="answer",
                content=self._current_content.strip(),
            ))
            self._current_content = ""
        self.reset()
        return steps

    def _process_line(self, line: str) -> ReActStep | None:
        """处理一行文本。"""
        if line.startswith("Thought:"):
            content = line[len("Thought:"):].strip()
            self._current_step_type = "thought"
            return ReActStep(step_type="thought", content=content)

        elif line.startswith("Action:"):
            self._action_name = line[len("Action:"):].strip()
            self._current_step_type = "action"
            return None  # 等待 Action Input

        elif line.startswith("Action Input:"):
            raw_input = line[len("Action Input:"):].strip()
            tool_input = ReActParser._parse_json_input(raw_input)
            step = ReActStep(
                step_type="action",
                content=f"调用 {self._action_name}",
                tool_name=self._action_name,
                tool_input=tool_input,
            )
            self._action_name = None
            return step

        elif line.startswith("Answer:"):
            content = line[len("Answer:"):].strip()
            self._current_step_type = "answer"
            self._current_content = content
            return ReActStep(step_type="answer", content=content)

        else:
            # 正文续行 — 追加到当前步骤
            if self._current_step_type == "answer":
                self._current_content += "\n" + line

        return None
