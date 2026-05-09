"""异步工具执行器 — 在线程池中运行同步工具，提供异步调度能力

核心组件:
    AsyncToolExecutor — 基于 asyncio + ThreadPoolExecutor 的异步执行器

设计理由:
    项目现有的 Services / Infrastructure 层全部为同步代码，
    BaseTool._run() 也定义为同步方法。AsyncToolExecutor 通过
    run_in_executor() 在线程池中运行同步工具，使 Agent 调度层
    获得并发能力而不阻塞事件循环。
"""

import asyncio
import structlog
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from agent.tools.base import ToolResult
from agent.tools.chain import ToolChain, ToolChainResult
from agent.tools.errors import (
    ToolNotFoundError,
    ToolTimeoutError,
    ToolExecutionError,
)
from agent.tools.registry import get_tool_registry

logger = structlog.get_logger(__name__)

# 默认线程池大小
DEFAULT_MAX_WORKERS = 4
# 默认超时时间（秒）
DEFAULT_TIMEOUT = 60.0


@dataclass
class ToolCall:
    """一次工具调用的描述（用于 execute_batch）。

    Attributes:
        tool_name: 工具名称。
        params:    工具参数字典。
        call_id:   可选的调用标识（用于追踪）。
    """

    tool_name: str
    params: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""


class AsyncToolExecutor:
    """异步工具执行器。

    在 ThreadPoolExecutor 中运行同步工具的 execute() 方法，
    提供单工具异步执行、批量并发执行、带超时执行、工具链异步执行。

    Args:
        max_workers: 线程池最大工作线程数。
        default_timeout: 默认超时时间（秒），0 表示无超时。

    使用方式:
        executor = AsyncToolExecutor()

        # 单个工具
        result = await executor.execute("search_news", query="AI")

        # 批量并发
        results = await executor.execute_batch([
            ToolCall("search_news", {"query": "AI"}),
            ToolCall("get_news_stats"),
        ])

        # 带超时
        result = await executor.execute_with_timeout(
            "search_news", timeout=10.0, query="AI"
        )

        # 用完关闭
        executor.shutdown()
    """

    def __init__(
        self,
        max_workers: int = DEFAULT_MAX_WORKERS,
        default_timeout: float = DEFAULT_TIMEOUT,
    ):
        self._max_workers = max_workers
        self._default_timeout = default_timeout
        self._thread_pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="tool-executor",
        )
        self._registry = get_tool_registry()
        logger.info(
            f"AsyncToolExecutor 初始化: "
            f"max_workers={max_workers}, timeout={default_timeout}s"
        )

    async def execute(self, tool_name: str, **params: Any) -> ToolResult:
        """异步执行单个工具。

        在线程池中运行工具的同步 execute() 方法。

        Args:
            tool_name: 工具名称。
            **params: 工具参数。

        Returns:
            ToolResult: 工具执行结果。
        """
        try:
            tool = self._registry.get(tool_name)
        except ToolNotFoundError as e:
            return ToolResult(
                success=False,
                error=str(e),
                tool_name=tool_name,
            )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._thread_pool,
            lambda: tool.execute(**params),
        )
        return result

    async def execute_with_timeout(
        self,
        tool_name: str,
        timeout: float | None = None,
        **params: Any,
    ) -> ToolResult:
        """带超时控制的异步执行。

        Args:
            tool_name: 工具名称。
            timeout: 超时时间（秒），None 使用默认超时。
            **params: 工具参数。

        Returns:
            ToolResult: 工具执行结果或超时错误。
        """
        actual_timeout = timeout if timeout is not None else self._default_timeout

        try:
            result = await asyncio.wait_for(
                self.execute(tool_name, **params),
                timeout=actual_timeout,
            )
            return result

        except asyncio.TimeoutError:
            logger.error(
                f"工具 '{tool_name}' 执行超时 ({actual_timeout}s)"
            )
            return ToolResult(
                success=False,
                error=f"执行超时 ({actual_timeout}s)",
                tool_name=tool_name,
            )

    async def execute_batch(
        self,
        calls: list[ToolCall],
    ) -> list[ToolResult]:
        """并发执行多个工具调用。

        所有调用在线程池中并发执行，结果按输入顺序返回。

        Args:
            calls: 工具调用列表。

        Returns:
            list[ToolResult]: 与输入同序的结果列表。
        """
        if not calls:
            return []

        logger.info(f"批量执行 {len(calls)} 个工具调用")

        tasks = [
            self.execute(call.tool_name, **call.params)
            for call in calls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 将异常转换为 ToolResult
        final_results: list[ToolResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(
                    ToolResult(
                        success=False,
                        error=f"{type(result).__name__}: {result}",
                        tool_name=calls[i].tool_name,
                    )
                )
            else:
                final_results.append(result)

        succeeded = sum(1 for r in final_results if r.success)
        logger.info(
            f"批量执行完成: {succeeded}/{len(calls)} 成功"
        )
        return final_results

    async def execute_chain(self, chain: ToolChain) -> ToolChainResult:
        """在线程池中异步执行工具链。

        工具链内部仍然是顺序执行（步骤间可能有依赖），
        但整个链的执行不阻塞事件循环。

        Args:
            chain: 要执行的工具链。

        Returns:
            ToolChainResult: 链执行结果。
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._thread_pool,
            chain.run,
        )
        return result

    def shutdown(self, wait: bool = True) -> None:
        """关闭线程池。

        Args:
            wait: 是否等待正在执行的任务完成。
        """
        logger.info("AsyncToolExecutor 正在关闭...")
        self._thread_pool.shutdown(wait=wait)
        logger.info("AsyncToolExecutor 已关闭")

    def __repr__(self) -> str:
        return (
            f"<AsyncToolExecutor("
            f"workers={self._max_workers}, "
            f"timeout={self._default_timeout}s)>"
        )
