# Logos 架构文档

> **项目阶段**：Demo+ （前后端分离架构 + ReAct Agent + 深度研究 + Web 搜索 + AI 摘要 + Rerank + 混合检索 RAG + Webhook 推送）

---

## 最近架构变更

| 时间 | 变更 | 摘要 |
|---|---|---|
| 2026-05 | Pipeline 抓取与任务反馈修复 | 前端异步任务轮询、RSS 并发抓取、Celery 自动重试 |
| 2026-05 | RAGAs 评估框架 | 三维度评估（检索质量 + 端到端问答 + Agent 工具调用），LLM-as-Judge |
| 2026-05 | pgvector 统一存储 | 移除 Qdrant，子 chunk 向量并入 PostgreSQL |
| 2026-05 | 混合检索 + RRF | 向量+关键词双通道 + jieba 中文分词 + Reciprocal Rank Fusion |
| 2026-05 | 父子分块 RAG | Markdown 感知分块，子 chunk→pgvector 检索，父 chunk→PostgreSQL 召回 |
| 2026-05 | 基础设施迁移 | SQLite→PostgreSQL, APScheduler→Celery+Redis, Docker Compose |
| 2026-05 | VPS 一键部署 | 新增应用镜像、生产 Compose、Caddy Basic Auth 与初始化迁移 |

→ 完整变更历史：[docs/design-docs/changelog.md](docs/design-docs/changelog.md)

---

## 1. 系统概览

Logos 是一个**个人 AI 新闻分析助手**，具备以下核心能力：

1. **定时 Pipeline**：自动从多个数据源（RSS + 网页爬取）抓取内容 → Markdown 转换 + 元数据提取 → 去重存储 → AI 摘要打标签 → 父子分块 + 向量化 + jieba 分词全文索引 → 每日自动生成新闻简报
2. **ReAct Agent 问答**：用户通过自然语言提问，ReAct Agent 自主推理并决策调用工具（语义检索、统计查询、全文阅读、Web 搜索、简报生成等），基于工具返回的真实数据生成回答
3. **深度研究**：Plan-Execute 深度研究模式，先生成研究计划供用户审阅，确认后 ReAct Agent 按计划执行多步研究任务，自动保存研究报告
4. **Web 搜索**：多搜索引擎并发搜索（DuckDuckGo + Tavily），程序化去重聚合
5. **NewsAPI 在线搜索**：代理 NewsAPI 接口，支持全球新闻搜索和热门头条
6. **Webhook 推送**：将新闻简报/研究报告通过 Webhook 推送到飞书、钉钉、企业微信、Telegram、ntfy 等平台
7. **Agent 工具系统**：完整的工具定义、注册、编排、执行基础设施 + 6 个内置工具 + ReAct 推理-行动循环核心
8. **RAGAs 评估**：基于 RAGAs 框架的三维度自动化评估（检索质量、端到端问答质量、Agent 工具调用准确性），支持自定义 OpenAI 兼容评判 LLM

当前系统为**前后端分离架构**（Vue 3 + FastAPI）。

---

## 2. 技术选型

| 模块 | 选型 | 一句话理由 |
|---|---|---|
| 后端语言 | Python 3.11+ | 后端全栈，AI 生态完善 |
| 前端 | Vue 3 + Vite 6 | 轻量 SPA，开发效率高 |
| Web 框架 | FastAPI + Uvicorn | 异步 REST + SSE 流式支持 |
| 元数据存储 | PostgreSQL 16 | 并发写入 + JSONB + tsvector 全文搜索 |
| 向量数据库 | PostgreSQL + pgvector | 单库持久化 + cosine 检索 |
| 任务调度 | Celery + Redis | 分布式异步执行 + Flower 监控 |
| LLM | openai/gemini/anthropic SDK | 4 种后端统一 Protocol |
| 检索 | HybridSearchService + RRF | 向量+关键词双通道融合 |
| 分块 | tiktoken + ChunkingService | Markdown 感知的父子分块 |
| 评估 | RAGAs + LLM-as-Judge | 三维度 RAG 质量自动化评估 |
| 日志 | structlog | 结构化 JSON + request_id 追踪 |

→ 完整选型论证与 ADR：[docs/design-docs/tech-decisions.md](docs/design-docs/tech-decisions.md)

