# 外部依赖与集成参考

> **来源**：整合自 [ARCHITECTURE.md](../../ARCHITECTURE.md) 的配置管理、依赖注入和外部服务接口信息。

---

## 外部服务依赖

| 服务 | 集成方式 | 配置项 |
|---|---|---|
| PostgreSQL 16 + pgvector | `psycopg2-binary` 同步连接 | `PG_DSN`, `EMBEDDING_VECTOR_SIZE` |
| Redis 7 | Celery Broker | `CELERY_BROKER_URL` |
| OpenAI-compatible LLM | `openai` SDK | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` |
| OpenAI 官方 | `openai` SDK | `OPENAI_API_KEY` |
| Google Gemini | `google-genai` SDK | `GOOGLE_API_KEY` |
| Anthropic Claude | `anthropic` SDK | `ANTHROPIC_API_KEY` |
| Embedding API | `openai` SDK (自定义端点) | `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL` |
| Rerank API | HTTP POST `{base_url}/rerank` | `RERANK_API_KEY`, `RERANK_BASE_URL`, `RERANK_MODEL` |
| DuckDuckGo | `duckduckgo-search` | 无需 API Key |
| Tavily | `tavily-python` | `TAVILY_API_KEY` |
| NewsAPI | `requests` HTTP 代理 | `NEWSAPI_KEY` |

---

## Docker Compose 服务清单

| 服务 | 镜像 | 端口 | 数据卷 |
|---|---|---|---|
| `logos-postgres` | `pgvector/pgvector:pg16` | 5432 | `postgres_data` |
| `logos-redis` | `redis:7-alpine` | 6379 | `redis_data` |

所有容器配置 `healthcheck`，通过 Docker Named Volumes 持久化数据。

本地 `docker-compose.yml` 只启动基础设施，应用仍在本机 Python/Vite 进程中运行。

生产 `docker-compose.prod.yml` 增加以下服务：

| 服务 | 镜像/来源 | 对外端口 | 说明 |
|---|---|---|---|
| `web` | 本仓库 `Dockerfile` | 无直接发布 | FastAPI + Vue 静态资源 |
| `worker` | 本仓库 `Dockerfile` | 无 | Celery Worker |
| `beat` | 本仓库 `Dockerfile` | 无 | Celery Beat |
| `migrate` | 本仓库 `Dockerfile` | 无 | 一次性初始化 schema 并执行 migrations |
| `caddy` | `caddy:2-alpine` | 80/443 | Basic Auth + 反向代理 |
| `flower` | 本仓库 `Dockerfile` | profile 启用后内部 5555 | 可选任务监控 |

生产部署入口见 [../deployment/docker-vps.md](../deployment/docker-vps.md)。`.env.deploy.example` 提供容器内连接串，`data`、`output`、PostgreSQL、Redis、Caddy 数据均使用 Docker Named Volumes。

---

## ConfigManager 组件管理

`ConfigManager` 是应用级线程安全单例，管理以下组件的生命周期：

| 组件 | 工厂函数 | 实现类 |
|---|---|---|
| `article_store` | `create_article_store()` | PostgresArticleStore |
| `vector_store` | `create_vector_store()` | PgVectorStore |
| `llm_client` | `create_llm_client()` | 4 种 LLM 客户端之一 |
| `embedding_client` | `create_embedding_client()` | OpenAICompatibleEmbeddingClient |
| `rerank_client` | `create_rerank_client()` | OpenAICompatibleRerankClient (可选) |
| `summary_llm_client` | `create_summary_llm_client()` | 可复用主 LLM |
| `chunking_service` | `create_chunking_service()` | ChunkingService |

`reload()` 方法支持热重载：读取最新 `.env`，diff 变更字段，只重建受影响的组件。

---

## AppConfig 完整字段参考

```python
class AppConfig(BaseSettings):
    # === LLM ===
    llm_provider: Literal["openai_compatible", "openai", "gemini", "anthropic"]
    llm_api_key / llm_base_url / llm_model: str
    openai_api_key / google_api_key / anthropic_api_key: str

    # === Embedding ===
    embedding_api_key / embedding_base_url / embedding_model: str

    # === Rerank (可选) ===
    rerank_enabled: bool = False
    rerank_api_key / rerank_base_url / rerank_model: str
    rerank_top_k_multiplier: int = 3

    # === 存储路径 ===
    markdown_output_path: str = "data/markdown"
    output_path: str = "output"

    # === PostgreSQL + pgvector ===
    pg_dsn: str = "postgresql://logos:logos@localhost:5432/logos"
    embedding_vector_size: int = 1536

    # === Celery / Redis ===
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # === 调度 ===
    fetch_interval_hours: int = 4
    daily_brief_hour: int = 8
    brief_fetch_hours: int = 24
    brief_mode: Literal["daily", "interval"] = "daily"
    brief_interval_hours: int = 8
    max_articles_per_fetch: int = 20

    # === 数据管理 ===
    article_retention_days: int = 90
    log_level: str = "INFO"

    # === RSS 来源 ===
    rss_feeds: list[dict]   # 默认 3 个源

    # === 搜索引擎 ===
    tavily_api_key: str = ""

    # === AI 摘要 ===
    summary_use_same_llm: bool = True
    summary_llm_provider / summary_llm_api_key / summary_llm_base_url / summary_llm_model: str
    summary_batch_size: int = 5

    # === 分块 ===
    chunk_max_child_tokens: int = 512
    chunk_target_parent_tokens: int = 1024
    chunk_overlap_tokens: int = 100

    # === 混合检索 ===
    hybrid_search_enabled: bool = True
    hybrid_rrf_k: int = 60
    hybrid_vector_weight: float = 1.0
    hybrid_keyword_weight: float = 1.0
    hybrid_keyword_candidates: int = 20
```

---

## 配置来源一览

| 配置项 | 存储位置 | 管理方式 |
|---|---|---|
| LLM/Embedding/Rerank API 参数 | `.env` 文件 | 前端 ConfigView 通过 API 读写 |
| RSS 源列表 | `data/feeds_config.json` | 前端 SettingsView 通过 API 增删 |
| 爬虫源列表 | `data/sites_config.json` | 前端 SettingsView 通过 API 增删 |
| 调度参数 | `.env` 文件 | 前端 SettingsView 通过 API 读写 |
| 推送渠道 + 自动推送 | `data/webhook_config.json` | 前端 WebhookView 通过 API 增删改 |
| 搜索引擎 Key | `.env` 文件 | 前端 ConfigView 通过 API 读写 |
| 应用默认值 | `core/config.py` | pydantic Field default |
