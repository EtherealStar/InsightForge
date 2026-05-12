import logging
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class AppConfig(BaseSettings):
    """应用配置，从 .env 加载并做类型校验"""

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

    # --- Celery / Redis ---
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # --- 调度 ---
    fetch_interval_hours: int = 4
    daily_brief_hour: int = 8
    brief_fetch_hours: int = 24
    brief_mode: Literal["daily", "interval"] = "daily"  # daily=每天固定时间, interval=按间隔
    brief_interval_hours: int = 8  # interval 模式下的间隔小时数
    max_articles_per_fetch: int = 20

    # --- 数据管理 ---
    article_retention_days: int = 90
    log_level: str = "INFO"

    # --- RSS 来源 ---
    rss_feeds: list[dict] = Field(
        default=[
            {
                "name": "Reuters",
                "url": "https://www.reutersagency.com/en/reuters-best/rss/",
            },
            {"name": "BBC News", "url": "https://feeds.bbci.co.uk/news/rss.xml"},
            {
                "name": "联合早报",
                "url": "https://www.zaobao.com.sg/rss/realtime/china",
            },
        ]
    )

    # --- 搜索引擎 ---
    tavily_api_key: str = ""

    # --- AI 摘要配置 ---
    summary_use_same_llm: bool = True        # True=复用主 LLM，False=使用独立配置
    summary_llm_provider: str = ""            # 独立 provider
    summary_llm_api_key: str = ""             # 独立 API Key
    summary_llm_base_url: str = ""            # 独立 Base URL
    summary_llm_model: str = ""               # 独立模型
    summary_batch_size: int = 5               # 每批发送多少条新闻给 AI

    # --- 分块配置 ---
    chunk_max_child_tokens: int = 512          # 子 chunk 最大 token 数
    chunk_target_parent_tokens: int = 1024     # 父 chunk 目标 token 数
    chunk_overlap_tokens: int = 100            # 父 chunk 之间的 overlap token 数
    embedding_vector_size: int = 1536          # pgvector embedding 维度

    # --- 混合检索配置 ---
    hybrid_search_enabled: bool = True           # 是否启用混合检索（False=退化为纯向量检索）
    hybrid_rrf_k: int = 60                       # RRF 平滑常数
    hybrid_vector_weight: float = 1.0            # 向量检索权重
    hybrid_keyword_weight: float = 1.0           # 关键词检索权重
    hybrid_keyword_candidates: int = 20          # 关键词检索候选数量

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
