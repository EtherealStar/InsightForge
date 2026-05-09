"""工具链管理系统 — 编排多个工具的有序执行

核心组件:
    ToolChainStep    — 链中的单步定义（工具名 + 参数模板）
    ToolChainResult  — 链执行结果（每步结果 + 整体状态）
    ToolChain        — 链式管理器（添加步骤 → 顺序执行 → 收集结果）

特性:
    - 管道传参: 参数值为 "$prev" 时自动替换为上一步结果的 data
    - 失败策略: stop_on_failure 控制某步失败后是否中止整条链
    - 结果聚合: 完整保留每一步的 ToolResult
"""

import time
import structlog
from dataclasses import dataclass, field
from typing import Any

from agent.tools.base import ToolResult
from agent.tools.errors import ToolChainError, ToolNotFoundError
from agent.tools.registry import get_tool_registry

logger = structlog.get_logger(__name__)

# 管道传参占位符 — 参数值为此值时，替换为上一步结果
PIPE_PLACEHOLDER = "$prev"


@dataclass
class ToolChainStep:
    """工具链中的单步定义。

    Attributes:
        tool_name:  要调用的工具名称（必须已注册）。
        params:     传给工具的参数。值为 "$prev" 的参数在执行时
                    会被替换为上一步的 ToolResult.data。
        step_name:  可选的步骤说明（用于日志/调试）。
    """

    tool_name: str
    params: dict[str, Any] = field(default_factory=dict)
    step_name: str = ""

    def __post_init__(self) -> None:
        if not self.step_name:
            self.step_name = f"执行 {self.tool_name}"


@dataclass
class ToolChainResult:
    """工具链执行结果。

    Attributes:
        success:         整条链是否全部成功。
        step_results:    每一步的 ToolResult 列表。
        total_time:      整条链的总执行时间(秒)。
        failed_step:     失败的步骤索引 (-1 表示全部成功)。
        chain_name:      链名称。
    """

    success: bool = True
    step_results: list[ToolResult] = field(default_factory=list)
    total_time: float = 0.0
    failed_step: int = -1
    chain_name: str = ""

    @property
    def last_result(self) -> ToolResult | None:
        """最后一步的结果（通常是最终输出）。"""
        return self.step_results[-1] if self.step_results else None

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "success": self.success,
            "chain_name": self.chain_name,
            "total_time": round(self.total_time, 4),
            "failed_step": self.failed_step,
            "steps": [r.to_dict() for r in self.step_results],
        }


class ToolChain:
    """工具链管理器 — 编排多个工具的有序执行。

    使用方式:
        chain = ToolChain("新闻分析链")
        chain.add_step("search_news", params={"query": "AI 新闻"})
        chain.add_step("generate_brief", params={"articles": "$prev"})
        result = chain.run()

    Args:
        name:             链名称（用于日志和结果标识）。
        stop_on_failure:  某步失败后是否中止（默认 True）。
    """

    def __init__(self, name: str = "unnamed_chain", stop_on_failure: bool = True):
        self.name = name
        self.stop_on_failure = stop_on_failure
        self._steps: list[ToolChainStep] = []

    def add_step(
        self,
        tool_name: str,
        params: dict[str, Any] | None = None,
        step_name: str = "",
    ) -> "ToolChain":
        """添加一个执行步骤。

        Args:
            tool_name:  工具名称。
            params:     工具参数（支持 "$prev" 管道传参）。
            step_name:  可选的步骤说明。

        Returns:
            self（支持链式调用）。
        """
        step = ToolChainStep(
            tool_name=tool_name,
            params=params or {},
            step_name=step_name,
        )
        self._steps.append(step)
        return self

    def clear(self) -> None:
        """清空所有步骤。"""
        self._steps.clear()

    @property
    def steps(self) -> list[ToolChainStep]:
        """当前所有步骤（只读副本）。"""
        return list(self._steps)

    @property
    def step_count(self) -> int:
        """步骤数量。"""
        return len(self._steps)

    def run(self) -> ToolChainResult:
        """顺序执行所有步骤。

        对每一步:
            1. 从注册中心获取工具
            2. 解析参数中的 "$prev" 占位符
            3. 调用工具的 execute() 方法
            4. 收集结果

        Returns:
            ToolChainResult: 链执行结果。

        Raises:
            ToolChainError: stop_on_failure=True 且某步失败时。
        """
        if not self._steps:
            logger.warning(f"工具链 '{self.name}' 没有任何步骤")
            return ToolChainResult(chain_name=self.name)

        registry = get_tool_registry()
        chain_result = ToolChainResult(chain_name=self.name)
        start_time = time.time()
        prev_result: ToolResult | None = None

        logger.info(
            f"开始执行工具链 '{self.name}' ({len(self._steps)} 步)"
        )

        for i, step in enumerate(self._steps):
            logger.info(
                f"  [{i + 1}/{len(self._steps)}] {step.step_name}"
            )

            # 1. 获取工具
            try:
                tool = registry.get(step.tool_name)
            except ToolNotFoundError as e:
                error_result = ToolResult(
                    success=False,
                    error=str(e),
                    tool_name=step.tool_name,
                )
                chain_result.step_results.append(error_result)
                chain_result.success = False
                chain_result.failed_step = i

                if self.stop_on_failure:
                    chain_result.total_time = time.time() - start_time
                    raise ToolChainError(self.name, i, str(e)) from e
                continue

            # 2. 解析管道参数
            resolved_params = self._resolve_params(step.params, prev_result)

            # 3. 执行工具
            result = tool.execute(**resolved_params)
            chain_result.step_results.append(result)

            # 4. 检查结果
            if not result.success:
                chain_result.success = False
                chain_result.failed_step = i
                logger.warning(
                    f"  [{i + 1}] 失败: {result.error}"
                )

                if self.stop_on_failure:
                    chain_result.total_time = time.time() - start_time
                    raise ToolChainError(
                        self.name, i,
                        f"{step.tool_name}: {result.error}",
                    )
            else:
                logger.info(
                    f"  [{i + 1}] 成功 ({result.execution_time:.3f}s)"
                )

            prev_result = result

        chain_result.total_time = time.time() - start_time
        logger.info(
            f"工具链 '{self.name}' 完成: "
            f"success={chain_result.success}, "
            f"time={chain_result.total_time:.3f}s"
        )
        return chain_result

    @staticmethod
    def _resolve_params(
        params: dict[str, Any],
        prev_result: ToolResult | None,
    ) -> dict[str, Any]:
        """解析参数中的管道占位符。

        将值为 "$prev" 的参数替换为上一步结果的 data。
        """
        resolved = {}
        for key, value in params.items():
            if value == PIPE_PLACEHOLDER and prev_result is not None:
                resolved[key] = prev_result.data
            else:
                resolved[key] = value
        return resolved

    def __repr__(self) -> str:
        step_names = [s.tool_name for s in self._steps]
        return f"<ToolChain '{self.name}': {' → '.join(step_names)}>"
