"""内置工具：阅读文章全文

通过文章数据库 ID 获取完整的 Markdown 正文内容，
用于深度研究模式下 Agent 深入阅读单篇文章。
"""

import structlog
from typing import Any

from agent.tools.base import BaseTool, ToolParameter
from core.protocols import ArticleStoreProtocol

logger = structlog.get_logger(__name__)

# 防止超长内容导致 LLM token 溢出
_MAX_CONTENT_CHARS = 8000


class ReadArticleTool(BaseTool):
    """通过文章 ID 读取完整 Markdown 正文内容。

    与 query_knowledge_base / get_recent_news 不同：
    - 那些工具返回文章列表 + 摘要（用于概览）
    - 本工具返回单篇文章的完整正文（用于深度阅读）

    适用场景：
    - 深度研究时 Agent 选定感兴趣的文章后，需要阅读全文
    - 用户明确要求查看某篇文章内容
    """

    def __init__(self, article_store: ArticleStoreProtocol):
        self._article_store = article_store

    @property
    def name(self) -> str:
        return "read_article"

    @property
    def description(self) -> str:
        return (
            "通过文章 ID 读取一篇新闻文章的完整 Markdown 正文。"
            "适用于深度研究时需要仔细阅读某篇文章的全文内容。"
            "请先通过 query_knowledge_base 或 get_recent_news 获取文章列表和 ID，"
            "再使用本工具阅读感兴趣的文章全文。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="article_id",
                type="integer",
                description="文章的数据库 ID（从 query_knowledge_base 或 get_recent_news 结果中获取）",
            ),
        ]

    def _run(self, article_id: int, **kwargs: Any) -> str:
        """读取文章全文并格式化返回。"""
        article = self._article_store.get_article_by_id(article_id)

        if article is None:
            return f"未找到 ID 为 {article_id} 的文章。请确认文章 ID 是否正确。"

        # 构建详细的文章信息
        parts = [
            f"# {article.title}",
            "",
            f"- **来源**: {article.source}",
            f"- **发布时间**: {article.published_at or '未知'}",
            f"- **URL**: {article.url}",
        ]
        if article.author:
            parts.append(f"- **作者**: {article.author}")
        parts.append("")

        # 正文内容（优先 Markdown content，回退到 summary）
        content = article.content or article.summary or "（无正文内容）"
        if len(content) > _MAX_CONTENT_CHARS:
            content = content[:_MAX_CONTENT_CHARS] + "\n\n... (正文内容已截断)"

        parts.append("## 正文")
        parts.append("")
        parts.append(content)

        return "\n".join(parts)
