"""根据配置创建具体实现实例"""
from core.config import AppConfig
from core.protocols import (
    AgentSessionStoreProtocol,
    AuthStoreProtocol,
    CompetitorStoreProtocol,
    ConfigAuditStoreProtocol,
    DocumentStoreProtocol,
    ArchiveExtractorProtocol,
    DocumentParserProtocol,
    FileBlobStoreProtocol,
    FileTypeDetectorProtocol,
    InsightStoreProtocol,
    IntelStoreProtocol,
    MemoryStoreProtocol,
    RedisStateStoreProtocol,
    ReportStoreProtocol,
    JudgeClientProtocol,
    StructuredExtractionClientProtocol,
    TaskRunStoreProtocol,
    UploadStoreProtocol,
    VectorIndexProtocol,
    LLMClientProtocol,
    EmbeddingClientProtocol,
)


def create_competitor_store(config: AppConfig) -> CompetitorStoreProtocol:
    from infrastructure.competitor_store import PostgresCompetitorStore

    return PostgresCompetitorStore(dsn=config.pg_dsn)


def create_report_store(config: AppConfig) -> ReportStoreProtocol:
    from infrastructure.report_store import PostgresReportStore

    return PostgresReportStore(dsn=config.pg_dsn)


def create_auth_store(config: AppConfig) -> AuthStoreProtocol:
    from infrastructure.auth_store import PostgresAuthStore

    return PostgresAuthStore(dsn=config.pg_dsn)


def create_config_audit_store(config: AppConfig) -> ConfigAuditStoreProtocol:
    from infrastructure.config_audit_store import PostgresConfigAuditStore

    return PostgresConfigAuditStore(dsn=config.pg_dsn)


def create_intel_store(config: AppConfig) -> IntelStoreProtocol:
    from infrastructure.intel_store import PostgresIntelStore

    return PostgresIntelStore(dsn=config.pg_dsn)


def create_insight_store(config: AppConfig) -> InsightStoreProtocol:
    from infrastructure.insight_store import PostgresInsightStore

    return PostgresInsightStore(dsn=config.pg_dsn)


def create_agent_session_store(config: AppConfig) -> AgentSessionStoreProtocol:
    from infrastructure.agent_session_store import AgentSessionStore

    return AgentSessionStore(
        dsn=config.pg_dsn,
        redis_url=config.celery_broker_url,
    )


def create_memory_store(config: AppConfig) -> MemoryStoreProtocol:
    from infrastructure.memory_store import MemoryStore

    return MemoryStore(dsn=config.pg_dsn)


def create_task_run_store(config: AppConfig) -> TaskRunStoreProtocol:
    from infrastructure.task_run_store import PostgresTaskRunStore

    return PostgresTaskRunStore(dsn=config.pg_dsn)


def create_upload_store(config: AppConfig) -> UploadStoreProtocol:
    from infrastructure.upload_store import PostgresUploadStore

    return PostgresUploadStore(dsn=config.pg_dsn)


def create_redis_state_store(config: AppConfig) -> RedisStateStoreProtocol:
    from infrastructure.redis.state_store import RedisStateStore

    return RedisStateStore(redis_url=config.celery_broker_url)


def create_file_type_detector(config: AppConfig) -> FileTypeDetectorProtocol:
    from infrastructure.files.type_detector import FileTypeDetector

    return FileTypeDetector(allowed_extensions=config.upload_allowed_extensions)


def create_file_blob_store(config: AppConfig) -> FileBlobStoreProtocol:
    from infrastructure.files.blob_store import LocalFileBlobStore
    from infrastructure.files.type_detector import FileTypeDetector

    detector = FileTypeDetector(allowed_extensions=config.upload_allowed_extensions)
    return LocalFileBlobStore(
        root=config.upload_storage_root,
        max_file_size_bytes=config.upload_max_file_size_mb * 1024 * 1024,
        detector=detector,
    )


def create_archive_extractor(config: AppConfig) -> ArchiveExtractorProtocol:
    from infrastructure.files.archive_extractor import ArchiveExtractor
    from infrastructure.files.type_detector import FileTypeDetector

    detector = FileTypeDetector(allowed_extensions=config.upload_allowed_extensions)
    return ArchiveExtractor(detector=detector)


