"""Builtin tool: query insight claims."""
from __future__ import annotations

from typing import Any

from agent.tools.base import BaseTool, ToolParameter


class QueryInsightClaimsTool(BaseTool):
    def __init__(self, insight_service: Any):
        self._insight_service = insight_service

    @property
    def name(self) -> str:
        return "query_insight_claims"

    @property
    def description(self) -> str:
        return "按竞品、claim 类型、维度和状态查询分析 claims。"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("competitor_ids", "array", "竞品 ID 列表", required=False, default=[], items_type="integer"),
            ToolParameter("claim_type", "string", "claim 类型", required=False, default=""),
            ToolParameter("dimension", "string", "分析维度", required=False, default=""),
            ToolParameter("status", "string", "状态过滤", required=False, default=""),
            ToolParameter("limit", "integer", "返回数量，范围 1-50", required=False, default=20),
        ]

    def _run(
        self,
        competitor_ids: list[int] | None = None,
        claim_type: str = "",
        dimension: str = "",
        status: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> str:
        if limit < 1 or limit > 50:
            raise ValueError("limit must be between 1 and 50")
        filters: dict[str, Any] = {}
        if competitor_ids:
            filters["competitor_ids"] = [int(v) for v in competitor_ids]
        if claim_type.strip():
            filters["claim_type"] = claim_type.strip()
        if dimension.strip():
            filters["dimension"] = dimension.strip()
        if status.strip():
            filters["status"] = status.strip()
        claims = self._insight_service.list_claims(filters, limit=limit)
        if not claims:
            return "未找到匹配的 insight claims。"
        parts = [f"找到 {len(claims)} 条 claims:"]
        for i, claim in enumerate(claims, 1):
            parts.append(
                f"\n{i}. **{claim.get('claim_text')}**\n"
                f"   ID: {claim.get('id')} | type: {claim.get('claim_type')} | "
                f"dimension: {claim.get('dimension')} | status: {claim.get('status')}\n"
                f"   competitors: {claim.get('competitor_ids') or '-'} | "
                f"facts: {claim.get('fact_ids') or '-'}\n"
                f"   confidence: {claim.get('confidence_score', 0)}"
            )
        return "\n".join(parts)
