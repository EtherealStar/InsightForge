"""AI 摘要 + 自动打标签服务

将新闻批量发送给 LLM，生成中文摘要和分类标签。
- 每批默认 5 条（可配置）
- 单批最多重试 3 次
- 3 次失败后标记为 summarized（无摘要），让文章可继续流转
"""
from __future__ import annotations

import json
import structlog
from typing import TYPE_CHECKING

from core.protocols import ArticleStoreProtocol, LLMClientProtocol

if TYPE_CHECKING:
    from models.article import Article

logger = structlog.get_logger(__name__)

# ======================================================================
# Prompt 模板
# ======================================================================

_SYSTEM_PROMPT = """你是一个专业的新闻摘要助手。你的任务是对多条新闻分别生成简洁的中文摘要和分类标签。

要求：
1. 每条新闻生成一段 50-150 字的中文摘要，准确概括核心信息
2. 每条新闻分配 2-5 个分类标签
3. 推荐标签类别：政治、经济、科技、军事、社会、文化、体育、健康、环境、国际、法律、教育、能源、金融、AI
4. 可以在推荐标签之外创建更精确的标签
5. 所有摘要和标签统一使用中文

请严格按以下 JSON 数组格式输出，不要添加任何额外文字或 markdown 标记：
[
  {
    "index": 1,
    "summary": "摘要文本...",
    "tags": ["标签1", "标签2"]
  }
]"""


def _build_user_message(articles: list[Article]) -> str:
    """构建包含多条新闻的用户消息。"""
    parts = [f"请对以下 {len(articles)} 条新闻分别生成摘要和标签：\n"]
    for i, article in enumerate(articles, 1):
        # 限制正文长度，避免 token 超限
        content = article.content or ""
        if len(content) > 800:
            content = content[:800] + "..."
        source_info = f"来源: {article.source}" if article.source else ""
        parts.append(
            f"---\n"
            f"【新闻 {i}】\n"
            f"标题: {article.title}\n"
            f"{source_info}\n"
            f"正文: {content}\n"
        )
    return "\n".join(parts)


def _parse_llm_response(response: str, expected_count: int) -> list[dict] | None:
    """
    解析 LLM 返回的 JSON 数组。

    Returns:
        解析成功返回 list[dict]，每个 dict 包含 index, summary, tags。
        解析失败返回 None。
    """
    # 尝试提取 JSON 部分（LLM 可能包裹在 ```json ... ``` 中）
    text = response.strip()
    if "```" in text:
        # 提取代码块内容
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # 尝试找到第一个 [ 和最后一个 ]
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                result = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                logger.warning("JSON 解析失败，无法提取有效数组")
                return None
        else:
            logger.warning("LLM 响应中未找到 JSON 数组")
            return None

    if not isinstance(result, list):
        logger.warning(f"LLM 响应不是数组: {type(result)}")
        return None

    if len(result) != expected_count:
        logger.warning(
            f"LLM 返回 {len(result)} 条结果，期望 {expected_count} 条"
        )
        # 仍然接受，按 index 匹配

    # 校验每条结果的格式
    valid = []
    for item in result:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary", "")
        tags = item.get("tags", [])
        index = item.get("index", len(valid) + 1)
        if not isinstance(tags, list):
            tags = []
        tags = [str(t) for t in tags if t]
        valid.append({"index": index, "summary": str(summary), "tags": tags})

    return valid if valid else None


# ======================================================================
# Service
# ======================================================================


