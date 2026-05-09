"""内置工具：生成新闻简报

调用 BriefService 生成新闻简报并返回内容预览。
"""

import structlog
from typing import Any

from agent.tools.base import BaseTool, ToolParameter
from core.protocols import ArticleStoreProtocol, LLMClientProtocol

logger = structlog.get_logger(__name__)


class GenerateBriefTool(BaseTool):
    """生成新闻简报。"""

    def __init__(
        self,
        article_store: ArticleStoreProtocol,
        llm_client: LLMClientProtocol,
        output_path: str,
    ):
        self._article_store = article_store
        self._llm_client = llm_client
        self._output_path = output_path

    @property
    def name(self) -> str:
        return "generate_brief"

    @property
    def description(self) -> str:
        return (
            "基于最近收集的新闻文章生成一份新闻简报。"
            "适用于用户要求生成简报、总结新闻等场景。"
            "注意：生成简报需要较长时间。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="hours",
                type="integer",
                description="使用最近多少小时内的新闻来生成简报",
                required=False,
                default=24,
            ),
        ]

    def _run(self, hours: int = 24, **kwargs: Any) -> str:
        """生成简报并返回预览文本。"""
        from services.brief_service import BriefService

        service = BriefService(
            article_store=self._article_store,
            llm_client=self._llm_client,
            output_path=self._output_path,
        )

        brief = service.generate(hours=hours)

        # 返回简报内容的前 2000 字符作为预览
        preview = brief.content_markdown
        if len(preview) > 2000:
            preview = preview[:2000] + "\n\n... (简报内容已截断，完整版本已保存到文件)"

        return (
            f"简报生成成功！包含 {brief.article_count} 篇文章的分析。\n\n"
            f"--- 简报预览 ---\n\n{preview}"
        )