def create_document_parser(config: AppConfig) -> DocumentParserProtocol:
    from infrastructure.files.type_detector import FileTypeDetector
    from infrastructure.parsers.document_parser import DocumentParser

    detector = FileTypeDetector(allowed_extensions=config.upload_allowed_extensions)
    return DocumentParser(detector=detector)


def create_document_store(config: AppConfig) -> DocumentStoreProtocol:
    from infrastructure.document_store import PostgresDocumentStore

    return PostgresDocumentStore(dsn=config.pg_dsn)


def create_source_profile_store(config: AppConfig):
    from infrastructure.source_profile_store import PostgresSourceProfileStore
    return PostgresSourceProfileStore(dsn=config.pg_dsn)


def create_collection_run_store(config: AppConfig):
    from infrastructure.collection_store import PostgresCollectionRunStore
    return PostgresCollectionRunStore(config.pg_dsn)


def create_fetch_candidate_store(config: AppConfig):
    from infrastructure.collection_store import PostgresFetchCandidateStore
    return PostgresFetchCandidateStore(config.pg_dsn)


def create_fetch_artifact_store(config: AppConfig):
    from infrastructure.collection_store import PostgresFetchArtifactStore
    return PostgresFetchArtifactStore(config.pg_dsn)


def create_normalized_document_store(config: AppConfig):
    from infrastructure.collection_store import PostgresNormalizedDocumentStore
    return PostgresNormalizedDocumentStore(config.pg_dsn)


def create_fetch_blob_store(config: AppConfig):
    from infrastructure.fetch_blob_store import FileFetchBlobStore
    return FileFetchBlobStore(config.fetch_blob_path)


def create_source_rate_limiter(config: AppConfig, redis_state_store=None):
    from infrastructure.source_rate_limiter import ConservativeSourceRateLimiter
    return ConservativeSourceRateLimiter(redis_state_store)


def create_http_fetch_engine(config: AppConfig):
    from infrastructure.fetch_engines import HttpFetchEngine
    return HttpFetchEngine()


def create_browser_fetch_engine(config: AppConfig):
    from infrastructure.fetch_engines import BrowserFetchEngine
    return BrowserFetchEngine()


def create_normalization_service(config: AppConfig):
    from services.normalization_service import DeterministicNormalizationService
    return DeterministicNormalizationService()


def create_document_dedup_store(config: AppConfig):
    from infrastructure.document_dedup_store import PostgresDocumentDedupStore

    return PostgresDocumentDedupStore(dsn=config.pg_dsn)


def create_dedup_cache(config: AppConfig):
    from infrastructure.redis.dedup_cache import RedisDedupCache

    return RedisDedupCache(redis_url=config.celery_broker_url)


def create_document_clustering_service(config: AppConfig):
    from services.document_clustering_service import DocumentClusteringService

    return DocumentClusteringService(
        create_document_dedup_store(config),
        create_dedup_cache(config),
    )


def create_document_version_service(config: AppConfig):
    from services.document_version_service import DocumentVersionService

    return DocumentVersionService(create_document_dedup_store(config))


def create_dedup_maintenance_service(config: AppConfig):
    from services.dedup_maintenance_service import DedupMaintenanceService

    return DedupMaintenanceService(
        create_document_dedup_store(config),
        create_dedup_cache(config),
    )


def create_source_governance_service(config: AppConfig):
    from services.source_governance_service import SourceGovernanceService
    return SourceGovernanceService(create_source_profile_store(config))


def create_qdrant_vector_index(config: AppConfig) -> VectorIndexProtocol:
    from infrastructure.qdrant.vector_index import QdrantVectorIndex

    index = QdrantVectorIndex(
        url=config.qdrant_url,
        api_key=config.qdrant_api_key,
        collection_name=config.qdrant_documents_collection,
        vector_size=config.embedding_vector_size,
        distance=config.qdrant_distance,
    )
    index.ensure_collection()
    return index


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