class SummaryService:
    """AI 摘要 + 打标签服务"""

    MAX_RETRIES = 3

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        article_store: ArticleStoreProtocol,
        batch_size: int = 5,
    ):
        self.llm_client = llm_client
        self.article_store = article_store
        self.batch_size = batch_size

    # ------------------------------------------------------------------
    # 核心：处理一批文章
    # ------------------------------------------------------------------

    def _process_batch(self, articles: list[Article]) -> dict:
        """
        对一批文章执行 AI 摘要 + 打标签。

        Returns:
            {"success": int, "failed": int, "success_ids": list, "failed_ids": list}
        """
        result = {"success": 0, "failed": 0, "success_ids": [], "failed_ids": []}

        if not articles:
            return result

        user_message = _build_user_message(articles)
        parsed = None

        # 最多重试 MAX_RETRIES 次
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info(
                    f"[Summary] 批量摘要请求 (第 {attempt} 次，{len(articles)} 篇)"
                )
                response = self.llm_client.generate(_SYSTEM_PROMPT, user_message)
                parsed = _parse_llm_response(response, len(articles))
                if parsed:
                    break
                logger.warning(f"[Summary] 第 {attempt} 次解析失败，准备重试")
            except Exception as e:
                logger.error(f"[Summary] 第 {attempt} 次 LLM 调用失败: {e}")

        if parsed:
            # 按 index 匹配文章
            index_map = {item["index"]: item for item in parsed}
            for i, article in enumerate(articles, 1):
                item = index_map.get(i)
                if item and article.id is not None:
                    try:
                        self.article_store.update_summary(
                            article.id, item["summary"], item["tags"]
                        )
                        self.article_store.mark_summarized([article.id])
                        result["success"] += 1
                        result["success_ids"].append(article.id)
                    except Exception as e:
                        logger.error(
                            f"[Summary] 更新文章 {article.id} 摘要失败: {e}"
                        )
                        result["failed"] += 1
                        result["failed_ids"].append(article.id)
                else:
                    # 该文章没有对应的结果，跳过（保持 pending_summary）
                    if article.id is not None:
                        result["failed"] += 1
                        result["failed_ids"].append(article.id)
        else:
            # 所有重试失败 — 直接标记为 summarized（无摘要），让文章可继续流转
            logger.warning(
                f"[Summary] {len(articles)} 篇文章 AI 摘要全部失败，"
                f"标记为 summarized 跳过"
            )
            failed_ids = [a.id for a in articles if a.id is not None]
            self.article_store.mark_summarized(failed_ids)
            result["failed"] = len(articles)
            result["failed_ids"] = failed_ids

        return result

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def summarize_pending(self) -> dict:
        """
        处理所有 pending_summary 状态的文章。
        按 batch_size 分批发送给 AI。

        Returns:
            {"success": int, "failed": int, "total": int}
        """
        pending = self.article_store.get_pending_summary()
        if not pending:
            logger.info("[Summary] 无待摘要文章")
            return {"success": 0, "failed": 0, "total": 0}

        logger.info(f"[Summary] 开始处理 {len(pending)} 篇待摘要文章")
        total_success = 0
        total_failed = 0

        # 分批处理
        for i in range(0, len(pending), self.batch_size):
            batch = pending[i : i + self.batch_size]
            batch_result = self._process_batch(batch)
            total_success += batch_result["success"]
            total_failed += batch_result["failed"]

        logger.info(
            f"[Summary] 摘要完成: 成功 {total_success}，失败 {total_failed}"
        )
        return {
            "success": total_success,
            "failed": total_failed,
            "total": len(pending),
        }

    def resummarize_articles(self, article_ids: list[int]) -> dict:
        """
        对指定文章重新执行 AI 摘要（前端手动触发）。
        先标记为 pending_summary，再执行摘要。

        Returns:
            {"success": int, "failed": int, "total": int}
        """
        if not article_ids:
            return {"success": 0, "failed": 0, "total": 0}

        # 先标记为待摘要
        self.article_store.mark_pending_summary(article_ids)

        # 获取这些文章
        articles = []
        for aid in article_ids:
            article = self.article_store.get_article_by_id(aid)
            if article:
                articles.append(article)

        if not articles:
            return {"success": 0, "failed": 0, "total": 0}

        logger.info(f"[Summary] 重新摘要 {len(articles)} 篇文章")
        total_success = 0
        total_failed = 0

        for i in range(0, len(articles), self.batch_size):
            batch = articles[i : i + self.batch_size]
            batch_result = self._process_batch(batch)
            total_success += batch_result["success"]
            total_failed += batch_result["failed"]

        return {
            "success": total_success,
            "failed": total_failed,
            "total": len(articles),
        }
