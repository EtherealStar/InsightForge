"""Builtin tool: create a draft intel fact."""
from __future__ import annotations

from typing import Any

from agent.tools.base import BaseTool, ToolParameter
from agent.tools.builtin.formatting import format_fact_item


class CreateIntelFactTool(BaseTool):
    def __init__(self, intel_service: Any):
        self._intel_service = intel_service

    @property
    def name(self) -> str:
        return "create_intel_fact"

    @property
    def description(self) -> str:
        return "创建 draft 状态的结构化事实。必须提供证据，Agent 不能直接创建 active fact。"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("fact_kind", "string", "fact/event/signal", required=False, default="fact"),
            ToolParameter("fact_type", "string", "事实类型", required=False, default="general"),
            ToolParameter("dimension", "string", "分析维度", required=False, default="general"),
            ToolParameter("subject", "string", "事实主体"),
            ToolParameter("predicate", "string", "事实动作"),
            ToolParameter("object", "string", "事实客体", required=False, default=""),
            ToolParameter("fact_text", "string", "人类可读原子事实"),
            ToolParameter("attributes", "object", "结构化属性", required=False, default={}),
            ToolParameter("event_date", "string", "事件日期 YYYY-MM-DD 或空", required=False, default=""),
            ToolParameter("competitor_ids", "array", "关联竞品 ID", required=False, default=[], items_type="integer"),
            ToolParameter("product_ids", "array", "关联产品 ID", required=False, default=[], items_type="integer"),
            ToolParameter("parent_chunk_id", "string", "证据父块 ID；与 url 至少提供一个", required=False, default=""),
            ToolParameter("url", "string", "证据 URL；与 parent_chunk_id 至少提供一个", required=False, default=""),
            ToolParameter("evidence_snippet", "string", "支撑事实的短证据片段"),
            ToolParameter("confidence_score", "number", "置信度 0-1", required=False, default=0.0),
        ]

    def _run(self, **kwargs: Any) -> str:
        parent_chunk_id = str(kwargs.get("parent_chunk_id") or "").strip()
        url = str(kwargs.get("url") or "").strip()
        if not parent_chunk_id and not url:
            raise ValueError("create_intel_fact requires parent_chunk_id or url evidence")
        data = {
            "fact_kind": kwargs.get("fact_kind") or "fact",
            "fact_type": kwargs.get("fact_type") or "general",
            "dimension": kwargs.get("dimension") or "general",
            "subject": kwargs["subject"],
            "predicate": kwargs["predicate"],
            "object": kwargs.get("object") or "",
            "fact_text": kwargs["fact_text"],
            "attributes": kwargs.get("attributes") or {},
            "event_date": kwargs.get("event_date") or None,
            "confidence_score": kwargs.get("confidence_score") or 0.0,
            "status": "draft",
            "competitor_ids": kwargs.get("competitor_ids") or [],
            "product_ids": kwargs.get("product_ids") or [],
            "evidence": [
                {
                    "parent_chunk_id": parent_chunk_id or None,
                    "url": url,
                    "snippet": kwargs["evidence_snippet"],
                    "evidence_type": "source_chunk" if parent_chunk_id else "url",
                    "relevance_score": 1.0,
                }
            ],
        }
        saved = self._intel_service.create_fact(data, created_by="agent")
        detail = self._intel_service.get_fact_detail(saved.id) or {"id": saved.id}
        return "已创建 draft fact:\n\n" + format_fact_item(detail)
