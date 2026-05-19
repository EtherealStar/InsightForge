"""
运行时配置管理器 — 支持热重载，无需重启后端

使用方式:
    from core.config_manager import get_config_manager

    mgr = get_config_manager()
    config = mgr.config              # 当前 AppConfig
    llm = mgr.llm_client             # 缓存的 LLM 客户端单例
    mgr.reload()                     # 重新读取 .env 并重建受影响组件
"""

import threading
import structlog
from typing import Any, Callable

from core.config import AppConfig
from core.factory import (
    create_agent_session_store,
    create_competitor_store,
    create_document_store,
    create_insight_store,
    create_intel_store,
    create_memory_store,
    create_upload_store,
    create_redis_state_store,
    create_file_type_detector,
    create_file_blob_store,
    create_archive_extractor,
    create_document_parser,
    create_report_store,
    create_auth_store,
    create_config_audit_store,
    create_task_run_store,
    create_qdrant_vector_index,
    create_llm_client,
    create_structured_extraction_client,
    create_judge_client,
    create_embedding_client,
    create_rerank_client,
    create_chunking_service,
    create_hybrid_search_service,
    create_webhook_service,
    create_deep_research_service,
    create_competitor_service,
    create_intel_service,
    create_insight_service,
    create_report_service,
    create_web_search_service,
    create_service_registry,
    create_builtin_tool_definition_registry,
    create_builtin_tool_factory,
    create_query_service,
    create_memory_service,
    create_document_ingestion_service,
)

logger = structlog.get_logger(__name__)


