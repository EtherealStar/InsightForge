"""Agent 工具层 — 公开 API

提供 ReAct Agent 工具系统的核心组件:
    - BaseTool / ToolParameter / ToolResult     — 工具定义与结果
    - ToolRegistry / get_tool_registry          — 工具注册与发现
    - register_tool                             — 自动注册装饰器
    - ToolChain / ToolChainStep / ToolChainResult — 工具链编排
    - AsyncToolExecutor / ToolCall              — 异步执行
    - 异常类型                                    — 工具层异常层次
"""

from agent.tools.base import BaseTool, ToolParameter, ToolResult
from agent.tools.registry import ToolRegistry, get_tool_registry, register_tool
from agent.tools.chain import ToolChain, ToolChainStep, ToolChainResult
from agent.tools.executor import AsyncToolExecutor, ToolCall
from agent.tools.errors import (
    ToolError,
    ToolNotFoundError,
    ToolValidationError,
    ToolExecutionError,
    ToolTimeoutError,
    ToolChainError,
)

__all__ = [
    # 基类
    "BaseTool",
    "ToolParameter",
    "ToolResult",
    # 注册
    "ToolRegistry",
    "get_tool_registry",
    "register_tool",
    # 工具链
    "ToolChain",
    "ToolChainStep",
    "ToolChainResult",
    # 执行器
    "AsyncToolExecutor",
    "ToolCall",
    # 异常
    "ToolError",
    "ToolNotFoundError",
    "ToolValidationError",
    "ToolExecutionError",
    "ToolTimeoutError",
    "ToolChainError",
]
