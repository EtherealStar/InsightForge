"""
运行时配置管理器 — 支持热重载，无需重启后端

使用方式:
    from core.config_manager import get_config_manager

    mgr = get_config_manager()
    config = mgr.config              # 当前 AppConfig
    store = mgr.article_store        # 缓存的 ArticleStore 单例
    llm = mgr.llm_client             # 缓存的 LLM 客户端单例
    mgr.reload()                     # 重新读取 .env 并重建受影响组件
"""

import threading
import structlog
from typing import Any, Callable

from core.config import AppConfig
from core.factory import (
    create_article_store,
    create_vector_store,
    create_llm_client,
    create_embedding_client,
    create_rerank_client,
    create_summary_llm_client,
    create_chunking_service,
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

        # 缓存的组件实例
        self._article_store: Any = None
        self._vector_store: Any = None
        self._llm_client: Any = None
        self._embedding_client: Any = None
        self._rerank_client: Any = None
        self._summary_llm_client: Any = None
        self._chunking_service: Any = None

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
            self._article_store = create_article_store(self._config)
            self._vector_store = create_vector_store(self._config)
            try:
                self._llm_client = create_llm_client(self._config)
            except Exception as e:
                logger.warning(f"LLM 客户端创建失败 (可能 API Key 未配置): {e}")
                self._llm_client = None
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
                self._summary_llm_client = create_summary_llm_client(self._config)
            except Exception as e:
                logger.warning(f"Summary LLM 客户端创建失败: {e}")
                self._summary_llm_client = None
            try:
                self._chunking_service = create_chunking_service(self._config)
            except Exception as e:
                logger.warning(f"分块服务创建失败: {e}")
                self._chunking_service = None

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
        embed_fields = {"embedding_api_key", "embedding_base_url", "embedding_model"}
        store_fields = {"pg_dsn"}
        vector_fields = {"pg_dsn", "embedding_vector_size"}

        changed_keys = set(changes.keys())
        rebuilt: list[str] = []

        with self._component_lock:
            if changed_keys & store_fields:
                self._article_store = create_article_store(self._config)
                rebuilt.append("article_store")

            if changed_keys & vector_fields:
                self._vector_store = create_vector_store(self._config)
                rebuilt.append("vector_store")

            if changed_keys & llm_fields:
                try:
                    self._llm_client = create_llm_client(self._config)
                    rebuilt.append("llm_client")
                except Exception as e:
                    logger.error(f"重建 LLM 客户端失败: {e}")

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

            summary_fields = {
                "summary_use_same_llm", "summary_llm_provider",
                "summary_llm_api_key", "summary_llm_base_url",
                "summary_llm_model", "summary_batch_size",
            }
            if changed_keys & (summary_fields | llm_fields):
                try:
                    self._summary_llm_client = create_summary_llm_client(self._config)
                    rebuilt.append("summary_llm_client")
                except Exception as e:
                    logger.error(f"重建 Summary LLM 客户端失败: {e}")

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

    # ------------------------------------------------------------------
    # 属性访问器
    # ------------------------------------------------------------------

    @property
    def config(self) -> AppConfig:
        """返回当前运行时配置。"""
        return self._config

    @property
    def article_store(self):
        """返回缓存的 ArticleStore 单例。"""
        return self._article_store

    @property
    def vector_store(self):
        """返回缓存的 VectorStore 单例。"""
        return self._vector_store

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
    def summary_llm_client(self):
        """返回缓存的摘要专用 LLM 客户端单例。"""
        return self._summary_llm_client

    @property
    def chunking_service(self):
        """返回缓存的分块服务单例。"""
        return self._chunking_service

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