def create_structured_extraction_client(
    config: AppConfig,
) -> StructuredExtractionClientProtocol:
    from infrastructure.structured_extraction_client import (
        AnthropicStructuredExtractionClient,
        GeminiStructuredExtractionClient,
        OpenAICompatibleStructuredExtractionClient,
        OpenAIStructuredExtractionClient,
    )

    match config.structured_extraction_provider:
        case "openai_compatible":
            return OpenAICompatibleStructuredExtractionClient(
                api_key=config.structured_extraction_api_key,
                base_url=config.structured_extraction_base_url,
                model=config.structured_extraction_model,
                max_tokens=config.structured_extraction_max_tokens,
                default_temperature=config.structured_extraction_temperature,
            )
        case "openai":
            return OpenAIStructuredExtractionClient(
                api_key=config.structured_extraction_api_key,
                model=config.structured_extraction_model or "gpt-4o-mini",
                max_tokens=config.structured_extraction_max_tokens,
                default_temperature=config.structured_extraction_temperature,
            )
        case "gemini":
            return GeminiStructuredExtractionClient(
                api_key=config.structured_extraction_api_key,
                model=config.structured_extraction_model or "gemini-2.0-flash",
                max_tokens=config.structured_extraction_max_tokens,
                default_temperature=config.structured_extraction_temperature,
            )
        case "anthropic":
            return AnthropicStructuredExtractionClient(
                api_key=config.structured_extraction_api_key,
                model=config.structured_extraction_model or "claude-sonnet-4-20250514",
                max_tokens=config.structured_extraction_max_tokens,
                default_temperature=config.structured_extraction_temperature,
            )

    raise ValueError(
        f"未知的结构化抽取 provider: {config.structured_extraction_provider}"
    )


def create_judge_client(config: AppConfig) -> JudgeClientProtocol:
    from infrastructure.judge_client import (
        AnthropicJudgeClient,
        GeminiJudgeClient,
        OpenAICompatibleJudgeClient,
        OpenAIJudgeClient,
    )

    match config.judge_provider:
        case "openai_compatible":
            return OpenAICompatibleJudgeClient(
                api_key=config.judge_api_key,
                base_url=config.judge_base_url,
                model=config.judge_model,
                max_tokens=config.judge_max_tokens,
                default_temperature=config.judge_temperature,
            )
        case "openai":
            return OpenAIJudgeClient(
                api_key=config.judge_api_key,
                model=config.judge_model or "gpt-4o-mini",
                max_tokens=config.judge_max_tokens,
                default_temperature=config.judge_temperature,
            )
        case "gemini":
            return GeminiJudgeClient(
                api_key=config.judge_api_key,
                model=config.judge_model or "gemini-2.0-flash",
                max_tokens=config.judge_max_tokens,
                default_temperature=config.judge_temperature,
            )
        case "anthropic":
            return AnthropicJudgeClient(
                api_key=config.judge_api_key,
                model=config.judge_model or "claude-sonnet-4-20250514",
                max_tokens=config.judge_max_tokens,
                default_temperature=config.judge_temperature,
            )

    raise ValueError(f"未知的 Judge provider: {config.judge_provider}")


