"""工具注册中心 — 管理所有 Agent 工具的注册与发现

提供:
    ToolRegistry     — 线程安全单例，管理工具实例的注册、查询、Schema 生成
    @register_tool   — 类装饰器，定义工具类时自动注册到全局注册中心
    get_tool_registry() — 模块级便捷函数，获取全局唯一注册中心
"""

import threading
import structlog
from typing import Type

from agent.tools.base import BaseTool
from agent.tools.errors import ToolNotFoundError, ToolError

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """工具注册中心（线程安全单例）。

    管理所有 BaseTool 实例的注册和查询，供 Agent 在运行时发现可用工具
    并获取 OpenAI function calling 格式的 Schema。

    与项目中 ConfigManager 保持一致的单例模式。
    """

    _instance: "ToolRegistry | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self._tools: dict[str, BaseTool] = {}
        self._registry_lock = threading.Lock()
        logger.info("ToolRegistry 初始化完成")

    # ------------------------------------------------------------------
    # 注册与注销
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """注册一个工具实例。

        Args:
            tool: BaseTool 子类的实例。

        Raises:
            ToolError: 工具名称已被注册。
            TypeError: 参数不是 BaseTool 实例。
        """
        if not isinstance(tool, BaseTool):
            raise TypeError(
                f"只能注册 BaseTool 实例，收到 {type(tool).__name__}"
            )

        with self._registry_lock:
            if tool.name in self._tools:
                raise ToolError(
                    f"工具 '{tool.name}' 已注册，不可重复注册"
                )
            self._tools[tool.name] = tool
            logger.info(f"工具已注册: '{tool.name}'")

    def unregister(self, name: str) -> None:
        """注销一个工具。

        Args:
            name: 工具名称。

        Raises:
            ToolNotFoundError: 工具不存在。
        """
        with self._registry_lock:
            if name not in self._tools:
                raise ToolNotFoundError(name)
            del self._tools[name]
            logger.info(f"工具已注销: '{name}'")

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get(self, name: str) -> BaseTool:
        """按名称获取工具实例。

        Args:
            name: 工具名称。

        Returns:
            BaseTool: 工具实例。

        Raises:
            ToolNotFoundError: 工具不存在。
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(name)
        return tool

    def has(self, name: str) -> bool:
        """检查工具是否已注册。"""
        return name in self._tools

    def list_tools(self) -> list[BaseTool]:
        """返回所有已注册工具的列表。"""
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        """返回所有已注册工具的名称列表。"""
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # Schema 生成
    # ------------------------------------------------------------------

    def get_schemas(self) -> list[dict]:
        """批量生成所有工具的 OpenAI function calling Schema。

        返回的列表可直接作为 OpenAI Chat API 的 `tools` 参数:
            response = client.chat.completions.create(
                ...
                tools=registry.get_schemas()
            )

        Returns:
            list[dict]: 所有工具的 OpenAI Schema 列表。
        """
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def get_tool_descriptions(self) -> list[dict]:
        """获取所有工具的简要描述（用于展示）。"""
        return [tool.to_dict() for tool in self._tools.values()]

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """已注册工具数量。"""
        return len(self._tools)

    def clear(self) -> None:
        """清空所有注册（主要用于测试）。"""
        with self._registry_lock:
            self._tools.clear()
            logger.info("ToolRegistry 已清空")

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def __len__(self) -> int:
        return self.count

    def __repr__(self) -> str:
        names = ", ".join(self._tools.keys())
        return f"<ToolRegistry({self.count} tools): [{names}]>"


# ======================================================================
# 类装饰器：自动注册
# ======================================================================

def register_tool(cls: Type[BaseTool]) -> Type[BaseTool]:
    """类装饰器 — 定义工具类时自动实例化并注册到全局注册中心。

    使用方式:
        @register_tool
        class MyTool(BaseTool):
            ...

    注意: 装饰器会立即创建工具实例并注册，适用于无构造参数的工具类。
    需要依赖注入的工具应手动 register()。
    """
    if not (isinstance(cls, type) and issubclass(cls, BaseTool)):
        raise TypeError(
            f"@register_tool 只能用于 BaseTool 子类，收到 {cls}"
        )

    registry = get_tool_registry()
    try:
        tool_instance = cls()
        registry.register(tool_instance)
    except Exception as e:
        logger.warning(f"自动注册工具 {cls.__name__} 失败: {e}")

    return cls


# ======================================================================
# 模块级便捷函数
# ======================================================================

def get_tool_registry() -> ToolRegistry:
    """获取全局唯一的 ToolRegistry 实例。"""
    return ToolRegistry()
