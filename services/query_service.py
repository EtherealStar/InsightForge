"""编排 检索 → 分析 的查询流程"""
import logging
from typing import Iterator

from core.protocols import (
    ArticleStoreProtocol,
    VectorStoreProtocol,
    LLMClientProtocol,
    EmbeddingClientProtocol,
)
from models.article import Article
from models.search import SearchQuery, SearchResult

logger = logging.getLogger(__name__)

QA_SYSTEM_PROMPT = """你是一位专业的新闻分析师。请基于以下提供的新闻文章内容回答用户的问题。

规则：
1. 只基于提供的文章内容回答，不要编造信息
2. 如果文章中没有相关信息，请如实说明
3. 回答要客观、简洁、有洞察力
4. 回答末尾列出参考来源（标题 + URL）"""


class QueryService:
    """编排 检索 → 分析 的查询流程"""

    def __init__(
        self,
        article_store: ArticleStoreProtocol,
        vector_store: VectorStoreProtocol,
        llm_client: LLMClientProtocol,
        embedding_client: EmbeddingClientProtocol,
    ):
        self.article_store = article_store
        self.vector_store = vector_store
        self.llm_client = llm_client
        self.embedding_client = embedding_client

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """
        语义检索（Demo 阶段简化，只用语义检索）：
        1. query.text → Embedding → vector_store.search(top_k)
        2. 返回前 top_k 条
        """
        # 生成查询向量
        query_embeddings = self.embedding_client.embed([query.text])
        if not query_embeddings:
            logger.warning("查询向量生成失败，回退到关键词搜索")
            articles = self.article_store.search_by_keyword(
                query.text, query.top_k
            )
            return [
                SearchResult(article=a, relevance_score=0.5, match_type="keyword")
                for a in articles
            ]

        # 构建过滤器
        filters = {}
        if query.sources:
            filters["source"] = query.sources[0]  # ChromaDB 单值过滤
        if query.language:
            filters["language"] = query.language.value

        results = self.vector_store.search(
            query_embedding=query_embeddings[0],
            top_k=query.top_k,
            filters=filters if filters else None,
        )

        logger.info(f"检索完成: '{query.text}' → {len(results)} 条结果")
        return results

    def answer(self, question: str, top_k: int = 10) -> str:
        """
        完整 RAG 流程：检索 + LLM 生成回答
        """
        # 1. 检索相关文章
        results = self.search(SearchQuery(text=question, top_k=top_k))

        if not results:
            return "未找到相关新闻文章。请尝试其他关键词或等待更多新闻被收录。"

        # 2. 构建 context
        context = self._build_context(results)

        # 3. LLM 生成回答
        user_message = f"## 参考文章\n\n{context}\n\n## 用户问题\n\n{question}"
        answer = self.llm_client.generate(QA_SYSTEM_PROMPT, user_message)
        return answer

    def answer_stream(
        self, question: str, top_k: int = 10
    ) -> Iterator[str]:
        """同 answer，但使用 streaming"""
        # 1. 检索相关文章
        results = self.search(SearchQuery(text=question, top_k=top_k))

        if not results:
            yield "未找到相关新闻文章。请尝试其他关键词或等待更多新闻被收录。"
            return

        # 2. 构建 context
        context = self._build_context(results)

        # 3. LLM 流式回答
        user_message = f"## 参考文章\n\n{context}\n\n## 用户问题\n\n{question}"
        for chunk in self.llm_client.generate_stream(
            QA_SYSTEM_PROMPT, user_message
        ):
            yield chunk

    @staticmethod
    def _build_context(results: list[SearchResult]) -> str:
        """将检索结果格式化为 LLM context"""
        context_parts = []
        for i, result in enumerate(results, 1):
            context_parts.append(
                f"### 文章 {i}（相关度: {result.relevance_score:.2f}）\n"
                f"{result.article.to_context_str()}"
            )
        return "\n\n".join(context_parts)