---

## 3. 分层架构

```
┌────────────────────────────────────────────────────────────────────┐
│                        前端表现层 (Frontend)                        │
│   Vue 3 SPA: NewsView │ BriefView │ NewsApiView │ QueryView       │
│              WebhookView │ SettingsView │ ConfigView               │
│   通过 Axios 调用 /api/* 端点                                      │
├────────────────────────────────────────────────────────────────────┤
│                     后端表现层 (Delivery)                           │
│   FastAPI Server (server.py) — 9 个路由模块 + CLI 调试工具         │
├────────────────────────────────────────────────────────────────────┤
│                  Agent 智能体层 (Agent/React + Tools)                │
│   ReActAgent (推理-行动循环)  │  ToolRegistry (注册中心)           │
│   6 个内置工具               │  ToolChain / AsyncToolExecutor     │
│   三层记忆系统：核心记忆 + 持久记忆 + 会话记忆                      │
├────────────────────────────────────────────────────────────────────┤
│                     应用服务层 (Services)                           │
│   PipelineService │ QueryService │ BriefService │ WebhookService   │
│   SummaryService  │ WebSearchService │ DeepResearchService         │
├────────────────────────────────────────────────────────────────────┤
│                     领域模型层 (Models)                             │
│   ArticleEntity/DTO │ DailyBrief │ Chunk │ ParentChunk │ SearchResult │
├────────────────────────────────────────────────────────────────────┤
│                    基础设施层 (Infrastructure)                      │
│   PostgresArticleStore │ PgVectorStore │ ChunkingService        │
│   HybridSearchService  │ 4×LLMClient │ EmbeddingClient            │
│   NewsCollector │ WebCrawler │ WebSearchClients │ RerankClient     │
├────────────────────────────────────────────────────────────────────┤
│                    横切关注点 (Core)                                │
│   AppConfig │ Protocols │ Factory │ ConfigManager                    │
│   Exceptions │ Logging │ Retry                                     │
├────────────────────────────────────────────────────────────────────┤
│                     调度层 (Scheduler)                              │
│   Celery + Redis — Beat 定时触发 │ Worker 异步执行                 │
└────────────────────────────────────────────────────────────────────┘
```

**层间依赖规则**（严格单向）：
- Frontend → Delivery（HTTP API）
- Delivery → Agent/Tools → Services → Infrastructure
- Agent/Tools 通过 BaseTool 子类调用 Services 层
- Infrastructure 实现 Core/Protocols 定义的接口
- Models 是纯数据层，被所有层引用
- Core 被所有层引用

---

## 4. 目录结构

