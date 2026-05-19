"""Builtin tool: create a draft insight claim."""
from __future__ import annotations

from typing import Any

from agent.tools.base import BaseTool, ToolParameter


class CreateInsightClaimTool(BaseTool):
    def __init__(self, insight_service: Any):
        self._insight_service = insight_service

    @property
    def name(self) -> str:
        return "create_insight_claim"

    @property
    def description(self) -> str:
        return "基于已有 facts 创建 draft 分析 claim。至少需要一个 fact_id，Agent 不能直接创建 active claim。"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("claim_text", "string", "分析结论文本"),
            ToolParameter("claim_type", "string", "trend/comparison/risk/opportunity/finding/hypothesis", required=False, default="finding"),
            ToolParameter("dimension", "string", "分析维度", required=False, default="general"),
            ToolParameter("competitor_ids", "array", "竞品 ID", required=False, default=[], items_type="integer"),
            ToolParameter("product_ids", "array", "产品 ID", required=False, default=[], items_type="integer"),
            ToolParameter("fact_ids", "array", "支撑事实 ID，至少一个", items_type="string"),
            ToolParameter("limitations", "string", "数据限制和推断边界", required=False, default=""),
            ToolParameter("confidence_score", "number", "置信度 0-1", required=False, default=0.0),
        ]

    def _run(self, **kwargs: Any) -> str:
        fact_ids = [str(v) for v in kwargs.get("fact_ids") or []]
        if not fact_ids:
            raise ValueError("create_insight_claim requires at least one fact_id")
        claim = self._insight_service.create_claim(
            {
                "claim_text": kwargs["claim_text"],
                "claim_type": kwargs.get("claim_type") or "finding",
                "dimension": kwargs.get("dimension") or "general",
                "competitor_ids": kwargs.get("competitor_ids") or [],
                "product_ids": kwargs.get("product_ids") or [],
                "fact_ids": fact_ids,
                "limitations": kwargs.get("limitations") or "",
                "confidence_score": kwargs.get("confidence_score") or 0.0,
                "status": "draft",
            },
            created_by="agent",
        )
        return (
            f"已创建 draft claim: {claim.id}\n"
            f"claim_type: {claim.claim_type}\n"
            f"dimension: {claim.dimension}\n"
            f"fact_ids: {claim.fact_ids}\n"
            f"text: {claim.claim_text}"
        )
