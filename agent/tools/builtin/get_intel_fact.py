"""Builtin tool: get one structured intel fact."""
from __future__ import annotations

from typing import Any

from agent.tools.base import BaseTool, ToolParameter
from agent.tools.builtin.formatting import format_fact_item, truncate


class GetIntelFactTool(BaseTool):
    def __init__(self, intel_service: Any):
        self._intel_service = intel_service

    @property
    def name(self) -> str:
        return "get_intel_fact"

    @property
    def description(self) -> str:
        return "获取单条结构化事实详情，包括关联竞品、产品和证据引用。"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [ToolParameter("fact_id", "string", "IntelFact ID")]

    def _run(self, fact_id: str, **kwargs: Any) -> str:
        fact = self._intel_service.get_fact_detail(fact_id)
        if not fact:
            return f"未找到事实: {fact_id}"
        parts = [format_fact_item(fact)]
        evidence_refs = fact.get("evidence_refs") or []
        if evidence_refs:
            parts.append("\n证据:")
            for i, evidence in enumerate(evidence_refs, 1):
                parts.append(
                    f"{i}. {evidence.get('title') or 'Untitled'}\n"
                    f"   source_document_id: {evidence.get('source_document_id') or '-'}\n"
                    f"   parent_chunk_id: {evidence.get('parent_chunk_id') or '-'}\n"
                    f"   url: {evidence.get('url') or '-'}\n"
                    f"   snippet: {truncate(evidence.get('snippet'), 400)}"
                )
        return "\n".join(parts)
