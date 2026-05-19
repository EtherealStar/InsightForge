"""Builtin tool: update a non-active intel fact."""
from __future__ import annotations

from typing import Any

from agent.tools.base import BaseTool, ToolParameter
from agent.tools.builtin.formatting import format_fact_item


class UpdateIntelFactTool(BaseTool):
    def __init__(self, intel_service: Any):
        self._intel_service = intel_service

    @property
    def name(self) -> str:
        return "update_intel_fact"

    @property
    def description(self) -> str:
        return "修改 draft/rejected/archived 状态的结构化事实；Agent 不能激活 fact。"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("fact_id", "string", "IntelFact ID"),
            ToolParameter("fact_type", "string", "事实类型", required=False, default=""),
            ToolParameter("dimension", "string", "分析维度", required=False, default=""),
            ToolParameter("subject", "string", "事实主体", required=False, default=""),
            ToolParameter("predicate", "string", "事实动作", required=False, default=""),
            ToolParameter("object", "string", "事实客体", required=False, default=""),
            ToolParameter("fact_text", "string", "事实文本", required=False, default=""),
            ToolParameter("attributes", "object", "结构化属性", required=False, default={}),
            ToolParameter("event_date", "string", "事件日期 YYYY-MM-DD 或空", required=False, default=""),
            ToolParameter("importance_score", "number", "重要度 0-1", required=False, default=-1),
            ToolParameter("confidence_score", "number", "置信度 0-1", required=False, default=-1),
            ToolParameter("status", "string", "draft/rejected/archived", required=False, default=""),
        ]

    def _run(self, fact_id: str, **kwargs: Any) -> str:
        allowed_statuses = {"", "draft", "rejected", "archived"}
        status = str(kwargs.get("status") or "").strip()
        if status not in allowed_statuses:
            raise ValueError("Agent may only set status to draft, rejected, or archived")
        data: dict[str, Any] = {}
        for key in ("fact_type", "dimension", "subject", "predicate", "object", "fact_text", "event_date"):
            value = kwargs.get(key)
            if isinstance(value, str) and value.strip():
                data[key] = value.strip()
        if kwargs.get("attributes"):
            data["attributes"] = kwargs["attributes"]
        for key in ("importance_score", "confidence_score"):
            value = kwargs.get(key)
            if isinstance(value, (int, float)) and value >= 0:
                data[key] = value
        if status:
            data["status"] = status
        if not data:
            raise ValueError("no allowed fields provided")
        saved = self._intel_service.update_fact(fact_id, data, updated_by="agent")
        if not saved:
            return f"未找到事实: {fact_id}"
        detail = self._intel_service.get_fact_detail(saved.id) or {"id": saved.id}
        return "已更新 fact:\n\n" + format_fact_item(detail)