```
Logos/
├── core/                           # 横切关注点
│   ├── config.py                   # AppConfig (pydantic-settings)
│   ├── config_manager.py           # ConfigManager 热重载单例
│   ├── protocols.py                # Protocol 接口契约
│   ├── factory.py                  # 工厂函数
│   ├── exceptions.py               # 统一异常层次
│   ├── logging.py                  # structlog 配置
│   └── retry.py                    # @with_retry 指数退避
│
├── models/                         # 领域模型 (纯 dataclass)
│   ├── article.py                  # ArticleEntity + ArticleDTO + Mapper
│   ├── agent_session.py            # 通用 Agent 会话 + 深度研究 todo
│   ├── memory.py                   # 三层记忆系统数据模型
│   ├── brief.py                    # DailyBrief
│   ├── chunk.py                    # Chunk + ParentChunk
│   └── search.py                   # SearchQuery + SearchResult + ChunkSearchResult
│
├── infrastructure/                 # 基础设施层 (实现 Protocol)
│   ├── collector.py                # NewsCollector (feedparser + trafilatura)
│   ├── postgres_article_store.py   # PostgresArticleStore
│   ├── agent_session_store.py      # 通用 Agent session: PostgreSQL + Redis
│   ├── memory_store.py             # 核心记忆 + 持久记忆 PostgreSQL 存储
│   ├── pgvector_store.py           # PgVectorStore (chunk 级别)
│   ├── chunking_service.py         # ChunkingService (Markdown 父子分块)
│   ├── keyword_search_service.py   # KeywordSearchService (PostgreSQL FTS)
│   ├── hybrid_search_service.py    # HybridSearchService (RRF 混合检索)
│   ├── llm_client.py               # 4 个 LLM 客户端
│   ├── embedding_client.py         # OpenAICompatibleEmbeddingClient
│   ├── rerank_client.py            # OpenAICompatibleRerankClient
│   ├── markdown_converter.py       # NewsMarkdownConverter
│   ├── web_crawler.py              # WebCrawler (Crawlee)
│   └── web_search_client.py        # DuckDuckGo + Tavily
│
├── services/                       # 应用服务层
│   ├── pipeline_service.py         # 抓取→存储→摘要→分块→向量化
│   ├── query_service.py            # ReAct Agent 问答入口
│   ├── memory_service.py           # 三层记忆上下文构建与会话压缩
│   ├── brief_service.py            # 日报生成
│   ├── webhook_service.py          # 多平台推送
│   ├── summary_service.py          # AI 批量摘要
│   ├── web_search_service.py       # 多引擎并发搜索
│   └── deep_research_service.py    # 深度研究报告
│
├── agent/                          # Agent 智能体层
│   ├── react/                      # ReAct 推理-行动循环
│   │   ├── agent.py                # ReActAgent + AgentEvent + AgentResult
│   │   ├── parser.py               # LLM 输出解析器
│   │   └── prompts.py              # System prompt 模板
│   └── tools/                      # 工具系统
│       ├── base.py                 # BaseTool 抽象基类
│       ├── registry.py             # ToolRegistry 线程安全单例
│       ├── chain.py                # ToolChain 链式编排
│       ├── executor.py             # AsyncToolExecutor
│       └── builtin/                # 6 个内置工具
│
├── delivery/                       # 后端表现层
│   ├── server.py                   # FastAPI 应用入口
│   ├── cli.py                      # CLI 调试工具
│   └── api/                        # 9 个路由模块
│
├── scheduler/                      # 调度层 (Celery)
│   ├── celery_app.py               # Celery 配置 + Beat 规则
│   └── tasks.py                    # 异步任务定义
│
├── frontend/                       # Vue 3 前端
│   └── src/
│       ├── views/                  # 7 个页面组件
│       ├── components/             # 通用组件
│       └── api/                    # Axios API 封装
│
├── docs/                           # 项目文档
│   ├── design-docs/                # 详细设计文档
│   ├── exec-plans/                 # 执行计划 (active/ + completed/)
│   ├── generated/                  # 生成文档 (DB Schema 等)
│   ├── product-specs/              # 产品规格 (API 参考等)
│   ├── references/                 # 参考资料 (外部依赖等)
│   ├── DESIGN.md                   # 设计哲学概述
│   └── PLANS.md                    # 开发路线图
│
├── evals/                          # RAGAs 评估模块
│   ├── config.py                  # 评判 LLM 配置加载
│   ├── adapters.py                # Logos 数据 → RAGAs Sample 转换
│   ├── metrics.py                 # 三维度指标预设
│   ├── runner.py                  # LogosEvalRunner 评估编排
│   ├── eval_config.json           # 评判 LLM 配置（OpenAI 兼容）
│   ├── datasets/                  # 评估数据集（黄金 QA + 合成）
│   ├── results/                   # 评估结果输出
│   └── scripts/                   # CLI: run_eval.py + generate_testset.py
│
├── tests/                          # 测试
├── data/                           # 运行时数据 (.gitignore)
├── output/                         # 日报 + 研究报告
├── Dockerfile                      # 应用镜像（Vue 构建 + Python 运行时）
├── docker-compose.yml              # 本地基础设施容器编排
├── docker-compose.prod.yml         # VPS 生产编排
├── Caddyfile                       # 生产反向代理 + Basic Auth
├── ARCHITECTURE.md                 # 本文档
└── AGENTS.md                       # AI 编码助手上下文
```

---

## 5. 核心接口契约 (Protocol)

系统通过 `typing.Protocol` 定义接口，实现基础设施层与服务层的可替换性：

