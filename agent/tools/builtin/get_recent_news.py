"""内置工具：获取最近 N 小时的新闻列表

直接从 PostgreSQL 数据库按时间查询最新文章。
"""

import structlog
from typing import Any

from agent.tools.base import BaseTool, ToolParameter
from core.protocols import ArticleStoreProtocol

logger = structlog.get_logger(__name__)


class GetRecentNewsTool(BaseTool):
    """获取最近 N 小时内收集的新闻列表。"""

    def __init__(self, article_store: ArticleStoreProtocol):
        self._article_store = article_store

    @property
    def name(self) -> str:
        return "get_recent_news"

    @property
    def description(self) -> str:
        return (
            "获取最近 N 小时内收集的新闻文章列表。"
            "适用于用户想了解最新动态、今天有什么新闻等问题。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="hours",
                type="integer",
                description="查看最近多少小时内的新闻",
                required=False,
                default=24,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="最多返回多少条新闻",
                required=False,
                default=20,
            ),
        ]

    def _run(self, hours: int = 24, limit: int = 20, **kwargs: Any) -> str:
        """获取最近新闻并格式化为文本。"""
        articles = self._article_store.get_recent(hours=hours, limit=limit)

        if not articles:
            return f"最近 {hours} 小时内没有收集到新闻文章。"

        parts = []
        for i, article in enumerate(articles, 1):
            parts.append(
                f"{i}. 【{article.source}】{article.title}\n"
                f"   ID: {article.id}\n"
                f"   发布时间: {article.published_at}\n"
                f"   摘要: {article.summary or '无摘要'}\n"
                f"   URL: {article.url}"
            )

        return (
            f"最近 {hours} 小时内共有 {len(articles)} 条新闻:\n\n"
            + "\n\n".join(parts)
        )
