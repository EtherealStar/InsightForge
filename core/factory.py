"""根据配置创建具体实现实例（Demo 阶段只支持 SQLite + ChromaDB）"""
from core.config import AppConfig
from core.protocols import (
    ArticleStoreProtocol,
    VectorStoreProtocol,
    LLMClientProtocol,
    EmbeddingClientProtocol,
)


def create_article_store(config: AppConfig) -> ArticleStoreProtocol:
    from infrastructure.article_store import SQLiteArticleStore

    return SQLiteArticleStore(config.db_path)


def create_vector_store(config: AppConfig) -> VectorStoreProtocol:
    from infrastructure.vector_store import ChromaVectorStore

    return ChromaVectorStore(config.chroma_path)


def create_llm_client(config: AppConfig) -> LLMClientProtocol:
    from infrastructure.llm_client import (
        OpenAICompatibleClient,
        OpenAIClient,
        GeminiClient,
        AnthropicClient,
    )

    match config.llm_provider:
        case "openai_compatible":
            return OpenAICompatibleClient(
                api_key=config.llm_api_key,
                base_url=config.llm_base_url,
                model=config.llm_model,
            )
        case "openai":
            return OpenAIClient(
                api_key=config.openai_api_key,
                model=config.llm_model or "gpt-4o-mini",
            )
        case "gemini":
            return GeminiClient(
                api_key=config.google_api_key,
                model=config.llm_model or "gemini-2.0-flash",
            )
        case "anthropic":
            return AnthropicClient(
                api_key=config.anthropic_api_key,
                model=config.llm_model or "claude-sonnet-4-20250514",
            )

    raise ValueError(f"未知的 LLM provider: {config.llm_provider}")


def create_embedding_client(config: AppConfig) -> EmbeddingClientProtocol:
    from infrastructure.embedding_client import OpenAICompatibleEmbeddingClient

    return OpenAICompatibleEmbeddingClient(
        api_key=config.embedding_api_key,
        base_url=config.embedding_base_url,
        model=config.embedding_model,
    )