| Protocol | 核心方法 | 当前实现 |
|---|---|---|
| `ArticleStoreProtocol` | `save_articles`, `get_unembedded`, `mark_embedded`, `search_by_keyword`, `get_recent`, `get_stats`, `cleanup_old_articles` | `PostgresArticleStore` |
| `VectorStoreProtocol` | `add_chunks`, `search_chunks`, `delete_by_article_ids` | `PgVectorStore` |
| `LLMClientProtocol` | `generate`, `generate_stream`, `generate_with_history`, `generate_with_history_stream` | 4 个客户端 |
| `EmbeddingClientProtocol` | `embed` | `OpenAICompatibleEmbeddingClient` |
| `RerankClientProtocol` | `rerank` | `OpenAICompatibleRerankClient` |
| `AgentSessionStoreProtocol` | `create_general_session`, `create_session`, `append_event`, `append_message`, `update_summary` | `AgentSessionStore` |
| `MemoryStoreProtocol` | `get_active_core_memories`, `list_memory_index`, `create_persistent_memory` | `MemoryStore` |
| `WebhookServiceProtocol` | `broadcast`, `send_to_channel`, `load_channels`, `get_auto_push` | `WebhookService` |

→ 完整接口设计与实现说明：[docs/design-docs/protocol-contracts.md](docs/design-docs/protocol-contracts.md)

---

## 6. 数据流架构

### 6.1 Pipeline 数据流（定时/手动触发）

```
数据源 (RSS + 网页爬虫)
    → NewsCollector.fetch_all() 并发 RSS 抓取 + WebCrawler.crawl_all()
    → NewsMarkdownConverter.convert_batch()     HTML→Markdown
    → PostgresArticleStore.save_articles()      SHA256 去重
    → SummaryService.summarize_pending()        LLM 摘要+标签
    → ChunkingService.chunk_articles()          父子分块
    → EmbeddingClient.embed()                   子 chunk 向量化
    → PgVectorStore.add_chunks()                写入 PostgreSQL child_chunks
    → PostgresArticleStore.save_parent_chunks() 写入 PostgreSQL parent_chunks
    → mark_embedded()                            完成
```

### 6.2 ReAct Agent 问答数据流

```
用户问题 → QueryService.answer_agent_stream()
    → AgentSessionStore.create_general_session()/get_session()
    → MemoryService.build_memory_context()
    → ReActAgent.run_stream(question)
    → while steps < max_steps:
        → LLM.generate_with_history(messages)
        → ReActParser.parse() → Thought / Action / Answer
        → [Action] → ToolRegistry.get(tool).execute(**params)
        → yield AgentEvent → SSE 传输到前端
```

### 6.3 混合检索数据流

```
查询 → ┌─ 向量检索: Embedding → pgvector search_chunks → 子→父去重排名
       └─ 关键词检索: jieba 分词 → PostgreSQL tsvector @@ query
       → RRF 融合 (k=60, 加权)
       → PostgreSQL get_parent_chunks_by_ids()
       → [可选] Rerank 精排
       → 最终 top_k 父 chunks → LLM
```

**检索模式**：`hybrid`（默认）| `semantic` | `keyword`
**降级策略**：任一通道失败 → 使用另一通道 → 双失败 → 回退文章级 ILIKE

### 6.4 简报生成 + 推送

```
触发 → BriefService.generate(hours=24)
     → get_recent() → 格式化 context → LLM 生成 → 保存 .md
     → [auto_push?] → WebhookService.broadcast()
     → 飞书/钉钉/企业微信/Telegram/ntfy
```

### 6.5 深度研究

```
研究主题 → PlanExecuteRunner.generate_plan() → 用户审阅确认
         → PlanExecuteRunner.execute() → MemoryService.build_memory_context()
         → ReActAgent (max_steps=15)
         → 多步: 搜知识库 → 读全文 → Web 搜索 → 综合报告
         → DeepResearchService 自动保存 output/research/
```

### 6.6 三层记忆系统

```
core_memory_revisions(active)
    + persistent_memories(active → MEMORY 索引)
    + agent_sessions.summary
    → 注入普通问答 / 深度研究 Agent system prompt
```

- 核心记忆：全局 Agent 工作规则、工具说明、摘要模板，采用版本化 revision，不物理删除。
- 持久记忆：`user` / `feedback` / `project` 三类跨会话记忆，默认 `pending`，用户确认后进入 MEMORY 索引。
- 会话记忆：普通问答和深度研究共用 `agent_sessions`；达到 10k token 后开始摘要，后续每 5k token 更新，失败 3 次后退避为 10k。

