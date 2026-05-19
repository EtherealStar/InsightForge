# 外部依赖与集成参考

> 来源：整合自 [ARCHITECTURE.md](../../ARCHITECTURE.md) 的配置管理、依赖注入和外部服务接口信息。

---

## 外部服务依赖

| 服务 | 集成方式 | 配置项 |
|---|---|---|
| PostgreSQL 16 | `psycopg2-binary` 同步连接 | `PG_DSN` |
| Qdrant | `qdrant-client` | `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_DOCUMENTS_COLLECTION`, `QDRANT_DISTANCE` |
| Redis 7 | Celery Broker / Result Backend | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |
| OpenAI-compatible LLM | `openai` SDK | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` |
| OpenAI 官方 | `openai` SDK | `OPENAI_API_KEY` |
| Google Gemini | `google-genai` SDK | `GOOGLE_API_KEY` |
| Anthropic Claude | `anthropic` SDK | `ANTHROPIC_API_KEY` |
| Embedding API | `openai` SDK，自定义端点 | `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_VECTOR_SIZE` |
| Rerank API | HTTP POST `{base_url}/rerank` | `RERANK_API_KEY`, `RERANK_BASE_URL`, `RERANK_MODEL` |
| DuckDuckGo | `duckduckgo-search` | 无需 API Key |
| Tavily | `tavily-python` | `TAVILY_API_KEY` |
| NewsAPI | `requests` HTTP 代理 | `NEWSAPI_KEY` |

---

## Docker Compose 服务清单

本地 `docker-compose.yml` 只启动基础设施，应用仍在本机 Python/Vite 进程中运行。

| 服务 | 镜像 | 端口 | 数据卷 | 说明 |
|---|---|---|---|---|
| `logos-postgres` | `postgres:16` | 5432 | `postgres_data` | 权威文档、父块、全文索引、point 状态 |
| `logos-redis` | `redis:7-alpine` | 6379 | `redis_data` | Celery broker/result backend |
| `logos-qdrant` | `qdrant/qdrant` | 6333 | `qdrant_data` | 子块向量和 payload |

生产 `docker-compose.prod.yml` 增加：

| 服务 | 来源 | 对外端口 | 说明 |
|---|---|---|---|
| `web` | 本仓库 `Dockerfile` | 无直接发布 | FastAPI + Vue 静态资源 |
| `worker` | 本仓库 `Dockerfile` | 无 | Celery Worker |
| `beat` | 本仓库 `Dockerfile` | 无 | Celery Beat |
| `migrate` | 本仓库 `Dockerfile` | 无 | 执行 SQL migration 和健康检查 |
| `caddy` | `caddy:2-alpine` | 80/443 | Basic Auth + 反向代理 |
| `postgres` | `postgres:16` | 无公网端口 | PostgreSQL 权威存储 |
| `redis` | `redis:7-alpine` | 无公网端口 | Celery/Redis |
| `qdrant` | `qdrant/qdrant` | 无公网端口 | Qdrant 向量索引 |

---

## ConfigManager 组件管理

`ConfigManager` 是应用级线程安全单例，管理以下组件生命周期：

| 组件 | 工厂函数 | 实现类 |
|---|---|---|
| `document_store` | `create_document_store()` | `PostgresDocumentStore` |
| `vector_index` | `create_qdrant_vector_index()` | `QdrantVectorIndex` |
| `llm_client` | `create_llm_client()` | 4 种 LLM 客户端之一 |
| `embedding_client` | `create_embedding_client()` | `OpenAICompatibleEmbeddingClient` |
| `rerank_client` | `create_rerank_client()` | `OpenAICompatibleRerankClient` 或 `None` |
| `structured_extraction_client` | `create_structured_extraction_client()` | 结构化事实抽取客户端 |
| `chunking_service` | `create_chunking_service()` | `ChunkingService` |
| `intel_store` | `create_intel_store()` | `PostgresIntelStore` |
| `insight_store` | `create_insight_store()` | `PostgresInsightStore` |

`reload()` 读取最新 `.env`，按变更字段重建受影响组件。Qdrant URL、API key、collection、distance 或 vector size 变化会清空 `vector_index` 缓存；PostgreSQL DSN 变化会重建相关 Store；结构化抽取配置变化会重建 `structured_extraction_client`。

---

## AppConfig 基础设施字段

```python
class AppConfig(BaseSettings):
    pg_dsn: str = "postgresql://logos:logos@localhost:5432/logos"

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_documents_collection: str = "insightforge_documents_v1"
    qdrant_distance: str = "Cosine"
    vector_backend: str = "qdrant"

    embedding_vector_size: int = 1536  # Qdrant collection vector size

    chunk_max_child_tokens: int = 512
    chunk_target_parent_tokens: int = 1024
    chunk_overlap_tokens: int = 100

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
| LLM/Embedding/Rerank API 参数 | `.env` | 前端 ConfigView 通过 API 读写 |
| Qdrant/PostgreSQL/Redis | `.env` | 部署环境配置 |
| RSS 源列表 | `data/feeds_config.json` | 前端 SettingsView |
| 爬虫源列表 | `data/sites_config.json` | 前端 SettingsView |
| 调度参数 | `.env` | 前端 SettingsView / 部署配置 |
| 推送渠道 | `data/webhook_config.json` | 前端 WebhookView |
| 应用默认值 | `core/config.py` | pydantic Field default |