def create_embedding_client(config: AppConfig) -> EmbeddingClientProtocol:
    from infrastructure.embedding_client import OpenAICompatibleEmbeddingClient

    return OpenAICompatibleEmbeddingClient(
        api_key=config.embedding_api_key,
        base_url=config.embedding_base_url,
        model=config.embedding_model,
        dimensions=config.embedding_vector_size,
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


def create_chunking_service(config: AppConfig):
    """创建分块服务。"""
    from infrastructure.chunking_service import ChunkingService

    return ChunkingService(
        max_child_tokens=config.chunk_max_child_tokens,
        target_parent_tokens=config.chunk_target_parent_tokens,
        overlap_tokens=config.chunk_overlap_tokens,
    )


def create_hybrid_search_service(config: AppConfig, mgr):
    """创建混合检索服务（向量 + 关键词 + RRF）。"""
    from infrastructure.keyword_search_service import KeywordSearchService
    from infrastructure.hybrid_search_service import HybridSearchService

    if (
        mgr.document_store is None
        or mgr.vector_index is None
        or mgr.embedding_client is None
    ):
        raise RuntimeError("混合检索服务依赖未就绪")

    keyword_search = KeywordSearchService(mgr.document_store)
    return HybridSearchService(
        vector_index=mgr.vector_index,
        embedding_client=mgr.embedding_client,
        document_store=mgr.document_store,
        keyword_search_service=keyword_search,
        rrf_k=config.hybrid_rrf_k,
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


def create_competitor_service(config: AppConfig, mgr):
    """创建竞品服务。"""
    from services.competitor_service import CompetitorService

    return CompetitorService(
        competitor_store=mgr.competitor_store,
        intel_store=mgr.intel_store,
        document_store=mgr.document_store,
    )


def create_intel_service(config: AppConfig, mgr):
    """创建结构化事实服务。"""
    from services.intel_service import IntelService

    return IntelService(
        intel_store=mgr.intel_store,
        document_store=mgr.document_store,
        competitor_store=mgr.competitor_store,
        structured_extraction_client=mgr.structured_extraction_client,
        redis_state_store=mgr.redis_state_store,
    )


def create_insight_service(config: AppConfig, mgr):
    """创建分析结论服务。"""
    from services.insight_service import InsightService

    return InsightService(
        insight_store=mgr.insight_store,
        intel_store=mgr.intel_store,
        competitor_store=mgr.competitor_store,
        document_store=mgr.document_store,
    )


def create_report_service(config: AppConfig, mgr):
    """创建受质量门禁治理的报告工作流服务。"""
    from services.report_service import ReportService
    from services.report_quality_service import ReportQualityService

    quality_service = ReportQualityService(
        report_store=mgr.report_store,
        competitor_store=mgr.competitor_store,
        judge_client=mgr.judge_client,
        min_score=config.report_quality_min_score,
        judge_temperature=config.judge_temperature,
    )

    return ReportService(
        competitor_store=mgr.competitor_store,
        intel_service=mgr.intel_service,
        insight_service=mgr.insight_service,
        llm_client=mgr.llm_client,
        report_store=mgr.report_store,
        quality_service=quality_service,
        auto_publish_enabled=config.report_quality_auto_publish,
    )


def create_web_search_service(config: AppConfig, mgr=None):
    """创建 WebSearchService。"""
    from services.web_search_service import WebSearchService

    return WebSearchService(
        tavily_api_key=config.tavily_api_key,
        newsapi_api_key=config.newsapi_api_key,
    )


def create_service_registry(config: AppConfig, mgr):
    """创建工具可用的服务白名单注册表。"""
    from services.service_registry import ServiceRegistry

    return ServiceRegistry(
        {
            "intel_service": mgr.intel_service,
            "insight_service": mgr.insight_service,
            "competitor_service": mgr.competitor_service,
            "report_service": mgr.report_service,
            "evidence_search_service": mgr.hybrid_search_service,
            "web_search_service": mgr.web_search_service,
        }
    )


def create_builtin_tool_definition_registry():
    """创建内置工具定义注册表。"""
    from agent.tools.builtin.definitions import create_builtin_tool_definition_registry

    return create_builtin_tool_definition_registry()


def create_builtin_tool_factory(config: AppConfig, mgr):
    """创建内置工具工厂。"""
    from agent.tools.builtin.factory import BuiltinToolFactory

    return BuiltinToolFactory(mgr.service_registry)


def create_query_service(config: AppConfig, mgr):
    """创建 QueryService，组装所有依赖。

    Args:
        config: 当前应用配置。
        mgr: ConfigManager 实例，用于获取缓存的基础设施组件。
    """
    from services.query_service import QueryService
    from services.memory_service import MemoryService

    if hasattr(mgr, "bootstrap_builtin_tools"):
        mgr.bootstrap_builtin_tools(refresh=False)

    memory_service = None
    if mgr.memory_store and mgr.agent_session_store:
        memory_service = MemoryService(
            mgr.memory_store,
            mgr.agent_session_store,
            mgr.llm_client,
        )

    return QueryService(
        mgr.document_store,
        mgr.vector_index,
        mgr.llm_client,
        mgr.embedding_client,
        session_store=mgr.agent_session_store,
        memory_service=memory_service,
        config_manager=mgr,
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


def create_document_ingestion_service(mgr):
    """创建上传文档摄入服务。"""
    from services.document_ingestion_service import DocumentIngestionService

    if (
        mgr.upload_store is None
        or mgr.document_store is None
        or mgr.document_parser is None
        or mgr.chunking_service is None
        or mgr.embedding_client is None
        or mgr.vector_index is None
    ):
        raise RuntimeError("文档摄入服务依赖未就绪")

    return DocumentIngestionService(
        upload_store=mgr.upload_store,
        document_store=mgr.document_store,
        parser=mgr.document_parser,
        chunking_service=mgr.chunking_service,
        embedding_client=mgr.embedding_client,
        vector_index=mgr.vector_index,
        task_run_store=mgr.task_run_store,
        redis_state_store=mgr.redis_state_store,
    )