→ 完整 API 路由参考：[docs/product-specs/api-reference.md](docs/product-specs/api-reference.md)

---

## 7. 数据模型

### 核心实体关系

```
Article (1) ──→ (N) Chunk (子分块, PostgreSQL/pgvector)
Article (1) ──→ (N) ParentChunk (父分块, PostgreSQL)
Chunk (N)   ──→ (1) ParentChunk (通过 parent_chunk_id)
```

| 实体 | 存储 | 用途 |
|---|---|---|
| `ArticleEntity` / `ArticleDTO` | PostgreSQL `articles` | 文章元数据 + 全文 |
| `ParentChunk` | PostgreSQL `parent_chunks` | LLM 召回上下文 + 全文索引 |
| `Chunk` | PostgreSQL `child_chunks` | 向量检索单元 |

→ 完整 Schema 与 DDL：[docs/generated/dbdoc/](docs/generated/dbdoc/) (tbls 自动生成)
→ 业务规则补充：[docs/generated/db-schema.md](docs/generated/db-schema.md)

---

## 8. 配置管理

| 配置项 | 存储位置 | 管理方式 |
|---|---|---|
| LLM/Embedding/Rerank API | `.env` | 前端 ConfigView 通过 API 读写 |
| RSS 源列表 | `data/feeds_config.json` | `core/source_config.py` 读写，前端 SettingsView 管理 |
| 爬虫源列表 | `data/sites_config.json` | `core/source_config.py` 读写，前端 SettingsView 管理 |
| 推送渠道 | `data/webhook_config.json` | 前端 WebhookView |
| 应用默认值 | `core/config.py` | pydantic Field default |

→ 完整字段参考：[docs/references/external-deps.md](docs/references/external-deps.md)

---

## 9. 异常层次

```
NewsAssistantError (基础异常)
├── CollectorError → SourceUnavailableError
├── StoreError
├── EmbeddingError
├── RerankError
├── LLMError → RateLimitError
├── ConfigError
└── ToolError
    ├── ToolNotFoundError
    ├── ToolValidationError
    ├── ToolExecutionError
    ├── ToolTimeoutError
    └── ToolChainError
```

所有外部调用通过 `@with_retry` 自动指数退避重试（默认 3 次，基数 2.0）。

---

## 10. 进程模型

```
=== 本地开发基础设施层 (docker compose up -d) ===
  容器 1: logos-postgres  (:5432)  — 文章 + 父/子 chunk + 向量 + 全文索引
  容器 2: logos-redis     (:6379)  — Celery Broker

=== 应用层 (start_dev.bat) ===
  进程 1: FastAPI Server  (:8005)  — 处理 /api/* 请求
  进程 2: Celery Worker            — 异步任务执行
  进程 3: Celery Beat              — 定时触发
  进程 4: Vite Dev Server (:5173)  — 前端开发（开发模式）
```

进程间数据共享：PostgreSQL + 文件系统。

生产部署使用 `docker-compose.prod.yml`：

```
公网 80/443
  → caddy (Basic Auth + reverse proxy)
  → web    (FastAPI + Vue 静态资源, :8005)

migrate  一次性初始化 PostgreSQL schema + migrations/*.sql
worker   Celery Worker 执行 Pipeline / Brief / Cleanup
beat     Celery Beat 定时投递任务
postgres PostgreSQL 16 + pgvector
redis    Celery Broker / Result Backend
flower   可选 monitoring profile
```

生产环境只发布 Caddy 端口；PostgreSQL、Redis、Web、Worker、Beat 默认不直接暴露到公网。`.env` 作为共享绑定文件挂载到 `/app/.env`，`data/` 和 `output/` 使用 Docker Named Volumes 持久化。

---

## 11. 依赖注入

系统使用**工厂函数**（`core/factory.py`）+ **ConfigManager 单例**：

```python
# 基础设施层工厂函数 (8 个)
create_article_store(config)      → PostgresArticleStore
create_agent_session_store(config) → AgentSessionStore
create_memory_store(config)       → MemoryStore
create_vector_store(config)       → PgVectorStore
create_llm_client(config)         → LLMClient (按 provider 选择)
create_embedding_client(config)   → OpenAICompatibleEmbeddingClient
create_rerank_client(config)      → RerankClient | None
create_summary_llm_client(config) → LLMClient (可复用主 LLM)
create_chunking_service(config)   → ChunkingService

# Service 层工厂函数 (4 个)
create_webhook_service()          → WebhookService
create_deep_research_service()    → DeepResearchService
create_query_service(config, mgr) → QueryService (含 MemoryService)
create_memory_service(mgr)        → MemoryService

# ConfigManager 缓存全部实例，reload() 支持热重载
# Service 层使用懒加载，依赖的基础设施变更时自动清空缓存
```

