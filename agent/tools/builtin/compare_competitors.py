"""Builtin tool: compare competitors using structured facts."""
from __future__ import annotations

from typing import Any

from agent.tools.base import BaseTool, ToolParameter
from agent.tools.builtin.formatting import enum_value, obj_value


class CompareCompetitorsTool(BaseTool):
    """对比多个竞品，基于 fact/event 聚合而不是文章摘要。"""

    def __init__(self, competitor_service: Any):
        self._competitor_service = competitor_service

    @property
    def name(self) -> str:
        return "compare_competitors"

    @property
    def description(self) -> str:
        return "基于结构化 facts/events 对比多个竞品，支持按维度过滤。"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("competitor_ids", "array", "要对比的竞品 ID 列表，至少 2 个", items_type="integer"),
            ToolParameter("dimensions", "array", "维度过滤；空数组表示所有维度", required=False, default=[], items_type="string"),
            ToolParameter("date_from", "string", "开始日期 YYYY-MM-DD", required=False, default=""),
            ToolParameter("date_to", "string", "结束日期 YYYY-MM-DD", required=False, default=""),
        ]

    def _run(
        self,
        competitor_ids: list[int],
        dimensions: list[str] | None = None,
        date_from: str = "",
        date_to: str = "",
        **kwargs: Any,
    ) -> str:
        if not competitor_ids or len(competitor_ids) < 2:
            return "请提供至少 2 个竞品 ID 进行对比。可使用 list_competitors 查看可用竞品。"
        time_window = {}
        if date_from:
            time_window["date_from"] = date_from
        if date_to:
            time_window["date_to"] = date_to
        comparison = self._competitor_service.compare_competitor_facts(
            [int(v) for v in competitor_ids],
            dimensions=dimensions or None,
            time_window=time_window or None,
        )
        rows = comparison.get("comparisons") or []
        parts = [f"# 竞品事实对比: {competitor_ids}"]
        for row in rows:
            if not row:
                continue
            if "dimensions" in row:
                parts.append(f"\n## Competitor {row.get('competitor_id')}")
                profiles = row.get("dimensions") or []
            else:
                profiles = [row]
            for profile in profiles:
                comp = profile.get("competitor")
                aggregates = profile.get("aggregates") or {}
                facts = profile.get("facts") or []
                parts.append(
                    f"\n### {obj_value(comp, 'name', profile.get('competitor_id', 'unknown'))}\n"
                    f"总 facts: {aggregates.get('total', len(facts))}\n"
                    f"按维度: {aggregates.get('by_dimension', {})}\n"
                    f"按类型: {aggregates.get('by_type', {})}"
                )
                for fact in facts[:5]:
                    parts.append(
                        f"- [{enum_value(obj_value(fact, 'fact_type'))}/"
                        f"{enum_value(obj_value(fact, 'dimension'))}] "
                        f"{obj_value(fact, 'fact_text')}"
                    )
        return "\n".join(parts)
