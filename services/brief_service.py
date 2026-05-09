"""日报生成服务"""
import structlog
from datetime import datetime

from core.protocols import ArticleStoreProtocol, LLMClientProtocol
from models.brief import DailyBrief

logger = structlog.get_logger(__name__)

BRIEF_SYSTEM_PROMPT = """你是一位资深新闻编辑。请根据以下新闻文章生成一份中文每日简报。

简报格式要求：
# 每日新闻简报 — {日期}
## 📌 今日要闻
（3-5条最重要的新闻，每条含标题、来源、一句话摘要）
## 🔍 深度分析
（选取 1-2 个值得关注的趋势或事件，200字以内的分析）
## ⚡ 快讯
（其余新闻标题列表 + 来源）

要求：客观、简洁、有洞察力。"""

# 控制 context 上限（约 50 篇文章）
_MAX_CONTEXT_CHARS = 80000


class BriefService:
    """日报生成服务"""

    def __init__(
        self,
        article_store: ArticleStoreProtocol,
        llm_client: LLMClientProtocol,
        output_path: str,
    ):
        self.article_store = article_store
        self.llm_client = llm_client
        self.output_path = output_path

    def generate(self, hours: int = 24) -> DailyBrief:
        """
        1. 获取最近 hours 小时内的文章
        2. 格式化为 context
        3. 控制 context 总长度
        4. LLM 生成日报
        5. 保存文件
        """
        # 1. 获取文章
        articles = self.article_store.get_recent(hours=hours, limit=50)
        if not articles:
            logger.warning("无文章可用于生成日报")
            content = (
                f"# 每日新闻简报 — {datetime.now().strftime('%Y-%m-%d')}\n\n"
                "暂无新闻数据。请检查新闻抓取管道是否正常运行。"
            )
            brief = DailyBrief(
                date=datetime.now(),
                content_markdown=content,
                article_count=0,
            )
            brief.save_to_file(self.output_path)
            return brief

        # 2. 格式化 context
        context_parts = []
        total_chars = 0
        for article in articles:
            part = article.to_context_str()
            if total_chars + len(part) > _MAX_CONTEXT_CHARS:
                break
            context_parts.append(part)
            total_chars += len(part)

        context = "\n\n---\n\n".join(context_parts)

        # 3. LLM 生成
        today = datetime.now().strftime("%Y-%m-%d")
        prompt = BRIEF_SYSTEM_PROMPT.replace("{日期}", today)
        user_message = f"以下是最近 {hours} 小时内收集的 {len(context_parts)} 篇新闻：\n\n{context}"

        logger.info(
            f"生成日报: {len(context_parts)} 篇文章, "
            f"context {total_chars} 字符"
        )
        content_markdown = self.llm_client.generate(prompt, user_message)

        # 4. 构建 DailyBrief 并保存
        brief = DailyBrief(
            date=datetime.now(),
            content_markdown=content_markdown,
            article_count=len(context_parts),
        )
        file_path = brief.save_to_file(self.output_path)
        logger.info(f"日报已保存: {file_path}")

        return brief