class ConfigManager:
    """
    应用级单例，集中管理配置和基础设施组件的生命周期。

    - 启动时从 .env 加载配置并创建所有组件
    - 调用 reload() 可热重载 .env，只重建受影响的组件
    - 线程安全
    """

    _instance: "ConfigManager | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self._config: AppConfig = AppConfig()
        self._version: int = 0
        self._component_lock = threading.Lock()

        # 缓存的基础设施组件实例
        self._agent_session_store: Any = None
        self._memory_store: Any = None
        self._task_run_store: Any = None
        self._upload_store: Any = None
        self._redis_state_store: Any = None
        self._file_type_detector: Any = None
        self._file_blob_store: Any = None
        self._archive_extractor: Any = None
        self._document_parser: Any = None
        self._document_store: Any = None
        self._vector_index: Any = None
        self._llm_client: Any = None
        self._embedding_client: Any = None
        self._rerank_client: Any = None
        self._chunking_service: Any = None
        self._hybrid_search_service: Any = None

        # 竞品分析扩展组件
        self._competitor_store: Any = None
        self._report_store: Any = None
        self._auth_store: Any = None
        self._config_audit_store: Any = None
        self._intel_store: Any = None
        self._insight_store: Any = None
        self._structured_extraction_client: Any = None
        self._judge_client: Any = None

        # 缓存的 Service 层实例
        self._webhook_service: Any = None
        self._deep_research_service: Any = None
        self._query_service: Any = None
        self._memory_service: Any = None
        self._document_ingestion_service: Any = None
        self._competitor_service: Any = None
        self._intel_service: Any = None
        self._insight_service: Any = None
        self._report_service: Any = None
        self._web_search_service: Any = None
        self._service_registry: Any = None
        self._builtin_tool_definition_registry: Any = None
        self._builtin_tool_factory: Any = None

        # 变更回调列表
        self._callbacks: list[Callable[[dict], None]] = []

        # 初始创建所有组件
        self._rebuild_all()
        logger.info("ConfigManager 初始化完成 (v0)")

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _rebuild_all(self) -> None:
        """（在锁外调用时需自行加锁）重建全部组件。"""
        with self._component_lock:
            self._document_store = create_document_store(self._config)
            self._agent_session_store = create_agent_session_store(self._config)
            self._memory_store = create_memory_store(self._config)
            self._task_run_store = create_task_run_store(self._config)
            self._upload_store = create_upload_store(self._config)
            self._redis_state_store = create_redis_state_store(self._config)
            self._file_type_detector = create_file_type_detector(self._config)
            self._file_blob_store = create_file_blob_store(self._config)
            self._archive_extractor = create_archive_extractor(self._config)
            self._document_parser = create_document_parser(self._config)
            self._vector_index = create_qdrant_vector_index(self._config)
            self._competitor_store = create_competitor_store(self._config)
            self._report_store = create_report_store(self._config)
            self._auth_store = create_auth_store(self._config)
            self._config_audit_store = create_config_audit_store(self._config)
            self._intel_store = create_intel_store(self._config)
            self._insight_store = create_insight_store(self._config)
            try:
                self._llm_client = create_llm_client(self._config)
            except Exception as e:
                logger.warning(f"LLM 客户端创建失败 (可能 API Key 未配置): {e}")
                self._llm_client = None
            try:
                self._structured_extraction_client = create_structured_extraction_client(
                    self._config
                )
            except Exception as e:
                logger.warning(f"结构化抽取客户端创建失败: {e}")
                self._structured_extraction_client = None
            try:
                self._judge_client = create_judge_client(self._config)
            except Exception as e:
                logger.warning(f"Judge 客户端创建失败: {e}")
                self._judge_client = None
            try:
                self._embedding_client = create_embedding_client(self._config)
            except Exception as e:
                logger.warning(f"Embedding 客户端创建失败: {e}")
                self._embedding_client = None
            try:
                self._rerank_client = create_rerank_client(self._config)
            except Exception as e:
                logger.warning(f"Rerank 客户端创建失败: {e}")
                self._rerank_client = None
            try:
                self._chunking_service = create_chunking_service(self._config)
            except Exception as e:
                logger.warning(f"分块服务创建失败: {e}")
                self._chunking_service = None

        self._hybrid_search_service = None

        # Service 层组件
        self._webhook_service = create_webhook_service()
        self._deep_research_service = create_deep_research_service()
        # query_service / memory_service 依赖 LLM，延迟到属性访问时懒加载
        self._query_service = None
        self._memory_service = None
        self._document_ingestion_service = None
        self._competitor_service = None
        self._intel_service = None
        self._insight_service = None
        self._report_service = None
        self._web_search_service = None
        self._service_registry = None
        self._builtin_tool_definition_registry = None
        self._builtin_tool_factory = None

        self.bootstrap_builtin_tools(refresh=True)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def reload(self) -> dict:
        """
        重新读取 .env 并与当前配置 diff，只重建受影响的组件。

        Returns:
            dict: {"changed": bool, "fields": [...], "rebuilt": [...], "version": int}
        """
        old_config = self._config
        new_config = AppConfig()

        # 计算差异
        changes: dict[str, dict] = {}
        for field_name in new_config.model_fields:
            old_val = getattr(old_config, field_name)
            new_val = getattr(new_config, field_name)
            if old_val != new_val:
                changes[field_name] = {"old": old_val, "new": new_val}

        if not changes:
            logger.info("reload(): 配置无变化")
            return {"changed": False, "fields": [], "rebuilt": [], "version": self._version}

        # 更新配置
        self._config = new_config
        self._version += 1

        # 根据变更字段判断需要重建的组件
        llm_fields = {
            "llm_provider", "llm_api_key", "llm_base_url", "llm_model",
            "openai_api_key", "google_api_key", "anthropic_api_key",
        }
        structured_extraction_fields = {
            "structured_extraction_provider",
            "structured_extraction_api_key",
            "structured_extraction_base_url",
            "structured_extraction_model",
            "structured_extraction_temperature",
            "structured_extraction_max_tokens",
        }
        judge_fields = {
            "judge_provider",
            "judge_api_key",
            "judge_base_url",
            "judge_model",
            "judge_temperature",
            "judge_max_tokens",
        }
        embed_fields = {
            "embedding_api_key",
            "embedding_base_url",
            "embedding_model",
            "embedding_vector_size",
        }
        store_fields = {"pg_dsn"}
        agent_session_fields = {"pg_dsn", "celery_broker_url"}
        redis_fields = {"celery_broker_url"}
        document_fields = {"pg_dsn"}
        upload_fields = {
            "upload_storage_root",
            "upload_max_file_size_mb",
            "upload_max_batch_size_mb",
            "upload_max_archive_files",
            "upload_max_archive_unpacked_mb",
            "upload_allowed_extensions",
        }
        vector_fields = {
            "qdrant_url",
            "qdrant_api_key",
            "qdrant_documents_collection",
            "qdrant_distance",
            "embedding_vector_size",
        }
        web_search_fields = {"tavily_api_key", "newsapi_api_key"}

        changed_keys = set(changes.keys())
        rebuilt: list[str] = []

        with self._component_lock:
            if changed_keys & store_fields:
                self._document_store = create_document_store(self._config)
                self._memory_store = create_memory_store(self._config)
                self._task_run_store = create_task_run_store(self._config)
                self._upload_store = create_upload_store(self._config)
                self._competitor_store = create_competitor_store(self._config)
                self._report_store = create_report_store(self._config)
                self._auth_store = create_auth_store(self._config)
                self._config_audit_store = create_config_audit_store(self._config)
                self._intel_store = create_intel_store(self._config)
                self._insight_store = create_insight_store(self._config)
                rebuilt.append("document_store")
                rebuilt.append("memory_store")
                rebuilt.append("task_run_store")
                rebuilt.append("upload_store")
                rebuilt.append("competitor_store")
                rebuilt.append("report_store")
                rebuilt.append("auth_store")
                rebuilt.append("config_audit_store")
                rebuilt.append("intel_store")
                rebuilt.append("insight_store")
                self._competitor_service = None
                self._intel_service = None
                self._insight_service = None
                self._report_service = None
                self._service_registry = None
                self._builtin_tool_factory = None
                rebuilt.append("phase2_services (invalidated)")

            if changed_keys & agent_session_fields:
                self._agent_session_store = create_agent_session_store(self._config)
                rebuilt.append("agent_session_store")

            if changed_keys & redis_fields:
                self._redis_state_store = create_redis_state_store(self._config)
                rebuilt.append("redis_state_store")
                self._intel_service = None
                self._service_registry = None
                self._builtin_tool_factory = None
                rebuilt.append("intel_service (invalidated)")

            if changed_keys & upload_fields:
                self._file_type_detector = create_file_type_detector(self._config)
                self._file_blob_store = create_file_blob_store(self._config)
                self._archive_extractor = create_archive_extractor(self._config)
                self._document_parser = create_document_parser(self._config)
                rebuilt.append("file_type_detector")
                rebuilt.append("file_blob_store")
                rebuilt.append("archive_extractor")
                rebuilt.append("document_parser")

            if changed_keys & vector_fields:
                self._vector_index = create_qdrant_vector_index(self._config)
                rebuilt.append("vector_index")

            if changed_keys & llm_fields:
                try:
                    self._llm_client = create_llm_client(self._config)
                    rebuilt.append("llm_client")
                    self._insight_service = None
                    self._report_service = None
                    self._service_registry = None
                    self._builtin_tool_factory = None
                    rebuilt.append("insight_service (invalidated)")
                    rebuilt.append("report_service (invalidated)")
                except Exception as e:
                    logger.error(f"重建 LLM 客户端失败: {e}")

            if changed_keys & structured_extraction_fields:
                try:
                    self._structured_extraction_client = create_structured_extraction_client(
                        self._config
                    )
                    rebuilt.append("structured_extraction_client")
                    self._intel_service = None
                    self._service_registry = None
                    self._builtin_tool_factory = None
                    rebuilt.append("intel_service (invalidated)")
                except Exception as e:
                    logger.error(f"重建结构化抽取客户端失败: {e}")
                    self._structured_extraction_client = None

            if changed_keys & judge_fields:
                try:
                    self._judge_client = create_judge_client(self._config)
                    rebuilt.append("judge_client")
                    self._report_service = None
                    self._service_registry = None
                    self._builtin_tool_factory = None
                    rebuilt.append("report_service (invalidated)")
                except Exception as e:
                    logger.error(f"重建 Judge 客户端失败: {e}")
                    self._judge_client = None

            if changed_keys & embed_fields:
                try:
                    self._embedding_client = create_embedding_client(self._config)
                    rebuilt.append("embedding_client")
                except Exception as e:
                    logger.error(f"重建 Embedding 客户端失败: {e}")

            rerank_fields = {
                "rerank_enabled", "rerank_api_key", "rerank_base_url",
                "rerank_model", "rerank_top_k_multiplier",
            }
            if changed_keys & rerank_fields:
                try:
                    self._rerank_client = create_rerank_client(self._config)
                    rebuilt.append("rerank_client")
                except Exception as e:
                    logger.error(f"重建 Rerank 客户端失败: {e}")

            # Service 层：当依赖的基础设施组件变更时，清空缓存触发懒加载重建
            if changed_keys & (llm_fields | store_fields | document_fields | embed_fields | vector_fields):
                self._query_service = None
                self._memory_service = None
                self._document_ingestion_service = None
                self._competitor_service = None
                self._intel_service = None
                self._insight_service = None
                self._report_service = None
                self._service_registry = None
                self._builtin_tool_factory = None
                rebuilt.append("query_service (invalidated)")
                rebuilt.append("memory_service (invalidated)")
                rebuilt.append("document_ingestion_service (invalidated)")
                rebuilt.append("phase2_services (invalidated)")

            if changed_keys & upload_fields:
                self._document_ingestion_service = None
                rebuilt.append("document_ingestion_service (invalidated)")

            hybrid_fields = {"hybrid_rrf_k"}
            if changed_keys & (hybrid_fields | store_fields | document_fields | embed_fields | vector_fields):
                self._hybrid_search_service = None
                self._service_registry = None
                self._builtin_tool_factory = None
                rebuilt.append("hybrid_search_service (invalidated)")

            if changed_keys & web_search_fields:
                self._web_search_service = None
                self._service_registry = None
                self._builtin_tool_factory = None
                rebuilt.append("web_search_service (invalidated)")

        self.bootstrap_builtin_tools(refresh=True)

        # 通知注册的回调
        for cb in self._callbacks:
            try:
                cb(changes)
            except Exception:
                logger.exception("配置变更回调执行失败")

        logger.info(
            f"配置热重载完成 (v{self._version}): "
            f"变更字段={list(changes.keys())}, 重建组件={rebuilt}"
        )
        return {
            "changed": True,
            "fields": list(changes.keys()),
            "rebuilt": rebuilt,
            "version": self._version,
        }

    def bootstrap_builtin_tools(self, refresh: bool = True) -> int:
        """注册或刷新内置 Agent 工具。

        Args:
            refresh: 是否先注销同名内置工具再重新注册。

        Returns:
            int: 成功注册的工具数量。
        """
        try:
            from agent.tools.builtin import register_builtin_tools

            return register_builtin_tools(self, refresh=refresh)
        except Exception as e:
            logger.warning(f"内置工具注册失败 (refresh={refresh}): {e}")
            return 0

    # ------------------------------------------------------------------
    # 属性访问器
    # ------------------------------------------------------------------

    @property
    def config(self) -> AppConfig:
        """返回当前运行时配置。"""
        return self._config

    @property
    def agent_session_store(self):
        """返回缓存的 AgentSessionStore 单例。"""
        return self._agent_session_store

    @property
    def memory_store(self):
        """返回缓存的 MemoryStore 单例。"""
        return self._memory_store

    @property
    def task_run_store(self):
        """返回缓存的 TaskRunStore 单例。"""
        return self._task_run_store

    @property
    def upload_store(self):
        """返回缓存的 UploadStore 单例。"""
        return self._upload_store

    @property
    def redis_state_store(self):
        """返回缓存的 RedisStateStore 单例。"""
        return self._redis_state_store

    @property
    def file_type_detector(self):
        """返回缓存的文件类型检测器单例。"""
        return self._file_type_detector

    @property
    def file_blob_store(self):
        """返回缓存的文件 BlobStore 单例。"""
        return self._file_blob_store

    @property
    def archive_extractor(self):
        """返回缓存的 ArchiveExtractor 单例。"""
        return self._archive_extractor

    @property
    def document_parser(self):
        """返回缓存的 DocumentParser 单例。"""
        return self._document_parser

    @property
    def document_store(self):
        """返回缓存的 DocumentStore 单例。"""
        return self._document_store

    @property
    def vector_index(self):
        """返回缓存的 Qdrant VectorIndex 单例。"""
        return self._vector_index

    @property
    def llm_client(self):
        """返回缓存的 LLM 客户端单例。"""
        return self._llm_client

    @property
    def embedding_client(self):
        """返回缓存的 Embedding 客户端单例。"""
        return self._embedding_client

    @property
    def rerank_client(self):
        """返回缓存的 Rerank 客户端单例（未启用时为 None）。"""
        return self._rerank_client

    @property
    def chunking_service(self):
        """返回缓存的分块服务单例。"""
        return self._chunking_service

    @property
    def hybrid_search_service(self):
        """返回缓存的混合检索服务单例（向量 + 关键词 + RRF）。"""
        if self._hybrid_search_service is None:
            with self._component_lock:
                if self._hybrid_search_service is None:
                    self._hybrid_search_service = create_hybrid_search_service(
                        self._config,
                        self,
                    )
        return self._hybrid_search_service

    @property
    def competitor_store(self):
        """返回缓存的 CompetitorStore 单例。"""
        return self._competitor_store

    @property
    def report_store(self):
        """返回缓存的 ReportStore 单例。"""
        return self._report_store

    @property
    def auth_store(self):
        """返回缓存的 AuthStore 单例。"""
        return self._auth_store

    @property
    def config_audit_store(self):
        """返回缓存的 ConfigAuditStore 单例。"""
        return self._config_audit_store

    @property
    def intel_store(self):
        """返回缓存的 IntelStore 单例。"""
        return self._intel_store

    @property
    def insight_store(self):
        """返回缓存的 InsightStore 单例。"""
        return self._insight_store

    @property
    def structured_extraction_client(self):
        """返回缓存的结构化抽取客户端单例。"""
        return self._structured_extraction_client

    @property
    def judge_client(self):
        """返回缓存的 Judge 客户端单例。"""
        return self._judge_client

    @property
    def competitor_service(self):
        """返回缓存的 CompetitorService 单例。"""
        if self._competitor_service is None:
            with self._component_lock:
                if self._competitor_service is None:
                    self._competitor_service = create_competitor_service(self._config, self)
        return self._competitor_service

    @property
    def intel_service(self):
        """返回缓存的 IntelService 单例。"""
        if self._intel_service is None:
            with self._component_lock:
                if self._intel_service is None:
                    self._intel_service = create_intel_service(self._config, self)
        return self._intel_service

    @property
    def insight_service(self):
        """返回缓存的 InsightService 单例。"""
        if self._insight_service is None:
            with self._component_lock:
                if self._insight_service is None:
                    self._insight_service = create_insight_service(self._config, self)
        return self._insight_service

    @property
    def report_service(self):
        """返回缓存的 ReportService 单例。"""
        if self._report_service is None:
            with self._component_lock:
                if self._report_service is None:
                    self._report_service = create_report_service(self._config, self)
        return self._report_service

    @property
    def web_search_service(self):
        """返回缓存的 WebSearchService 单例。"""
        if self._web_search_service is None:
            with self._component_lock:
                if self._web_search_service is None:
                    self._web_search_service = create_web_search_service(self._config, self)
        return self._web_search_service

    @property
    def service_registry(self):
        """返回工具可用的 service 白名单注册表。"""
        if self._service_registry is None:
            with self._component_lock:
                if self._service_registry is None:
                    self._service_registry = create_service_registry(self._config, self)
        return self._service_registry

    @property
    def builtin_tool_definition_registry(self):
        """返回内置工具定义注册表。"""
        if self._builtin_tool_definition_registry is None:
            with self._component_lock:
                if self._builtin_tool_definition_registry is None:
                    self._builtin_tool_definition_registry = create_builtin_tool_definition_registry()
        return self._builtin_tool_definition_registry

    @property
    def builtin_tool_factory(self):
        """返回内置工具工厂。"""
        if self._builtin_tool_factory is None:
            with self._component_lock:
                if self._builtin_tool_factory is None:
                    self._builtin_tool_factory = create_builtin_tool_factory(self._config, self)
        return self._builtin_tool_factory

    @property
    def webhook_service(self):
        """返回缓存的 WebhookService 单例。"""
        if self._webhook_service is None:
            with self._component_lock:
                if self._webhook_service is None:
                    self._webhook_service = create_webhook_service()
        return self._webhook_service

    @property
    def deep_research_service(self):
        """返回缓存的 DeepResearchService 单例。"""
        if self._deep_research_service is None:
            with self._component_lock:
                if self._deep_research_service is None:
                    self._deep_research_service = create_deep_research_service()
        return self._deep_research_service

    @property
    def query_service(self):
        """返回缓存的 QueryService 单例（懒加载，依赖 LLM）。"""
        if self._query_service is None:
            with self._component_lock:
                if self._query_service is None:
                    self._query_service = create_query_service(self._config, self)
        return self._query_service

    @property
    def memory_service(self):
        """返回缓存的 MemoryService 单例（懒加载）。"""
        if self._memory_service is None:
            with self._component_lock:
                if self._memory_service is None:
                    self._memory_service = create_memory_service(self)
        return self._memory_service

    @property
    def document_ingestion_service(self):
        """返回缓存的文档摄入服务单例（懒加载）。"""
        if self._document_ingestion_service is None:
            with self._component_lock:
                if self._document_ingestion_service is None:
                    self._document_ingestion_service = create_document_ingestion_service(self)
        return self._document_ingestion_service

    @property
    def version(self) -> int:
        """返回当前配置版本号。"""
        return self._version

    # ------------------------------------------------------------------
    # 回调注册
    # ------------------------------------------------------------------

    def on_config_changed(self, callback: Callable[[dict], None]) -> None:
        """
        注册一个配置变更回调，reload() 成功后会依次调用。

        callback 签名: (changes: dict[str, {"old": Any, "new": Any}]) -> None
        """
        self._callbacks.append(callback)


# ======================================================================
# 模块级便捷函数
# ======================================================================

def get_config_manager() -> ConfigManager:
    """获取全局唯一的 ConfigManager 实例。"""
    return ConfigManager()
