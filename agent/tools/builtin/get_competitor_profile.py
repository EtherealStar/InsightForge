"""Builtin tool: get competitor fact profile."""
from __future__ import annotations

from typing import Any

from agent.tools.base import BaseTool, ToolParameter
from agent.tools.builtin.formatting import enum_value, format_fact_item, obj_value


class GetCompetitorProfileTool(BaseTool):
    """获取指定竞品的详细档案，包含产品线和结构化事实聚合。"""

    def __init__(self, competitor_service: Any):
        self._competitor_service = competitor_service

    @property
    def name(self) -> str:
        return "get_competitor_profile"

    @property
    def description(self) -> str:
        return "获取竞品档案、产品线、近期结构化 facts/events 和按维度/类型聚合的数据。"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("competitor_id", "integer", "竞品 ID"),
            ToolParameter("fact_limit", "integer", "最多返回多少条结构化事实", required=False, default=10),
        ]

    def _run(self, competitor_id: int, fact_limit: int = 10, **kwargs: Any) -> str:
        profile = self._competitor_service.get_competitor_fact_profile(
            competitor_id,
            {"limit": fact_limit},
        )
        if not profile:
            return f"未找到 ID 为 {competitor_id} 的竞品。请使用 list_competitors 查看可用竞品。"

        comp = profile["competitor"]
        products = profile.get("products") or []
        facts = profile.get("facts") or []
        aggregates = profile.get("aggregates") or {}
        parts = [
            f"# 竞品档案: {obj_value(comp, 'name')}",
            f"\n**行业**: {obj_value(comp, 'industry') or '未设置'}",
            f"**官网**: {obj_value(comp, 'website') or '未设置'}",
            f"**别名**: {', '.join(obj_value(comp, 'aliases', []) or []) or '无'}",
            f"**标签**: {', '.join(obj_value(comp, 'tags', []) or []) or '无'}",
            f"**简介**: {obj_value(comp, 'description') or '无'}",
            f"**状态**: {enum_value(obj_value(comp, 'status', 'active'))}",
            f"\n## Facts 聚合\n总数: {aggregates.get('total', len(facts))}\n"
            f"按维度: {aggregates.get('by_dimension', {})}\n"
            f"按类型: {aggregates.get('by_type', {})}",
        ]
        if products:
            parts.append(f"\n## 产品线 ({len(products)} 个)")
            for product in products:
                parts.append(
                    f"- **{obj_value(product, 'name')}** ({obj_value(product, 'category') or '未分类'})"
                    f" | 定价: {obj_value(product, 'pricing_info') or '未知'}\n"
                    f"  {obj_value(product, 'description') or '无描述'}"
                )
        else:
            parts.append("\n## 产品线\n暂无产品线记录。")

        if facts:
            parts.append(f"\n## 近期结构化事实 ({len(facts)} 条)")
            for i, fact in enumerate(facts, 1):
                if not isinstance(fact, dict):
                    fact = {
                        "id": obj_value(fact, "id"),
                        "fact_text": obj_value(fact, "fact_text"),
                        "fact_type": enum_value(obj_value(fact, "fact_type")),
                        "dimension": enum_value(obj_value(fact, "dimension")),
                        "status": enum_value(obj_value(fact, "status")),
                        "event_date": obj_value(fact, "event_date"),
                        "confidence_score": obj_value(fact, "confidence_score", 0),
                        "importance_score": obj_value(fact, "importance_score", 0),
                        "competitor_ids": obj_value(fact, "competitor_ids", []),
                        "product_ids": obj_value(fact, "product_ids", []),
                        "evidence_refs": [],
                    }
                parts.append(format_fact_item(fact, i))
        else:
            parts.append("\n## 近期结构化事实\n暂无关联 facts。")
        return "\n".join(parts)
