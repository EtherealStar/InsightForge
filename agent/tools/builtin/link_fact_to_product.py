"""Builtin tool: link fact to product."""
from __future__ import annotations

from typing import Any

from agent.tools.base import BaseTool, ToolParameter


class LinkFactToProductTool(BaseTool):
    def __init__(self, intel_service: Any):
        self._intel_service = intel_service

    @property
    def name(self) -> str:
        return "link_fact_to_product"

    @property
    def description(self) -> str:
        return "将结构化事实归因到指定产品线。"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("fact_id", "string", "IntelFact ID"),
            ToolParameter("product_id", "integer", "产品 ID"),
            ToolParameter("relation_type", "string", "subject/mentioned/affected", required=False, default="subject"),
            ToolParameter("confidence_score", "number", "关联置信度 0-1", required=False, default=1.0),
        ]

    def _run(
        self,
        fact_id: str,
        product_id: int,
        relation_type: str = "subject",
        confidence_score: float = 1.0,
        **kwargs: Any,
    ) -> str:
        self._intel_service.link_fact_to_product(
            fact_id,
            product_id,
            relation_type=relation_type,
            confidence_score=confidence_score,
        )
        return f"已将 fact {fact_id} 关联到 product {product_id} ({relation_type})。"
