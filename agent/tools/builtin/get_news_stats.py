"""内置工具：获取新闻库统计信息

查询数据库中的文章总数、来源分布等统计数据。
"""

import structlog
from typing import Any

from agent.tools.base import BaseTool, ToolParameter
from core.protocols import ArticleStoreProtocol

logger = structlog.get_logger(__name__)


class GetNewsStatsTool(BaseTool):
    """获取新闻库的统计信息。"""

    def __init__(self, article_store: ArticleStoreProtocol):
        self._article_store = article_store

    @property
    def name(self) -> str:
        return "get_news_stats"

    @property
    def description(self) -> str:
        return (
            "获取新闻库的统计概览，包括文章总数、各来源数量、各状态数量等。"
            "适用于用户询问数据库状态、数据量等问题。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    def _run(self, **kwargs: Any) -> str:
        """获取统计信息并格式化为文本。"""
        stats = self._article_store.get_stats()

        parts = [f"新闻库统计信息:"]

        if "total" in stats:
            parts.append(f"  - 文章总数: {stats['total']}")
        if "by_status" in stats:
            parts.append("  - 按状态分布:")
            for status, count in stats["by_status"].items():
                parts.append(f"    - {status}: {count}")
        if "by_source" in stats:
            parts.append("  - 按来源分布:")
            for source, count in stats["by_source"].items():
                parts.append(f"    - {source}: {count}")
        if "by_language" in stats:
            parts.append("  - 按语言分布:")
            for lang, count in stats["by_language"].items():
                parts.append(f"    - {lang}: {count}")
        if "latest_article" in stats and stats["latest_article"]:
            parts.append(f"  - 最新文章时间: {stats['latest_article']}")

        return "\n".join(parts)
