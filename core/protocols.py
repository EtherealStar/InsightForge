"""接口契约：Demo 和 Full 都实现这些 Protocol"""
from typing import Any, Protocol, Iterator, runtime_checkable

from models.article import Article
from models.agent_session import AgentSession, ResearchTodo, SessionStatus
from models.chunk import Chunk, ParentChunk
from models.search import SearchResult, ChunkSearchResult


@runtime_checkable
class ArticleStoreProtocol(Protocol):
    """文章元数据存储（PostgreSQL）"""

    def save_articles(self, articles: list[Article]) -> int: ...

    def get_unembedded(self, limit: int = 100) -> list[Article]: ...

    def mark_embedded(self, article_ids: list[int]) -> None: ...

    def search_by_keyword(
        self, keyword: str, limit: int = 20
    ) -> list[Article]: ...

    def get_recent(self, hours: int = 24, limit: int = 50) -> list[Article]: ...

    def get_stats(self) -> dict: ...

    def cleanup_old_articles(self, retention_days: int = 90) -> int: ...

    # 扩展方法：已被当前 Router/Service/Tool 稳定依赖
    def delete_articles(self, article_ids: list[int]) -> int: ...

    def get_pending_summary(self, limit: int = 100) -> list[Article]: ...

    def mark_pending_summary(self, article_ids: list[int]) -> None: ...

    def mark_summarized(self, article_ids: list[int]) -> None: ...

    def update_summary(
        self, article_id: int, summary: str, tags: list[str]
    ) -> None: ...

    def get_article_by_id(self, article_id: int) -> Article | None: ...

    def get_articles(
        self,
        page: int = 1,
        page_size: int = 20,
        source: str | None = None,
        language: str | None = None,
        keyword: str | None = None,
    ) -> list[Article]: ...

    def count_articles(
        self,
        source: str | None = None,
        language: str | None = None,
        keyword: str | None = None,
    ) -> int: ...

    # --- 父 chunk 存储方法 ---

    def save_parent_chunks(self, parent_chunks: list[ParentChunk]) -> int:
        """批量保存父 chunks 到数据库 (upsert)。返回写入数量。"""
        ...

    def get_parent_chunks_by_ids(
        self, parent_chunk_ids: list[str]
    ) -> list[ParentChunk]:
        """根据 parent_chunk_id 列表批量获取父 chunks。"""
        ...

    def delete_parent_chunks_by_article_ids(
        self, article_ids: list[int]
    ) -> int:
        """删除指定文章 ID 关联的所有父 chunks。返回删除数量。"""
        ...

    # --- 全文搜索方法 ---

    def search_parent_chunks_by_keyword(
        self, query: str, top_k: int = 20
    ) -> list[tuple]:
        """在父 chunks 上执行全文搜索。

        Args:
            query: 已分词的查询文本（空格分隔）。
            top_k: 返回结果数量。

        Returns:
            [(ParentChunk, ts_rank_score), ...] 按分数降序。
        """
        ...

    def backfill_search_vectors(self) -> int:
        """为缺失 search_vector 的已有父 chunks 回填全文索引。返回更新数量。"""
        ...


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """向量存储（pgvector）— chunk 级别存储与检索"""

    def add_chunks(
        self, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> int:
        """将子 chunks 及其向量写入向量数据库。返回写入数量。"""
        ...

    def search_chunks(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[ChunkSearchResult]:
        """搜索子 chunks，返回匹配结果列表（parent_chunk 字段为 None）。"""
        ...

    def delete_by_article_ids(self, article_ids: list[int]) -> None:
        """删除指定文章 ID 关联的所有 chunk 向量。"""
        ...


@runtime_checkable
class LLMClientProtocol(Protocol):
    """LLM 调用（OpenAI 兼容 / GPT / Gemini / Claude）"""

    def generate(self, system_prompt: str, user_message: str) -> str: ...

    def generate_stream(
        self, system_prompt: str, user_message: str
    ) -> Iterator[str]: ...

    def generate_with_history(self, messages: list[dict]) -> str:
        """多轮对话：接受完整消息历史生成回复。

        Args:
            messages: OpenAI 格式消息列表，每条消息包含:
                - role: "system" | "user" | "assistant"
                - content: 消息内容

        Returns:
            LLM 生成的回复文本。
        """
        ...

    def generate_with_history_stream(
        self, messages: list[dict]
    ) -> Iterator[str]:
        """多轮对话流式版本。"""
        ...


@runtime_checkable
class EmbeddingClientProtocol(Protocol):
    """Embedding 调用（OpenAI 格式自定义 API）"""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class RerankClientProtocol(Protocol):
    """Rerank 重排序（Jina / Cohere / SiliconFlow 等 Cross-Encoder API）"""

    def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[dict]:
        """对文档列表按与 query 的相关性重新排序。

        Args:
            query: 查询文本。
            documents: 待排序的文档文本列表。
            top_n: 返回前 N 条结果，None 则返回全部。

        Returns:
            [{"index": int, "relevance_score": float}, ...]
            按 relevance_score 降序排列。
        """
        ...


@runtime_checkable
class AgentSessionStoreProtocol(Protocol):
    """Agent 会话存储（PostgreSQL + Redis 缓存）。"""

    def create_session(
        self,
        topic: str,
        plan: dict[str, Any] | str | None,
        todos: list[ResearchTodo],
        messages: list[dict[str, Any]] | None = None,
    ) -> AgentSession: ...

    def get_session(self, session_id: str) -> AgentSession | None: ...

    def save_plan(
        self,
        session_id: str,
        plan: dict[str, Any] | str,
        todos: list[ResearchTodo],
    ) -> AgentSession: ...

    def update_status(
        self,
        session_id: str,
        status: SessionStatus,
        error: str | None = None,
    ) -> AgentSession: ...

    def append_event(self, session_id: str, event: dict[str, Any]) -> None: ...

    def update_todos(
        self,
        session_id: str,
        todos: list[ResearchTodo],
    ) -> AgentSession: ...

    def complete_session(
        self,
        session_id: str,
        final_answer: str,
        report_filename: str | None,
    ) -> AgentSession: ...

    def fail_session(self, session_id: str, error: str) -> AgentSession: ...

    def flush_session(self, session_id: str) -> None: ...