→ Agent 智能体层详细设计：[docs/design-docs/react-agent.md](docs/design-docs/react-agent.md)

---

## 12. 当前已知局限性

| 局限 | 影响 | 改进方向 |
|---|---|---|
| 单环境 .env | 无 dev/prod 区分 | 多环境 .env |
| 无认证/授权 | API 完全开放 | 认证中间件 |
| structlog 已引入但部分模块待迁移 | 日志格式不统一 | 全局迁移 |

→ 完整问题清单：[docs/exec-plans/tech-debt-tracker.md](docs/exec-plans/tech-debt-tracker.md)

---

## 13. 运行方式

```bash
# 1. 安装依赖
pip install -r requirements.txt
cd frontend && pnpm install && cd ..

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 3. 启动基础设施
docker compose up -d

# 4. 一键启动所有服务 (Windows)
./start_dev.bat

# 或分别启动:
python -m delivery.server              # 后端
cd frontend && pnpm dev                # 前端
celery -A scheduler.celery_app worker -l info -P threads  # Worker
celery -A scheduler.celery_app beat -l info                # Beat

# CLI 调试
python -m delivery.cli pipeline
python -m delivery.cli ask "今天有什么重要新闻？"
python -m delivery.cli stats
```

### 13.1 VPS 生产部署

```bash
cp .env.deploy.example .env
# 编辑 .env，至少设置 CADDY_DOMAIN、BASIC_AUTH_USER、BASIC_AUTH_HASH、POSTGRES_PASSWORD、PG_DSN 和各类 API Key
docker compose -f docker-compose.prod.yml up -d --build
```

详细部署、备份、升级和清空重建步骤见 [docs/deployment/docker-vps.md](docs/deployment/docker-vps.md)。

---

## 14. RAGAs 评估框架

系统集成了 [RAGAs](https://docs.ragas.io/) 框架，对 AI 能力进行三维度自动化评估，采用 LLM-as-Judge 原理：

### 14.1 评估维度

| 维度 | 评估对象 | 核心指标 | 数据模型 |
|---|---|---|---|
| ① 检索质量 | `HybridSearchService` | Context Precision, Context Recall, Noise Sensitivity | `SingleTurnSample` |
| ② 端到端问答 | `QueryService` → `ReActAgent` | Faithfulness, Response Relevancy | `SingleTurnSample` |
| ③ Agent 工具调用 | `ReActAgent` 多步推理 | ToolCallAccuracy, AgentGoalAccuracy | `MultiTurnSample` |

### 14.2 评估数据流

```
黄金数据集 (golden_qa.json)
    ↓ 对每个 question
    ├── HybridSearchService.search()     → retrieved_contexts
    └── QueryService.answer_agent()      → response + AgentEvent[]
    ↓ adapters.py 转换
    ├── SingleTurnSample (维度 ①②)
    └── MultiTurnSample  (维度 ③)
    ↓ ragas.evaluate()
    → 评估报告 JSON (evals/results/)
```

### 14.3 评判 LLM 配置

通过 `evals/eval_config.json` 配置评判 LLM，支持 OpenAI 兼容的自定义端点：

```json
{
  "judge_llm": {
    "model": "gpt-4o-mini",
    "base_url": "https://api.openai.com/v1",
    "api_key_env": "OPENAI_API_KEY"
  }
}
```

### 14.4 使用方式

```bash
# 安装评估依赖（独立于生产依赖）
pip install -r requirements-eval.txt

# 运行全量评估
python -m evals.scripts.run_eval --suite all

# 单维度评估
python -m evals.scripts.run_eval --suite retrieval
python -m evals.scripts.run_eval --suite e2e
python -m evals.scripts.run_eval --suite agent

# 从知识库文章生成合成测试集
python -m evals.scripts.generate_testset --count 50 --size 30
```
