"""内置工具：列出所有监控中的竞品

从 CompetitorStore 获取竞品列表，展示名称、行业、标签等基本信息。
"""

import structlog
from typing import Any

from agent.tools.base import BaseTool, ToolParameter

logger = structlog.get_logger(__name__)


class ListCompetitorsTool(BaseTool):
    """列出所有当前监控中的竞品公司。"""

    def __init__(self, competitor_service: Any):
        self._competitor_service = competitor_service

    @property
    def name(self) -> str:
        return "list_competitors"

    @property
    def description(self) -> str:
        return (
            "列出所有当前监控中的竞品公司，包含名称、行业、标签等基本信息。"
            "适用于用户想了解有哪些竞品、查看竞品清单等场景。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="status",
                type="string",
                description="竞品状态过滤: active(监控中) 或 archived(已归档)",
                required=False,
                default="active",
            ),
        ]

    def _run(self, status: str = "active", **kwargs: Any) -> str:
        """获取竞品列表并格式化为文本。"""
        competitors = self._competitor_service.list_competitors(status=status)

        if not competitors:
            return f"当前没有状态为 '{status}' 的竞品记录。请先添加竞品。"

        parts = []
        for i, comp in enumerate(competitors, 1):
            tags_str = ", ".join(comp.tags) if comp.tags else "无标签"
            aliases_str = ", ".join(comp.aliases) if comp.aliases else "无别名"
            parts.append(
                f"{i}. **{comp.name}** (ID: {comp.id})\n"
                f"   行业: {comp.industry or '未设置'}\n"
                f"   别名: {aliases_str}\n"
                f"   标签: {tags_str}\n"
                f"   官网: {comp.website or '未设置'}\n"
                f"   简介: {comp.description or '无'}"
            )

        return (
            f"当前共有 {len(competitors)} 个{status}竞品:\n\n"
            + "\n\n".join(parts)
        )
