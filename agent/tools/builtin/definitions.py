"""Builtin tool definition registry."""
from __future__ import annotations

from agent.tools.builtin.compare_competitors import CompareCompetitorsTool
from agent.tools.builtin.create_insight_claim import CreateInsightClaimTool
from agent.tools.builtin.create_intel_fact import CreateIntelFactTool
from agent.tools.builtin.factory import BuiltinToolFactory
from agent.tools.builtin.get_competitor_profile import GetCompetitorProfileTool
from agent.tools.builtin.get_intel_fact import GetIntelFactTool
from agent.tools.builtin.link_fact_to_competitor import LinkFactToCompetitorTool
from agent.tools.builtin.link_fact_to_product import LinkFactToProductTool
from agent.tools.builtin.list_competitors import ListCompetitorsTool
from agent.tools.builtin.query_insight_claims import QueryInsightClaimsTool
from agent.tools.builtin.query_intel_facts import QueryIntelFactsTool
from agent.tools.builtin.search_evidence import SearchEvidenceTool
from agent.tools.builtin.specs import ToolDefinitionRegistry, ToolSpec
from agent.tools.builtin.update_intel_fact import UpdateIntelFactTool
from agent.tools.builtin.web_search import WebSearchTool
from agent.tools.builtin.generate_analysis_report import GenerateAnalysisReportTool


def create_builtin_tool_definition_registry() -> ToolDefinitionRegistry:
    registry = ToolDefinitionRegistry()
    for spec in [
        ToolSpec("search_evidence", SearchEvidenceTool, ("evidence_search_service",), tags=("evidence", "rag")),
        ToolSpec("query_intel_facts", QueryIntelFactsTool, ("intel_service",), tags=("intel", "fact")),
        ToolSpec("get_intel_fact", GetIntelFactTool, ("intel_service",), tags=("intel", "fact")),
        ToolSpec("create_intel_fact", CreateIntelFactTool, ("intel_service",), tags=("intel", "fact", "write")),
        ToolSpec("update_intel_fact", UpdateIntelFactTool, ("intel_service",), tags=("intel", "fact", "write")),
        ToolSpec("link_fact_to_competitor", LinkFactToCompetitorTool, ("intel_service",), tags=("intel", "fact", "write")),
        ToolSpec("link_fact_to_product", LinkFactToProductTool, ("intel_service",), tags=("intel", "fact", "write")),
        ToolSpec("create_insight_claim", CreateInsightClaimTool, ("insight_service",), tags=("insight", "claim", "write")),
        ToolSpec("query_insight_claims", QueryInsightClaimsTool, ("insight_service",), tags=("insight", "claim")),
        ToolSpec("web_search", WebSearchTool, ("web_search_service",), tags=("web",)),
        ToolSpec("list_competitors", ListCompetitorsTool, ("competitor_service",), tags=("competitor",)),
        ToolSpec("get_competitor_profile", GetCompetitorProfileTool, ("competitor_service",), tags=("competitor", "fact")),
        ToolSpec("compare_competitors", CompareCompetitorsTool, ("competitor_service",), tags=("competitor", "fact")),
        ToolSpec("generate_analysis_report", GenerateAnalysisReportTool, ("report_service",), tags=("report",)),
    ]:
        registry.register(spec)
    return registry


__all__ = [
    "BuiltinToolFactory",
    "ToolDefinitionRegistry",
    "ToolSpec",
    "create_builtin_tool_definition_registry",
]
