"""Builtin tool: generate analysis report through ReportService."""
from __future__ import annotations

from typing import Any

from agent.tools.base import BaseTool, ToolParameter


class GenerateAnalysisReportTool(BaseTool):
    """基于 fact/evidence 上下文生成竞品分析报告。"""

    def __init__(self, report_service: Any):
        self._report_service = report_service

    @property
    def name(self) -> str:
        return "generate_analysis_report"

    @property
    def description(self) -> str:
        return "基于结构化 facts、claims 和 evidence 生成竞品分析报告，保存草稿并运行质量门禁。"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter("competitor_ids", "array", "要分析的竞品 ID 列表", items_type="integer"),
            ToolParameter("report_type", "string", "overview/comparison/briefing/deep_research", required=False, default="overview"),
            ToolParameter("focus", "string", "分析重点", required=False, default=""),
            ToolParameter("dimensions", "array", "维度过滤；空数组表示不限", required=False, default=[], items_type="string"),
            ToolParameter("date_from", "string", "开始日期 YYYY-MM-DD", required=False, default=""),
            ToolParameter("date_to", "string", "结束日期 YYYY-MM-DD", required=False, default=""),
            ToolParameter("auto_publish", "boolean", "质量通过且配置允许时自动批准；默认关闭", required=False, default=False),
        ]

    def _run(
        self,
        competitor_ids: list[int],
        report_type: str = "overview",
        focus: str = "",
        dimensions: list[str] | None = None,
        date_from: str = "",
        date_to: str = "",
        auto_publish: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any] | str:
        if not competitor_ids:
            return "请提供至少一个竞品 ID。"
        return self._report_service.generate_analysis_report(
            [int(v) for v in competitor_ids],
            report_type=report_type,
            focus=focus,
            dimensions=dimensions or None,
            date_from=date_from or None,
            date_to=date_to or None,
            auto_publish=auto_publish,
        )
