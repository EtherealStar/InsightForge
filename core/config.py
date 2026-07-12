import logging
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class AppConfig(BaseSettings):
    """应用配置（InsightForge 竞品分析助手），从 .env 加载并做类型校验"""

    # --- LLM 配置 ---
    llm_provider: Literal[
        "openai_compatible", "openai", "gemini", "anthropic"
    ] = "openai_compatible"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # 各厂商 API Key（按 llm_provider 选择使用）
    openai_api_key: str = ""
    google_api_key: str = ""
    anthropic_api_key: str = ""

    # --- 结构化抽取配置（独立于 Agent/报告主 LLM） ---
    structured_extraction_provider: Literal[
        "openai_compatible", "openai", "gemini", "anthropic"
    ] = "openai_compatible"
    structured_extraction_api_key: str = ""
    structured_extraction_base_url: str = ""
    structured_extraction_model: str = ""
    structured_extraction_temperature: float = 0.0
    structured_extraction_max_tokens: int = 2048

    # --- 报告质量 Judge 配置（独立于主 LLM 和结构化抽取） ---
    judge_provider: Literal[
        "openai_compatible", "openai", "gemini", "anthropic"
    ] = "openai_compatible"
    judge_api_key: str = ""
    judge_base_url: str = ""
    judge_model: str = ""
    judge_temperature: float = 0.0
    judge_max_tokens: int = 2048

    # --- Embedding 配置 ---
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""

    # --- Rerank 重排序 ---
    rerank_enabled: bool = False
    rerank_api_key: str = ""
    rerank_base_url: str = ""                  # e.g. https://api.jina.ai/v1
    rerank_model: str = ""                     # e.g. jina-reranker-v2-base-multilingual
    rerank_top_k_multiplier: int = 3           # 候选召回倍数

    # --- 存储 ---
    pg_dsn: str = "postgresql://postgres:postgres@localhost:5432/logos"
    markdown_output_path: str = "data/markdown"
    output_path: str = "output"

    # --- 上传文件基础设施 ---
    upload_storage_root: str = "storage"
    upload_max_file_size_mb: int = 50
    upload_max_batch_size_mb: int = 200
    upload_max_archive_files: int = 200
    upload_max_archive_unpacked_mb: int = 500
    upload_allowed_extensions: list[str] = Field(
        default_factory=lambda: [
            "txt",
            "md",
            "markdown",
            "html",
            "htm",
            "csv",
            "tsv",
            "zip",
        ]
    )

    # --- Qdrant Vector Index ---
    vector_backend: Literal["qdrant"] = "qdrant"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_documents_collection: str = "insightforge_documents_v1"
    qdrant_distance: str = "Cosine"

    # --- Celery / Redis ---
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # --- 调度 ---
    fetch_interval_hours: int = 4
    max_articles_per_fetch: int = 20

    # --- 数据管理 ---
    article_retention_days: int = 90
    log_level: str = "INFO"

    # --- 竞品情报源 ---
    rss_feeds: list[dict] = Field(
        default=[
            {
                "name": "Cursor Blog",
                "url": "https://www.cursor.com/blog/rss.xml",
            },
            {
                "name": "The Verge AI",
                "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
            },
            {
                "name": "TechCrunch AI",
                "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
            },
        ]
    )

    # --- 搜索引擎 ---
    tavily_api_key: str = ""
    newsapi_api_key: str = ""         # NewsAPI 已合并到 web_search 工具

    # --- 情报分类配置 ---
    intel_classification_enabled: bool = True   # 是否启用 AI 自动情报分类

    # --- 分块配置 ---
    chunk_max_child_tokens: int = 512          # 子 chunk 最大 token 数
    chunk_target_parent_tokens: int = 1024     # 父 chunk 目标 token 数
    chunk_overlap_tokens: int = 100            # 父 chunk 之间的 overlap token 数
    embedding_vector_size: int = 1536          # Embedding dimensions / Qdrant vector size

    # --- 混合检索配置 ---
    hybrid_search_enabled: bool = True           # 是否启用混合检索（False=退化为纯向量检索）
    hybrid_rrf_k: int = 60                       # RRF 平滑常数
    hybrid_vector_weight: float = 1.0            # 向量检索权重
    hybrid_keyword_weight: float = 1.0           # 关键词检索权重
    hybrid_keyword_candidates: int = 20          # 关键词检索候选数量

    # --- 应用级安全和报告质量策略 ---
    app_env: Literal["development", "staging", "production"] = "development"
    auth_enabled: bool = False
    app_api_keys: list[str] = Field(default_factory=list)
    report_quality_min_score: float = 0.75
    report_quality_auto_publish: bool = False

    # 来源治理发布开关：关闭时不改变现有部署行为，开启后准入先于索引。
    source_governance_enabled: bool = False
    dedup_shadow_enabled: bool = False
    dedup_auto_cluster_enabled: bool = False

    # 三层结构化情报 v2 切流开关（Milestone 2-7）。默认关闭直到影子核对通过。
    # 写入与读取分两阶段启用；同一业务请求不会同时写两套事实身份。
    structured_intelligence_v2_write_enabled: bool = True
    structured_intelligence_v2_read_enabled: bool = True

    @field_validator("llm_api_key", "embedding_api_key")
    @classmethod
    def warn_empty_key(cls, v, info):
        if not v:
            import structlog

            logging.warning(
                f" {info.field_name} 为空 — 相关功能将被禁用"
            )
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
