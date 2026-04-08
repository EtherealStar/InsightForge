"""接口契约：Demo 和 Full 都实现这些 Protocol"""
from typing import Protocol, Iterator, runtime_checkable

from models.article import Article
from models.search import SearchResult


@runtime_checkable
class ArticleStoreProtocol(Protocol):
    """文章元数据存储（SQLite / PostgreSQL）"""

    def save_articles(self, articles: list[Article]) -> int: ...

    def get_unembedded(self, limit: int = 100) -> list[Article]: ...

    def mark_embedded(self, article_ids: list[int]) -> None: ...

    def search_by_keyword(
        self, keyword: str, limit: int = 20
    ) -> list[Article]: ...

    def get_recent(self, hours: int = 24, limit: int = 50) -> list[Article]: ...

    def get_stats(self) -> dict: ...

    def cleanup_old_articles(self, retention_days: int = 90) -> int: ...


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """向量存储（ChromaDB / Qdrant）"""

    def add_articles(
        self, articles: list[Article], embeddings: list[list[float]]
    ) -> int: ...

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]: ...


@runtime_checkable
class LLMClientProtocol(Protocol):
    """LLM 调用（OpenAI 兼容 / GPT / Gemini / Claude）"""

    def generate(self, system_prompt: str, user_message: str) -> str: ...

    def generate_stream(
        self, system_prompt: str, user_message: str
    ) -> Iterator[str]: ...


@runtime_checkable
class EmbeddingClientProtocol(Protocol):
    """Embedding 调用（OpenAI 格式自定义 API）"""

    def embed(self, texts: list[str]) -> list[list[float]]: ...
