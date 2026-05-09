"""内置工具：Web 搜索

通过多个互联网搜索引擎并发搜索实时信息，结果经程序化去重聚合后返回。
支持 DuckDuckGo（免费）和 Tavily（需 API Key）。
"""

import structlog
from typing import Any

from agent.tools.base import BaseTool, ToolParameter

logger = structlog.get_logger(__name__)


class WebSearchTool(BaseTool):
    """通过互联网搜索引擎并发搜索实时信息并自动去重聚合。"""

    def __init__(self, config_manager: Any):
        self._config_manager = config_manager

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "通过互联网搜索引擎搜索实时信息。"
            "适用于需要查找最新事件、实时数据、或本地新闻库中没有的信息。"
            "搜索结果会从多个搜索引擎并发获取并自动去重聚合。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="搜索关键词",
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description="每个搜索引擎返回的结果数量上限",
                required=False,
                default=8,
            ),
        ]

    def _run(self, query: str, max_results: int = 8, **kwargs: Any) -> str:
        """执行多引擎并发搜索并返回聚合结果。"""
        from services.web_search_service import WebSearchService

        # 从 config_manager 动态获取最新的 Tavily API Key
        tavily_key = self._config_manager.config.tavily_api_key

        service = WebSearchService(tavily_api_key=tavily_key)
        return service.search_and_aggregate(query, max_results)
