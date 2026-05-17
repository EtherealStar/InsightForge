"""根据配置创建具体实现实例"""
from core.config import AppConfig
from core.protocols import (
    ArticleStoreProtocol,
    AgentSessionStoreProtocol,
    MemoryStoreProtocol,
    VectorStoreProtocol,
    LLMClientProtocol,
    EmbeddingClientProtocol,
)


def create_article_store(config: AppConfig) -> ArticleStoreProtocol:
    from infrastructure.postgres_article_store import PostgresArticleStore

    return PostgresArticleStore(dsn=config.pg_dsn)


def create_agent_session_store(config: AppConfig) -> AgentSessionStoreProtocol:
    from infrastructure.agent_session_store import AgentSessionStore

    return AgentSessionStore(
        dsn=config.pg_dsn,
        redis_url=config.celery_broker_url,
    )


def create_memory_store(config: AppConfig) -> MemoryStoreProtocol:
    from infrastructure.memory_store import MemoryStore

    return MemoryStore(dsn=config.pg_dsn)


def create_vector_store(config: AppConfig) -> VectorStoreProtocol:
    from infrastructure.pgvector_store import PgVectorStore

    return PgVectorStore(
        dsn=config.pg_dsn,
        vector_size=config.embedding_vector_size,
    )


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


def create_rerank_client(config: AppConfig):
    """创建 Rerank 重排序客户端。未启用或缺少配置时返回 None。"""
    import structlog

    _logger = structlog.get_logger(__name__)

    if not config.rerank_enabled:
        return None
    if not config.rerank_api_key or not config.rerank_base_url:
        _logger.warning("Rerank 已启用但缺少 API Key 或 Base URL，跳过创建")
        return None

    from infrastructure.rerank_client import OpenAICompatibleRerankClient

    return OpenAICompatibleRerankClient(
        api_key=config.rerank_api_key,
        base_url=config.rerank_base_url,
        model=config.rerank_model,
    )


def create_summary_llm_client(config: AppConfig) -> LLMClientProtocol:
    """创建摘要专用 LLM 客户端。复用主 LLM 或使用独立配置。"""
    if config.summary_use_same_llm:
        return create_llm_client(config)

    from infrastructure.llm_client import (
        OpenAICompatibleClient,
        OpenAIClient,
        GeminiClient,
        AnthropicClient,
    )

    provider = config.summary_llm_provider or config.llm_provider
    match provider:
        case "openai_compatible":
            return OpenAICompatibleClient(
                api_key=config.summary_llm_api_key,
                base_url=config.summary_llm_base_url,
                model=config.summary_llm_model,
            )
        case "openai":
            return OpenAIClient(
                api_key=config.summary_llm_api_key,
                model=config.summary_llm_model or "gpt-4o-mini",
            )
        case "gemini":
            return GeminiClient(
                api_key=config.summary_llm_api_key,
                model=config.summary_llm_model or "gemini-2.0-flash",
            )
        case "anthropic":
            return AnthropicClient(
                api_key=config.summary_llm_api_key,
                model=config.summary_llm_model or "claude-sonnet-4-20250514",
            )

    raise ValueError(f"未知的摘要 LLM provider: {provider}")


def create_chunking_service(config: AppConfig):
    """创建分块服务。"""
    from infrastructure.chunking_service import ChunkingService

    return ChunkingService(
        max_child_tokens=config.chunk_max_child_tokens,
        target_parent_tokens=config.chunk_target_parent_tokens,
        overlap_tokens=config.chunk_overlap_tokens,
    )


# ======================================================================
# Service 层工厂函数
# ======================================================================


def create_webhook_service():
    """创建 Webhook 推送服务。"""
    from services.webhook_service import WebhookService

    return WebhookService()


def create_deep_research_service(output_dir: str | None = None):
    """创建研究报告持久化服务。"""
    import os
    from services.deep_research_service import DeepResearchService

    _dir = output_dir or os.path.join("output", "research")
    return DeepResearchService(output_dir=_dir)


def create_query_service(config: AppConfig, mgr):
    """创建 QueryService，组装所有依赖。

    Args:
        config: 当前应用配置。
        mgr: ConfigManager 实例，用于获取缓存的基础设施组件。
    """
    from services.query_service import QueryService
    from services.memory_service import MemoryService

    memory_service = None
    if mgr.memory_store and mgr.agent_session_store:
        memory_service = MemoryService(
            mgr.memory_store,
            mgr.agent_session_store,
            mgr.llm_client,
        )

    return QueryService(
        mgr.article_store,
        mgr.vector_store,
        mgr.llm_client,
        mgr.embedding_client,
        session_store=mgr.agent_session_store,
        memory_service=memory_service,
    )


def create_memory_service(mgr):
    """创建 MemoryService。

    Args:
        mgr: ConfigManager 实例，用于获取缓存的基础设施组件。
    """
    from services.memory_service import MemoryService

    return MemoryService(
        mgr.memory_store,
        mgr.agent_session_store,
        mgr.llm_client,
    )
