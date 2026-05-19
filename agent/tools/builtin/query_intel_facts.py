"""Builtin tool: query structured intel facts."""
from __future__ import annotations

from datetime import date
from typing import Any

from agent.tools.base import BaseTool, ToolParameter
from agent.tools.builtin.formatting import format_fact_item


class QueryIntelFactsTool(BaseTool):
    def __init__(self, intel_service: Any):
        self._intel_service = intel_service

    @property
    def name(self) -> str:
        return "query_intel_facts"

    @property
    def description(self) -> str:
        return "查询结构化竞品事实，不走语义 RAG；适用于按竞品、产品、类型、维度、状态或日期筛选 facts。"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("competitor_ids", "array", "竞品 ID 列表", required=False, default=[], items_type="integer"),
            ToolParameter("product_ids", "array", "产品 ID 列表", required=False, default=[], items_type="integer"),
            ToolParameter("fact_type", "string", "事实类型过滤", required=False, default=""),
            ToolParameter("dimension", "string", "分析维度过滤", required=False, default=""),
            ToolParameter("date_from", "string", "开始日期 YYYY-MM-DD", required=False, default=""),
            ToolParameter("date_to", "string", "结束日期 YYYY-MM-DD", required=False, default=""),
            ToolParameter("status", "string", "状态过滤: draft/active/rejected/archived", required=False, default=""),
            ToolParameter("limit", "integer", "返回数量，范围 1-50", required=False, default=20),
        ]

    def _run(
        self,
        competitor_ids: list[int] | None = None,
        product_ids: list[int] | None = None,
        fact_type: str = "",
        dimension: str = "",
        date_from: str = "",
        date_to: str = "",
        status: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> str:
        if limit < 1 or limit > 50:
            raise ValueError("limit must be between 1 and 50")
        filters: dict[str, Any] = {}
        if competitor_ids:
            filters["competitor_ids"] = [int(v) for v in competitor_ids]
        if product_ids:
            filters["product_ids"] = [int(v) for v in product_ids]
        if fact_type.strip():
            filters["fact_type"] = fact_type.strip()
        if dimension.strip():
            filters["dimension"] = dimension.strip()
        if status.strip():
            filters["status"] = status.strip()
        if date_from.strip():
            filters["date_from"] = self._validate_date(date_from.strip(), "date_from")
        if date_to.strip():
            filters["date_to"] = self._validate_date(date_to.strip(), "date_to")

        facts = self._intel_service.list_facts(filters, limit=limit)
        if not facts:
            return "未找到匹配的结构化事实。"
        return "找到以下结构化事实:\n\n" + "\n\n".join(
            format_fact_item(fact, i) for i, fact in enumerate(facts, 1)
        )

    @staticmethod
    def _validate_date(value: str, field_name: str) -> str:
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise ValueError(f"{field_name} must use YYYY-MM-DD") from exc
