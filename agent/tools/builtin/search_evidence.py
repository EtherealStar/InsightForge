"""Builtin tool: filtered source evidence search."""
from __future__ import annotations

from datetime import date
from typing import Any

from agent.tools.base import BaseTool, ToolParameter
from agent.tools.builtin.formatting import truncate


class SearchEvidenceTool(BaseTool):
    """Search original source evidence through hybrid RAG."""

    def __init__(self, evidence_search_service: Any):
        self._evidence_search_service = evidence_search_service

    @property
    def name(self) -> str:
        return "search_evidence"

    @property
    def description(self) -> str:
        return (
            "检索原文证据片段，走父子分块 RAG，可按竞品、文档类型和日期过滤。"
            "用于查找可溯源证据，不用于查询结构化 facts。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("query", "string", "要检索的证据查询文本"),
            ToolParameter("top_k", "integer", "返回证据数量，范围 1-20", required=False, default=5),
            ToolParameter(
                "competitor_ids",
                "array",
                "竞品 ID 过滤，空数组表示不过滤",
                required=False,
                default=[],
                items_type="integer",
            ),
            ToolParameter("document_type", "string", "文档类型过滤，空字符串表示不过滤", required=False, default=""),
            ToolParameter("date_from", "string", "开始日期 YYYY-MM-DD，空字符串表示不限", required=False, default=""),
            ToolParameter("date_to", "string", "结束日期 YYYY-MM-DD，空字符串表示不限", required=False, default=""),
        ]

    def _run(
        self,
        query: str,
        top_k: int = 5,
        competitor_ids: list[int] | None = None,
        document_type: str = "",
        date_from: str = "",
        date_to: str = "",
        **kwargs: Any,
    ) -> str:
        if top_k < 1 or top_k > 20:
            raise ValueError("top_k must be between 1 and 20")
        filters: dict[str, Any] = {}
        normalized_competitors = [int(v) for v in competitor_ids or []]
        if normalized_competitors:
            filters["competitor_ids"] = normalized_competitors
        if document_type.strip():
            filters["document_type"] = document_type.strip()
        if date_from.strip():
            filters["date_from"] = self._validate_date(date_from.strip(), "date_from")
        if date_to.strip():
            filters["date_to"] = self._validate_date(date_to.strip(), "date_to")

        results = self._evidence_search_service.search(
            query=query,
            top_k=top_k,
            filters=filters or None,
        )
        if not results:
            return "未找到匹配的原文证据。"

        parts = [f"找到 {len(results)} 条原文证据:"]
        for i, result in enumerate(results, 1):
            chunk = result.parent_chunk
            parts.append(
                f"\n{i}. **{chunk.doc_name or 'Untitled'}**\n"
                f"   source_document_id: {chunk.document_id}\n"
                f"   parent_chunk_id: {chunk.parent_chunk_id}\n"
                f"   url: {chunk.url or '-'}\n"
                f"   score: {round(float(result.rrf_score), 6)} | "
                f"match_sources: {', '.join(result.match_sources) or '-'}\n"
                f"   snippet: {truncate(chunk.content, 600)}"
            )
        return "\n".join(parts)

    @staticmethod
    def _validate_date(value: str, field_name: str) -> str:
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise ValueError(f"{field_name} must use YYYY-MM-DD") from exc
