# 架构变更历史

> **来源**：从 [ARCHITECTURE.md](../../ARCHITECTURE.md) 顶部"最近架构升级"迁出的完整变更记录。

---

## 2026-05 架构升级

本项目在 2026 年 5 月进行了底层核心基础设施的迁移与升级。

### 1. 关系型数据库迁移 (SQLite → PostgreSQL)

- 弃用了单文件锁机制的 SQLite (`SQLiteArticleStore`)。
- 引入了 `PostgresArticleStore`，利用 `psycopg2-binary` 建立同步连接。
- 使用 `INSERT ... ON CONFLICT DO NOTHING` 实现更安全的并发去重。
- 文章标签等 JSON 数据使用 Postgres 原生 `JSONB` 格式存储。

### 2. 向量数据库迁移 (ChromaDB → Qdrant Cloud → pgvector)

- 弃用了本地化、难以集群扩展的 ChromaDB。
- 曾引入独立向量数据库 `QdrantVectorStore`。
- 当前改为 `PgVectorStore`，通过 PostgreSQL `pgvector` 承载子 chunk embedding，减少独立基础设施和跨库一致性风险。

### 3. 异步任务队列升级 (APScheduler → Celery + Redis)

- 弃用了随应用启动的本地 `APScheduler` 单进程定时器。
- 引入了基于 `Celery` 和 `Redis` 的分布式异步任务架构。
- 通过 `Celery Beat` 进行定时触发调度，通过 `Celery Worker` 执行实际耗时任务。
- 将 `/api/news/pipeline` 和 `/api/briefs/generate` 接口改为异步执行并返回 `task_id`。

### 4. 父子分块 RAG 架构 (整篇文章 Embedding → Parent-Child Chunking)

- 弃用了整篇文章级别的 Embedding + 检索方式。
- 引入 `ChunkingService`，按 Markdown 章节结构将文章拆分为**子 chunk (≤512 token)** 用于向量检索，组装**父 chunk (~1024 token)** 用于 LLM 召回上下文。
- 子 chunk 存储在 PostgreSQL `child_chunks` 表，父 chunk 存储在 PostgreSQL `parent_chunks` 表。
- `VectorStoreProtocol` 重构为 chunk 级别接口 (`add_chunks` / `search_chunks` / `delete_by_article_ids`)。
- 使用 `tiktoken` (cl100k_base) 精确计算 token 数。

### 5. 混合检索 (纯向量检索 → 向量 + 关键词 + RRF 融合)

- 弃用了仅依赖向量语义搜索的单通道检索方式。
- 在 PostgreSQL `parent_chunks` 表上新增 `search_vector` (`tsvector`) 列 + GIN 索引。
- 使用应用层 `jieba` 分词实现中文全文检索支持。
- 引入 `HybridSearchService`，编排向量检索 + 关键词检索两路并行，通过 **RRF** 算法融合排名。
- 支持三种检索模式（hybrid/semantic/keyword）、优雅降级。

### 6. 基础设施容器化 (手动安装 → Docker Compose)

- 引入 `docker-compose.yml`，一条命令启动全部基础设施。
- PostgreSQL 16 + pgvector、Redis 7 使用 Docker Named Volumes 持久化数据。
- 所有容器配置 `healthcheck`。
- `start_dev.bat` 自动调用 `docker compose up -d`。

### 7. 日志系统升级 (logging → structlog)

- 替换标准 `logging` 为 `structlog`，实现结构化 JSON 日志。
- 集成 `StructlogMiddleware` 实现请求级 `request_id` 追踪。
- Celery 信号自动绑定 `task_id`/`task_name` 上下文。

> 上述升级遵循 `Protocol` 接口设计，在基础设施层实现了无缝替换。
