"""工具基类 — 所有 Agent 工具的抽象基础

核心组件:
    ToolParameter  — 描述工具的单个参数（生成 JSON Schema）
    ToolResult     — 工具执行结果的标准封装
    BaseTool       — 抽象基类，子类实现 name / description / parameters / _run()
"""

import time
import structlog
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from agent.tools.errors import ToolValidationError, ToolExecutionError

logger = structlog.get_logger(__name__)

# JSON Schema 支持的参数类型
ParameterType = Literal["string", "integer", "number", "boolean", "array", "object"]


@dataclass
class ToolParameter:
    """工具参数定义，可生成 OpenAI function calling 兼容的 JSON Schema。"""

    name: str
    type: ParameterType
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None

    # array 类型的 items 描述
    items_type: ParameterType | None = None

    def to_schema(self) -> dict:
        """生成该参数的 JSON Schema 片段。"""
        schema: dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum is not None:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        if self.type == "array" and self.items_type:
            schema["items"] = {"type": self.items_type}
        return schema


@dataclass
class ToolResult:
    """工具执行结果的标准封装。"""

    success: bool
    data: Any = None
    error: str | None = None
    execution_time: float = 0.0
    tool_name: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """序列化为字典。"""
        result = {
            "success": self.success,
            "tool_name": self.tool_name,
            "execution_time": round(self.execution_time, 4),
        }
        if self.success:
            result["data"] = self.data
        else:
            result["error"] = self.error
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    def __str__(self) -> str:
        if self.success:
            return f"ToolResult(tool={self.tool_name}, success=True, data={self.data!r})"
        return f"ToolResult(tool={self.tool_name}, success=False, error={self.error!r})"


class BaseTool(ABC):
    """Agent 工具抽象基类。

    子类必须实现:
        - name (property)        : 工具唯一标识
        - description (property) : 工具功能描述（供 LLM 理解）
        - parameters (property)  : 参数定义列表
        - _run(**kwargs)         : 实际执行逻辑

    使用方式:
        result = my_tool.execute(param1="value1", param2=42)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识名称。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """工具功能描述，供 LLM 理解工具用途。"""

    @property
    @abstractmethod
    def parameters(self) -> list[ToolParameter]:
        """工具接受的参数列表。"""

    @abstractmethod
    def _run(self, **kwargs: Any) -> Any:
        """子类实现的实际执行逻辑。

        Args:
            **kwargs: 经过校验的参数。

        Returns:
            任意类型的执行结果数据。

        Raises:
            任何异常将被 execute() 捕获并包装为 ToolResult。
        """

    def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具（模板方法）：参数校验 → _run() → 包装结果。

        这是工具的统一调用入口，子类不应覆写此方法。

        Args:
            **kwargs: 工具参数。

        Returns:
            ToolResult: 包含成功/失败状态、数据或错误信息、执行耗时。
        """
        start_time = time.time()

        try:
            # 1. 参数校验 + 默认值填充
            validated = self.validate_params(**kwargs)

            # 2. 执行实际逻辑
            logger.debug(f"执行工具 '{self.name}': params={validated}")
            data = self._run(**validated)

            elapsed = time.time() - start_time
            logger.info(f"工具 '{self.name}' 执行成功 ({elapsed:.3f}s)")

            return ToolResult(
                success=True,
                data=data,
                execution_time=elapsed,
                tool_name=self.name,
            )

        except ToolValidationError:
            # 校验异常直接抛出，不再包装
            raise

        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"工具 '{self.name}' 执行失败 ({elapsed:.3f}s): {error_msg}")

            return ToolResult(
                success=False,
                error=error_msg,
                execution_time=elapsed,
                tool_name=self.name,
            )

    def validate_params(self, **kwargs: Any) -> dict:
        """参数校验：必填检查 + 默认值填充。

        Args:
            **kwargs: 原始参数。

        Returns:
            dict: 校验并填充默认值后的参数。

        Raises:
            ToolValidationError: 校验失败。
        """
        validated = dict(kwargs)
        param_map = {p.name: p for p in self.parameters}

        # 检查必填参数
        missing = [
            p.name
            for p in self.parameters
            if p.required and p.name not in validated
        ]
        if missing:
            raise ToolValidationError(
                self.name, f"缺少必填参数: {', '.join(missing)}"
            )

        # 填充默认值
        for p in self.parameters:
            if p.name not in validated and p.default is not None:
                validated[p.name] = p.default

        # 检查未知参数
        known_names = set(param_map.keys())
        unknown = set(validated.keys()) - known_names
        if unknown:
            raise ToolValidationError(
                self.name, f"未知参数: {', '.join(unknown)}"
            )

        # 基本类型检查
        type_map: dict[str, type | tuple[type, ...]] = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        for p_name, value in validated.items():
            if p_name in param_map:
                expected = type_map.get(param_map[p_name].type)
                if expected and not isinstance(value, expected):
                    raise ToolValidationError(
                        self.name,
                        f"参数 '{p_name}' 类型错误: "
                        f"期望 {param_map[p_name].type}, "
                        f"实际 {type(value).__name__}",
                    )

        return validated

    def to_openai_schema(self) -> dict:
        """生成 OpenAI function calling 兼容的 JSON Schema。

        返回格式符合 OpenAI Chat Completions API 的 tools 参数要求，
        可直接用于 LLM 的 function calling / tool use。

        Returns:
            dict: OpenAI function 格式的工具描述。
        """
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_schema()
            if param.required:
                required.append(param.name)

        schema = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                },
            },
        }

        if required:
            schema["function"]["parameters"]["required"] = required

        return schema

    def to_dict(self) -> dict:
        """序列化为字典（用于工具列表展示）。"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                    "enum": p.enum,
                }
                for p in self.parameters
            ],
        }

    def __repr__(self) -> str:
        return f"<Tool '{self.name}': {self.description}>"
