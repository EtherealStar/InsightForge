from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
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

    # --- 存储 ---
    db_path: str = "data/news.db"
    chroma_path: str = "data/chroma"
    output_path: str = "output"

    # --- 调度 ---
    fetch_interval_hours: int = 4
    daily_brief_hour: int = 8
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

    @field_validator("llm_api_key", "embedding_api_key")
    @classmethod
    def warn_empty_key(cls, v, info):
        if not v:
            import logging

            logging.warning(
                f"⚠ {info.field_name} 为空 — 相关功能将被禁用"
            )
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
