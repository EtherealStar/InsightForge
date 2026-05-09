# Logos 当前架构文档

> **项目阶段**：Demo+ （前后端分离架构 + ReAct Agent + 深度研究 + Web 搜索 + AI 摘要 + Rerank + 混合检索 RAG + Webhook 推送）

---

## 最近架构升级 (2026-05)

本项目近期进行了底层核心基础设施的迁移与升级，主要更新内容如下：

1. **关系型数据库迁移 (SQLite → PostgreSQL)**
   - 弃用了单文件锁机制的 SQLite (`SQLiteArticleStore`)。
   - 引入了 `PostgresArticleStore`，利用 `psycopg2-binary` 建立同步连接。
   - 使用 `INSERT ... ON CONFLICT DO NOTHING` 实现更安全的并发去重。
   - 文章标签等 JSON 数据使用 Postgres 原生 `JSONB` 格式存储。

2. **向量数据库迁移 (ChromaDB → Qdrant Cloud)**
   - 弃用了本地化、难以集群扩展的 ChromaDB。
   - 引入了高性能向量数据库 `QdrantVectorStore`。
   - 利用 `qdrant-client` 自动创建 Cosine 集合，并支持 Payload 过滤检索。

3. **异步任务队列升级 (APScheduler → Celery + Redis)**
   - 弃用了随应用启动的本地 `APScheduler` 单进程定时器。
   - 引入了基于 `Celery` 和 `Redis` 的分布式异步任务架构。
   - 通过 `Celery Beat` 进行定时触发调度，通过 `Celery Worker` 执行实际耗时任务。
   - 将 `/api/news/pipeline` 和 `/api/briefs/generate` 接口改为异步执行并返回 `task_id`。

4. **父子分块 RAG 架构 (整篇文章 Embedding → Parent-Child Chunking)**
   - 弃用了整篇文章级别的 Embedding + 检索方式。
   - 引入 `ChunkingService`，按 Markdown 章节结构将文章拆分为**子 chunk (≤512 token)** 用于向量检索，组装**父 chunk (~1024 token)** 用于 LLM 召回上下文。
   - 子 chunk 存储在 Qdrant `news_chunks` collection，父 chunk 存储在 PostgreSQL `parent_chunks` 表（零冗余）。
   - `VectorStoreProtocol` 重构为 chunk 级别接口 (`add_chunks` / `search_chunks` / `delete_by_article_ids`)。
   - 使用 `tiktoken` (cl100k_base) 精确计算 token 数。

5. **混合检索 (纯向量检索 → 向量 + 关键词 + RRF 融合)**
   - 弃用了仅依赖向量语义搜索的单通道检索方式。
   - 在 PostgreSQL `parent_chunks` 表上新增 `search_vector` (`tsvector`) 列 + GIN 索引，实现关键词全文搜索。
   - 使用应用层 `jieba` 分词实现中文全文检索支持，写入时自动生成分词后的 `tsvector`。
   - 引入 `HybridSearchService`，编排向量检索 + 关键词检索两路并行，通过 **Reciprocal Rank Fusion (RRF)** 算法融合排名。
   - 检索流程：向量搜子 chunk → 去重为父 chunk 排名 ‖ 关键词搜父 chunk → RRF 融合 → 可选 Rerank 精排 → 返回 LLM。
   - 支持加权 RRF、三种检索模式（hybrid/semantic/keyword）、优雅降级。

6. **基础设施容器化 (手动安装 → Docker Compose)**
   - 弃用了需要手动安装和配置的本地 PostgreSQL、Qdrant、Redis。
   - 引入 `docker-compose.yml`，一条命令 (`docker compose up -d`) 启动全部基础设施。
   - PostgreSQL 16、Qdrant、Redis 7 统一使用 Docker Named Volumes 持久化数据。
   - 所有容器配置 `healthcheck`，确保服务就绪后才可用。
   - `start_dev.bat` 自动调用 `docker compose up -d`，无需手动管理基础设施。

> 上述升级遵循 `Protocol` 接口设计，在基础设施层实现了无缝替换。父子分块升级重构了 `VectorStoreProtocol` 接口，混合检索升级扩展了 `ArticleStoreProtocol` 接口，同步更新了所有调用方。

---

## 1. 系统概览

Logos 是一个**个人 AI 新闻分析助手**，具备以下核心能力：

1. **定时 Pipeline**：自动从多个数据源（RSS + 网页爬取）抓取内容 → Markdown 转换 + 元数据提取 → 去重存储 → AI 摘要打标签 → 父子分块 + 向量化 + jieba 分词全文索引 → 每日自动生成新闻简报
2. **ReAct Agent 问答**：用户通过自然语言提问，ReAct Agent 自主推理并决策调用工具（语义检索、统计查询、全文阅读、Web 搜索、简报生成等），基于工具返回的真实数据生成回答
3. **深度研究**：专用深度研究模式，Agent 使用更多推理步数（max_steps=15）执行多步研究任务，自动保存研究报告
4. **Web 搜索**：多搜索引擎并发搜索（DuckDuckGo + Tavily），程序化去重聚合
5. **NewsAPI 在线搜索**：代理 NewsAPI 接口，支持全球新闻搜索和热门头条
6. **Webhook 推送**：将新闻简报/研究报告通过 Webhook 推送到飞书、钉钉、企业微信、Telegram、ntfy 等平台
7. **Agent 工具系统**：完整的工具定义、注册、编排、执行基础设施 + 6 个内置工具 + ReAct 推理-行动循环核心

当前系统为**前后端分离架构**（Vue 3 + FastAPI）。

---

## 2. 技术选型总览

| 模块 | 当前选型 | 说明 |
|---|---|---|
| **语言** | Python 3.11+ | 后端全栈 |
| **前端框架** | Vue 3 + Vue Router 4 + Vite 6 | SPA 单页应用 |
| **HTTP 客户端** | Axios | 前端 API 调用 |
| **Markdown 渲染** | marked | 前端简报渲染 |
| **Web 框架** | FastAPI + Uvicorn | RESTful API 服务 |
| **新闻抓取** | feedparser + trafilatura | RSS 解析 + 正文提取 |
| **网页爬取** | Crawlee (BeautifulSoupCrawler) | 基于 Crawlee 的网页爬取 |
| **HTML→Markdown** | markdownify + BeautifulSoup | HTML 正文提取 + Markdown 转换 |
| **元数据存储** | PostgreSQL | 关系型数据库，支持并发和高级索引 |
| **向量存储** | Qdrant | 高性能向量数据库 (chunk 级别) |
| **分块** | tiktoken + 自研 ChunkingService | Markdown 感知的父子分块 |
| **中文分词** | jieba | 应用层分词，供 PostgreSQL FTS 使用 |
| **混合检索** | 自研 HybridSearchService + RRF | 向量+关键词双通道 + Reciprocal Rank Fusion |
| **LLM 调用** | openai / google-genai / anthropic SDK | 四种后端：OpenAI Compatible, OpenAI, Gemini, Claude |
| **Embedding** | openai SDK（自定义端点） | OpenAI 格式兼容 API |
| **Rerank** | Jina/SiliconFlow 兼容 API | 可选的 Cross-Encoder 重排序 |
| **Web 搜索** | duckduckgo-search + tavily-python | DuckDuckGo 免费 + Tavily 付费 |
| **NewsAPI** | requests 代理 | newsapi.org API 代理 |
| **任务调度** | Celery + Redis | 分布式任务队列，Beat 定时触发 + Worker 异步执行 |
| **配置管理** | pydantic-settings + .env | 类型校验 + 环境变量加载 |
| **测试** | pytest | 单元测试 + 集成测试 |

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
│   FastAPI Server (server.py)                                       │
│   ├── news_router    ─ /api/news/*      新闻 CRUD + Pipeline       │
│   ├── brief_router   ─ /api/briefs/*    简报列表/查看/生成(+推送)  │
│   ├── query_router   ─ /api/query/*     ReAct Agent 问答 (SSE)     │
│   ├── research_router─ /api/research/*  深度研究 (SSE + 报告 CRUD) │
│   ├── newsapi_router ─ /api/newsapi/*   NewsAPI 代理 + 文章保存    │
│   ├── webhook_router ─ /api/webhook/*   推送渠道管理 + 消息推送    │
│   ├── config_router  ─ /api/config/*    .env 配置读写              │
│   ├── settings_router─ /api/settings/*  RSS 源 + 爬虫源 + 调度参数 │
│   └── health         ─ /api/health      健康检查                   │
│                                                                    │
│   CLI (cli.py) — 调试工具                                          │
├────────────────────────────────────────────────────────────────────┤
│                  Agent 智能体层 (Agent/React + Tools)                │
│   ReActAgent (推理-行动循环)  │  ReActParser (输出解析器)          │
│   BaseTool (抽象基类)        │  ToolRegistry (注册中心)           │
│   builtin/ (6 个内置工具)    │  ToolChain / AsyncToolExecutor    │
│   ReAct Agent 自主推理 → 调用工具 → 观察结果 → 生成回答            │
│   Agent 通过 Tools 调用 Services / Infrastructure 层               │
├────────────────────────────────────────────────────────────────────┤
│                     应用服务层 (Services)                           │
│   PipelineService    │ QueryService       │ BriefService           │
│   WebhookService     │ SummaryService     │ WebSearchService       │
│   DeepResearchService                                              │
│   编排基础设施组件，不直接操作数据库或外部 API                       │
├────────────────────────────────────────────────────────────────────┤
│                     领域模型层 (Models)                             │
│   Article (dataclass) │ DailyBrief │ SearchQuery │ SearchResult    │
│   Chunk │ ParentChunk │ ChunkSearchResult                          │
│   Language │ ArticleStatus                                         │
│   纯数据定义，无 I/O 依赖                                          │
├────────────────────────────────────────────────────────────────────┤
│                    基础设施层 (Infrastructure)                      │
│   NewsCollector         │  PostgresArticleStore │ QdrantVectorStore  │
│   ChunkingService (Markdown 父子分块)                                │
│   KeywordSearchService │ HybridSearchService (RRF 融合)             │
│   OpenAI*/Gemini*/Anthropic*Client              │ EmbeddingClient  │
│   OpenAICompatibleRerankClient                  │ WebCrawler       │
│   NewsMarkdownConverter │  DuckDuckGo/TavilySearchClient           │
│   实现 core/protocols.py 中定义的 Protocol 接口                    │
├────────────────────────────────────────────────────────────────────┤
│                    横切关注点 (Core)                                │
│   AppConfig (pydantic-settings)  │  Protocols (5 个接口契约)       │
│   ConfigManager (热重载单例)     │  Factory (8 个工厂函数)         │
│   Exceptions (异常层次)          │  Logging (统一日志)             │
│   Retry (指数退避重试)                                             │
├────────────────────────────────────────────────────────────────────┤
│                     调度层 (Scheduler)                              │
│   Celery + Redis — 分布式任务队列                                  │
│   Celery Beat 定时触发 │ Celery Worker 异步执行                    │
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
│   ├── __init__.py
│   ├── config.py                   # AppConfig (pydantic-settings)
│   ├── config_manager.py           # ConfigManager 热重载单例
│   ├── protocols.py                # 5 个 Protocol 接口契约 (+全文搜索扩展)
│   ├── factory.py                  # 8 个工厂函数 + 混合检索服务构造
│   ├── exceptions.py               # 统一异常层次
│   ├── logging.py                  # logging 标准库配置
│   └── retry.py                    # @with_retry 指数退避装饰器
│
├── models/                         # 领域模型 (纯 dataclass)
│   ├── __init__.py
│   ├── article.py                  # Article + Language + ArticleStatus
│   ├── brief.py                    # DailyBrief
│   ├── chunk.py                    # Chunk (子分块) + ParentChunk (父分块)
│   └── search.py                   # SearchQuery + SearchResult + ChunkSearchResult
│
├── infrastructure/                 # 基础设施层
│   ├── __init__.py
│   ├── collector.py                # NewsCollector (feedparser + trafilatura)
│   ├── postgres_article_store.py   # PostgresArticleStore
│   ├── qdrant_vector_store.py      # QdrantVectorStore (chunk 级别)
│   ├── chunking_service.py         # ChunkingService (Markdown 父子分块)
│   ├── keyword_search_service.py   # KeywordSearchService (PostgreSQL FTS)
│   ├── hybrid_search_service.py    # HybridSearchService (RRF 混合检索)
│   ├── llm_client.py               # 4 个 LLM 客户端实现
│   ├── embedding_client.py         # OpenAICompatibleEmbeddingClient
│   ├── rerank_client.py            # OpenAICompatibleRerankClient
│   ├── markdown_converter.py       # NewsMarkdownConverter (HTML→Markdown)
│   ├── web_crawler.py              # WebCrawler (Crawlee BeautifulSoupCrawler)
│   └── web_search_client.py        # DuckDuckGoSearchClient + TavilySearchClient
│
├── services/                       # 应用服务层
│   ├── __init__.py
│   ├── pipeline_service.py         # PipelineService (抓取→Markdown→存储→摘要→分块→向量化)
│   ├── query_service.py            # QueryService (RAG 检索+回答 + ReAct Agent)
│   ├── brief_service.py            # BriefService (日报生成)
│   ├── webhook_service.py          # WebhookService (多平台推送)
│   ├── summary_service.py          # SummaryService (AI 批量摘要+打标签)
│   ├── web_search_service.py       # WebSearchService (多引擎并发+去重)
│   └── deep_research_service.py    # DeepResearchService (深度研究报告)
│
├── agent/                          # Agent 智能体层
│   ├── __init__.py
│   ├── react/                      # ReAct 推理-行动循环
│   │   ├── __init__.py             # 公开 API (ReActAgent, AgentEvent 等)
│   │   ├── agent.py                # ReActAgent 核心循环 + AgentEvent + AgentResult
│   │   ├── parser.py               # LLM 输出解析器 (batch + streaming)
│   │   └── prompts.py              # ReAct system prompt 模板 (通用/深度研究/简报)
│   └── tools/                      # 工具系统
│       ├── __init__.py             # 公开 API
│       ├── base.py                 # BaseTool 抽象基类 + ToolParameter + ToolResult
│       ├── registry.py             # ToolRegistry 线程安全单例 + @register_tool
│       ├── chain.py                # ToolChain 链式编排 + $prev 管道传参
│       ├── executor.py             # AsyncToolExecutor 异步执行器
│       ├── errors.py               # 工具层异常层次 (5 个子类)
│       └── builtin/                # 内置工具集 (6 个已实现)
│           ├── __init__.py         # register_builtin_tools() 注册函数
│           ├── query_knowledge_base.py  # 语义检索工具 (支持 Rerank 精排)
│           ├── get_recent_news.py  # 最近新闻工具
│           ├── get_news_stats.py   # 统计信息工具
│           ├── generate_brief.py   # 简报生成工具
│           ├── read_article.py     # 全文阅读工具 (深度研究用)
│           └── web_search.py       # Web 搜索工具 (DuckDuckGo+Tavily)
│
├── delivery/                       # 后端表现层
│   ├── __init__.py
│   ├── server.py                   # FastAPI 应用入口
│   ├── cli.py                      # CLI 调试工具
│   └── api/                        # FastAPI 路由模块
│       ├── __init__.py
│       ├── news_router.py          # 新闻 CRUD + Pipeline 触发
│       ├── brief_router.py         # 简报管理 (+自动推送联动)
│       ├── query_router.py         # ReAct Agent 问答 (SSE 结构化事件流)
│       ├── research_router.py      # 深度研究 (SSE + 报告 CRUD + 导出/推送)
│       ├── newsapi_router.py       # NewsAPI 代理 (everything/top-headlines/save)
│       ├── config_router.py        # .env 配置管理
│       ├── settings_router.py      # RSS 源 + 爬虫源 + 调度参数管理
│       └── webhook_router.py       # 推送渠道管理 + 消息推送
│
├── scheduler/                      # 调度层 (Celery)
│   ├── __init__.py
│   ├── celery_app.py               # Celery 实例配置与 Beat 定时规则
│   └── tasks.py                    # Celery 异步任务 (Pipeline/日报/清理)
│
├── frontend/                       # Vue 3 前端
│   ├── package.json                # 依赖: vue, vue-router, axios, marked
│   ├── vite.config.js              # Vite 构建配置 + API 代理
│   ├── index.html
│   └── src/
│       ├── main.js                 # Vue 应用入口
│       ├── App.vue                 # 根组件 (侧边栏+路由视图)
│       ├── api/index.ts            # Axios API 封装 (TypeScript)
│       ├── router/index.js         # Vue Router 路由定义
│       ├── components/
│       │   ├── NavSidebar.vue      # 导航侧边栏
│       │   ├── NewsCard.vue        # 新闻卡片
│       │   └── NewsDetail.vue      # 新闻详情（Markdown 渲染）
│       ├── views/
│       │   ├── NewsView.vue        # 新闻列表页
│       │   ├── BriefView.vue       # 简报页
│       │   ├── NewsApiView.vue     # NewsAPI 在线搜索页
│       │   ├── QueryView.vue       # ReAct Agent 问答页 (推理过程可视化)
│       │   ├── WebhookView.vue     # 推送渠道管理页
│       │   ├── SettingsView.vue    # 功能设置页 (RSS/爬虫/调度)
│       │   └── ConfigView.vue      # API 配置页
│       └── assets/styles/
│           ├── global.css
│           └── variables.css
│
├── tests/                          # 测试
│   ├── __init__.py
│   ├── conftest.py                 # 共享 fixtures
│   ├── test_collector.py
│   ├── test_article_store.py
│   ├── test_pipeline_service.py
│   ├── test_query_service.py
│   ├── test_markdown_converter.py  # Markdown 转换器测试
│   ├── test_tools.py              # Agent 工具层测试
│   ├── test_react_parser.py       # ReAct 解析器测试
│   ├── test_react_agent.py        # ReAct Agent 集成测试
│   └── test_hybrid_search.py     # 混合检索 + RRF 测试
│
├── document/                       # 设计文档
│   ├── demo_design.md              # Demo 设计方案
│   ├── full_design.md              # 完整方案 (v2)
│   ├── architecture-current.md     # 当前架构文档 (本文档)
│   ├── architecture-target.md      # 目标架构文档
│   └── Development Plan.md         # 开发计划
│
├── data/                           # 运行时数据 (.gitignore)
│   ├── markdown/                   # Markdown 文件输出 (可选)
│   ├── feeds_config.json           # 前端管理的 RSS 源列表
│   └── webhook_config.json         # 推送渠道配置 + 自动推送开关
│
├── output/                         # 输出
│   ├── daily_brief_YYYY-MM-DD.md   # 日报文件
│   └── research/                   # 深度研究报告
│       └── research_*.md
│
├── .env.example
├── .gitignore
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 5. 核心接口契约 (Protocol)

系统通过 5 个 `typing.Protocol` 定义接口契约，是**架构可替换性的基石**。所有 Protocol 均标记为 `@runtime_checkable`。

### 5.1 ArticleStoreProtocol

```python
class ArticleStoreProtocol(Protocol):
    def save_articles(self, articles: list[Article]) -> int: ...
    def get_unembedded(self, limit: int = 100) -> list[Article]: ...
    def mark_embedded(self, article_ids: list[int]) -> None: ...
    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Article]: ...
    def get_recent(self, hours: int = 24, limit: int = 50) -> list[Article]: ...
    def get_stats(self) -> dict: ...
    def cleanup_old_articles(self, retention_days: int = 90) -> int: ...
```

**当前实现**：`PostgresArticleStore`
- 去重策略：SHA256(url) → url_hash UNIQUE 约束
- 额外方法（超出 Protocol）：`delete_articles()`, `get_article_by_id()`, `get_articles()` (分页), `count_articles()`, `get_pending_summary()`, `mark_pending_summary()`, `mark_summarized()`, `update_summary()`
- 父 chunk 存储方法：`save_parent_chunks()`, `get_parent_chunks_by_ids()`, `delete_parent_chunks_by_article_ids()`
- 全文搜索方法：`search_parent_chunks_by_keyword()`, `backfill_search_vectors()`
- 工具方法：`_segment_text()` — 使用 jieba 分词，供 FTS 索引和查询使用

### 5.2 VectorStoreProtocol

```python
class VectorStoreProtocol(Protocol):
    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> int: ...
    def search_chunks(self, query_embedding: list[float], top_k: int = 10,
                      filters: dict | None = None) -> list[ChunkSearchResult]: ...
    def delete_by_article_ids(self, article_ids: list[int]) -> None: ...
```

**当前实现**：`QdrantVectorStore` (chunk 级别)
- Collection 名称：`news_chunks`
- 距离度量：cosine
- 批量写入大小：50 条
- 子 chunk 向量 + payload (包含 `parent_chunk_id` 引用)
- 删除通过 payload `article_id` 过滤
- 父 chunk 存储在 PostgreSQL `parent_chunks` 表（零冗余，含 `search_vector` 全文索引）

### 5.3 LLMClientProtocol

```python
class LLMClientProtocol(Protocol):
    def generate(self, system_prompt: str, user_message: str) -> str: ...
    def generate_stream(self, system_prompt: str, user_message: str) -> Iterator[str]: ...
    def generate_with_history(self, messages: list[dict]) -> str: ...
    def generate_with_history_stream(self, messages: list[dict]) -> Iterator[str]: ...
```

`generate_with_history` 系列方法接受 OpenAI 格式的消息列表 `[{"role": "system"|"user"|"assistant", "content": "..."}]`，支持 ReAct Agent 的多轮推理对话。各客户端内部将消息转换为对应 SDK 格式：
- **OpenAI Compatible / OpenAI**：直接传 `messages` 到 `chat.completions.create()`
- **Gemini**：提取 `system` 为 `system_instruction`，`user`/`assistant` 转为 `contents` 列表
- **Anthropic**：提取 `system` 为独立参数，其余为 `messages` 列表

**当前实现**（4 个客户端）：

| 客户端 | Provider 标识 | 默认模型 |
|---|---|---|
| `OpenAICompatibleClient` | `openai_compatible` | 用户自定义 |
| `OpenAIClient` | `openai` | `gpt-4o-mini` |
| `GeminiClient` | `gemini` | `gemini-2.0-flash` |
| `AnthropicClient` | `anthropic` | `claude-sonnet-4-20250514` |

### 5.4 EmbeddingClientProtocol

```python
class EmbeddingClientProtocol(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

**当前实现**：`OpenAICompatibleEmbeddingClient`（批量 50 条，自动分批）

### 5.5 RerankClientProtocol

```python
class RerankClientProtocol(Protocol):
    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[dict]:
        """对文档列表按与 query 的相关性重新排序。
        Returns: [{"index": int, "relevance_score": float}, ...] 按 relevance_score 降序。
        """
        ...
```

**当前实现**：`OpenAICompatibleRerankClient`
- 兼容 Jina Reranker / SiliconFlow / Cohere 等 Cross-Encoder API
- 请求格式：`POST {base_url}/rerank`
- 可选功能，通过 `RERANK_ENABLED=true` 启用

---

## 6. 数据流架构

### 6.1 Pipeline 数据流（定时/手动触发）

```
数据源
  ├─ RSS 源 (feeds_config.json)
  └─ 网页爬虫 (sites_config.json)
    │
    ▼
NewsCollector.fetch_all()  +  WebCrawler.crawl_all()
    │  feedparser 解析 RSS → trafilatura 提取正文
    │  Crawlee 爬取网页 → trafilatura 提取正文
    ▼
list[Article]  (内存，html_content + content)
    │
    ▼
NewsMarkdownConverter.convert_batch()
    │  HTML → Markdown 转换 + 元数据提取 (作者/标签/日期)
    │  article.content = Markdown, article.html_content = ""
    ▼
PostgresArticleStore.save_articles()
    │  SHA256(url) 去重 → INSERT OR SKIP
    │  新文章状态: pending_summary
    ▼
[可选] NewsMarkdownConverter.save_batch_as_files()
    │  保存为带 YAML Front Matter 的 .md 文件
    ▼
SummaryService.summarize_pending()  [可选，需 LLM]
    │  按 batch_size 分批 → LLM 生成摘要+标签 → 更新数据库
    │  状态: pending_summary → summarized
    ▼
PostgresArticleStore.get_unembedded()
    │  SELECT WHERE status = 'summarized'
    ▼
ChunkingService.chunk_articles()
    │  按 Markdown 章节结构拆分为子 chunk (≤512 tok) + 组装父 chunk (~1024 tok)
    │  子 chunk 包含标题层级路径 (heading_path)
    │  父 chunk 之间通过共享尾部子 chunk 实现 ~100 token overlap
    ▼
EmbeddingClient.embed()
    │  对子 chunks 批量生成向量 (50条/批)
    ▼
QdrantVectorStore.add_chunks()
    │  子 chunk 向量 + payload 写入 Qdrant (news_chunks collection)
    ▼
PostgresArticleStore.save_parent_chunks()
    │  父 chunk 写入 PostgreSQL (parent_chunks 表)
    ▼
PostgresArticleStore.mark_embedded()
    │  UPDATE status = 'embedded'
    ▼
完成 ✓
```

### 6.2 ReAct Agent 问答数据流

```
用户问题 (前端 QueryView)
    │
    ▼
QueryService.answer_agent_stream()
    │
    ▼
ReActAgent.run_stream(question)
    │
    ├─ 构建 system prompt (含可用工具描述 + 意图识别引导)
    │
    ├─ while steps < max_steps (默认 5):
    │   │
    │   ├─ LLMClient.generate_with_history(messages)
    │   │     多轮对话，包含历史 Thought/Observation
    │   │
    │   ├─ ReActParser.parse(llm_output)
    │   │     解析 Thought / Action / Answer
    │   │
    │   ├─ [Thought] → yield AgentEvent(type="thought")
    │   │
    │   ├─ [Action] → ToolRegistry.get(tool_name).execute(**params)
    │   │     │  工具执行 (query_knowledge_base / web_search / ...)
    │   │     ▼
    │   │   yield AgentEvent(type="observation", content=结果)
    │   │     结果追加到 messages 历史
    │   │
    │   └─ [Answer] → yield AgentEvent(type="answer")
    │         最终回答 → SSE 传输到前端
    │
    └─ SSE 事件流 → 前端展示推理过程 + 最终回答
```

**SSE 事件格式**（JSON 结构化）：
```json
data: {"event_type": "thought", "content": "用户想了解AI新闻，需要搜索..."}
data: {"event_type": "action", "tool_name": "query_knowledge_base", "tool_input": {"query": "AI"}}
data: {"event_type": "observation", "content": "找到 5 条相关文章..."}
data: {"event_type": "answer", "content": "根据搜索结果，最近的AI新闻..."}
data: [DONE]
```

### 6.3 深度研究数据流

```
用户研究主题 (前端 / API)
    │
    ▼
DeepResearchService.research_stream(topic)
    │
    ▼
ReActAgent (max_steps=15, 专用深度研究 system_prompt)
    │
    ├─ 自主执行多步研究流程:
    │   1. 生成搜索关键词
    │   2. query_knowledge_base — 本地知识库检索
    │   3. read_article — 阅读感兴趣的文章全文
    │   4. web_search — 互联网搜索补充信息
    │   5. 综合分析，生成研究报告
    │
    ├─ yield AgentEvent 流 → SSE 传输到前端
    │
    └─ 自动保存报告 → output/research/research_*.md
```

### 6.4 简报生成 + 推送数据流

```
触发（定时 / 手动按钮 / API）
    │
    ▼
BriefService.generate(hours=24)
    │
    ├─ ArticleStore.get_recent(hours=24, limit=50)
    │
    ├─ 格式化 context（上限 80,000 字符）
    │
    ├─ LLMClient.generate(BRIEF_SYSTEM_PROMPT, context)
    │
    ├─ DailyBrief.save_to_file(output_path)
    │     → output/daily_brief_YYYY-MM-DD.md
    │
    └─ [auto_push=true?]
          │
          ▼
        WebhookService.broadcast(content_markdown)
          │  遍历所有 enabled 渠道
          │  按平台格式化 → requests.post()
          ▼
        飞书 / 钉钉 / 企业微信 / Telegram / ntfy
```

### 6.5 Webhook 推送数据流

```
触发方式：
  ├─ 手动推送（前端按钮 / API /api/webhook/push）
  ├─ 简报生成后自动推送（auto_push 开关）
  ├─ 研究报告推送 (/api/research/push/{filename})
  └─ 单渠道推送 / 测试消息
    │
    ▼
WebhookService
    │
    ├─ load_channels()  ← data/webhook_config.json
    │     过滤 enabled=true 的渠道
    │
    ├─ 按平台格式化消息：
    │   ├── 飞书:    Interactive Card (JSON)    max 30,000 字符
    │   ├── 钉钉:    Markdown msgtype           max 20,000 字符
    │   ├── 企业微信: Markdown msgtype           max  4,096 字符
    │   ├── Telegram: sendMessage + Markdown     max  4,096 字符
    │   └── ntfy:    POST text/markdown          max  4,096 字符
    │
    └─ requests.post() → 各平台 Webhook 端点
          │  超长内容自动截断
          │  单渠道失败不影响其他渠道
          ▼
        返回 [{status, channel, result/error}, ...]
```

### 6.6 混合检索数据流（向量 + 关键词 + RRF 融合）

```
用户查询 "特斯拉 FSD 自动驾驶最新进展"
    │
    ├──────────────────────┬──────────────────────────┐
    │                      │                          │
    ▼                      ▼                          │
  向量检索通道            关键词检索通道                │
    │                      │                          │
    ▼                      ▼                          │
Embedding.embed()    jieba.cut(query)                 │
    │                      │                          │
    ▼                      ▼                          │
Qdrant search_chunks   PostgreSQL parent_chunks       │
(子 chunk, top_k*3)    WHERE search_vector @@ query   │
    │                   (父 chunk, top_k=20)           │
    ▼                      │                          │
子 chunk → 按              │                          │
parent_chunk_id 去重       │                          │
→ 父 chunk ID 排名         │                          │
    │                      │                          │
    └──────────┬───────────┘                          │
               ▼                                      │
          RRF 融合 (k=60)                             │
          Score(d) = Σ w_r / (k + rank_r(d) + 1)     │
               │                                      │
               ▼                                      │
          按 RRF 分数排序 → top_k * 2                 │
               │                                      │
               ▼                                      │
          PostgreSQL get_parent_chunks_by_ids()       │
               │                                      │
               ▼                                      │
          [可选] Rerank 精排 (对父 chunk content)     │
               │                                      │
               ▼                                      │
          最终 top_k 个父 chunks → 返回 LLM          │
```

**检索模式**：
- `hybrid`（默认）：向量 + 关键词 + RRF 融合
- `semantic`：仅向量语义检索（原有行为）
- `keyword`：仅关键词全文搜索

**降级策略**：
- 向量检索失败 → 仅使用关键词结果
- 关键词检索失败 → 仅使用向量结果
- 双通道均失败 → 回退到文章级 ILIKE 搜索

---

## 7. 前后端交互架构

### 7.1 API 路由一览

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| **新闻** | | |
| GET | `/api/news` | 分页获取新闻列表（支持来源/语言/关键词筛选） |
| GET | `/api/news/stats` | 数据库统计 |
| GET | `/api/news/sources` | 所有新闻来源 |
| GET | `/api/news/{id}` | 单篇新闻全文 |
| POST | `/api/news/pipeline` | 手动触发 Pipeline (异步返回 task_id) |
| POST | `/api/news/batch-delete` | 批量删除文章（含向量记录） |
| **简报** | | |
| GET | `/api/briefs` | 简报文件列表 |
| GET | `/api/briefs/{filename}` | 单份简报内容 |
| POST | `/api/briefs/generate` | 手动生成简报 (异步返回 task_id) |
| **任务** | | |
| GET | `/api/tasks/{task_id}` | 轮询查询异步任务状态和结果 |
| **Agent 问答** | | |
| POST | `/api/query` | ReAct Agent 非流式问答 |
| POST | `/api/query/stream` | ReAct Agent SSE 流式问答（结构化 AgentEvent JSON）|
| **深度研究** | | |
| POST | `/api/research/stream` | SSE 流式深度研究 |
| GET | `/api/research` | 研究报告列表 |
| GET | `/api/research/{filename}` | 单份研究报告内容 |
| DELETE | `/api/research/{filename}` | 删除研究报告 |
| POST | `/api/research/batch-delete` | 批量删除研究报告 |
| POST | `/api/research/batch-export` | 批量导出研究报告 (单文件 .md / 多文件 .zip) |
| POST | `/api/research/push/{filename}` | 推送研究报告到 Webhook 渠道 |
| **NewsAPI 代理** | | |
| GET | `/api/newsapi/everything` | NewsAPI 全文搜索代理 |
| GET | `/api/newsapi/top-headlines` | NewsAPI 热门头条代理 |
| POST | `/api/newsapi/save` | 保存 NewsAPI 文章到本地 |
| **Webhook** | | |
| GET | `/api/webhook/platforms` | 支持的推送平台列表 |
| GET | `/api/webhook/channels` | 推送渠道列表（URL 脱敏） |
| POST | `/api/webhook/channels` | 添加推送渠道 |
| PUT | `/api/webhook/channels/{id}` | 更新推送渠道 |
| DELETE | `/api/webhook/channels/{id}` | 删除推送渠道 |
| POST | `/api/webhook/channels/{id}/test` | 发送测试消息 |
| POST | `/api/webhook/push` | 推送最新简报到所有启用渠道 |
| POST | `/api/webhook/push/{id}` | 推送到指定渠道 |
| GET | `/api/webhook/auto-push` | 获取自动推送状态 |
| PUT | `/api/webhook/auto-push` | 设置自动推送开关 |
| **配置** | | |
| GET | `/api/config` | 获取配置（API Key 脱敏） |
| PUT | `/api/config` | 更新 .env 配置 |
| GET | `/api/config/providers` | LLM 提供商列表 |
| POST | `/api/config/models` | 远程获取可用模型列表 |
| **设置** | | |
| GET | `/api/settings/feeds` | RSS 源列表 |
| POST | `/api/settings/feeds` | 添加 RSS 源 |
| DELETE | `/api/settings/feeds/{id}` | 删除 RSS 源 |
| GET | `/api/settings/schedule` | 获取调度配置 |
| PUT | `/api/settings/schedule` | 更新调度配置 |

### 7.2 前端页面

| 路由 | 视图组件 | 功能 |
|---|---|---|
| `/news` | `NewsView.vue` | 新闻列表浏览、筛选、Pipeline 触发、批量删除 |
| `/briefs` | `BriefView.vue` | 简报列表、查看、手动生成 |
| `/newsapi` | `NewsApiView.vue` | NewsAPI 在线搜索 (everything + top-headlines) |
| `/query` | `QueryView.vue` | ReAct Agent 问答（推理过程可视化 + SSE 流式） |
| `/webhook` | `WebhookView.vue` | 推送渠道管理、测试、手动推送、自动推送开关 |
| `/settings` | `SettingsView.vue` | RSS 源管理 + 爬虫源管理 + 调度参数配置 |
| `/config` | `ConfigView.vue` | LLM/Embedding/Rerank/搜索引擎 API 配置管理 |

### 7.3 开发模式通信

```
浏览器                  Vite Dev Server (:5173)          FastAPI (:8005)
  │                           │                              │
  ├──  GET /news  ──────────▶ │  (SPA 路由，返回 index.html) │
  │                           │                              │
  ├──  GET /api/news  ───────▶│── proxy ────────────────────▶│
  │                           │                              │  SQLite 查询
  │◀──  JSON 响应  ───────────│◀─────────────────────────────│
```

生产模式下，Vue 构建产物放在 `delivery/static/`，由 FastAPI 直接托管 SPA。

---

## 8. 配置管理

### 8.1 配置来源

| 配置项 | 存储位置 | 管理方式 |
|---|---|---|
| LLM/Embedding/Rerank API 参数 | `.env` 文件 | 前端 ConfigView 通过 API 读写 |
| RSS 源列表 | `data/feeds_config.json` | 前端 SettingsView 通过 API 增删 |
| 爬虫源列表 | `data/sites_config.json` | 前端 SettingsView 通过 API 增删 |
| 调度参数 | `.env` 文件 | 前端 SettingsView 通过 API 读写 |
| 推送渠道 + 自动推送 | `data/webhook_config.json` | 前端 WebhookView 通过 API 增删改 |
| 搜索引擎 Key (Tavily/NewsAPI) | `.env` 文件 | 前端 ConfigView 通过 API 读写 |
| AI 摘要配置 | `.env` 文件 | 前端 ConfigView 通过 API 读写 |
| 应用默认值 | `core/config.py` AppConfig | 代码内 pydantic Field default |

### 8.2 AppConfig 关键字段

```python
class AppConfig(BaseSettings):
    # LLM
    llm_provider: Literal["openai_compatible", "openai", "gemini", "anthropic"]
    llm_api_key / llm_base_url / llm_model: str
    openai_api_key / google_api_key / anthropic_api_key: str

    # Embedding
    embedding_api_key / embedding_base_url / embedding_model: str

    # Rerank 重排序 (可选)
    rerank_enabled: bool = False
    rerank_api_key / rerank_base_url / rerank_model: str
    rerank_top_k_multiplier: int = 3

    # 存储路径
    markdown_output_path: str = "data/markdown"
    output_path: str = "output"

    # PostgreSQL
    pg_dsn: str = "postgresql://logos:logos@localhost:5432/logos"

    # Qdrant
    qdrant_url: str = "..."
    qdrant_api_key: str = "..."

    # Celery / Redis
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # 调度
    fetch_interval_hours: int = 4
    daily_brief_hour: int = 8
    brief_fetch_hours: int = 24
    brief_mode: Literal["daily", "interval"] = "daily"
    brief_interval_hours: int = 8
    max_articles_per_fetch: int = 20

    # 数据管理
    article_retention_days: int = 90
    log_level: str = "INFO"

    # RSS 来源
    rss_feeds: list[dict]   # 默认 3 个源

    # 搜索引擎
    tavily_api_key: str = ""

    # AI 摘要配置
    summary_use_same_llm: bool = True
    summary_llm_provider / summary_llm_api_key / summary_llm_base_url / summary_llm_model: str
    summary_batch_size: int = 5

    # 分块配置
    chunk_max_child_tokens: int = 512
    chunk_target_parent_tokens: int = 1024
    chunk_overlap_tokens: int = 100
    qdrant_chunk_collection_name: str = "news_chunks"

    # 混合检索配置
    hybrid_search_enabled: bool = True
    hybrid_rrf_k: int = 60
    hybrid_vector_weight: float = 1.0
    hybrid_keyword_weight: float = 1.0
    hybrid_keyword_candidates: int = 20
```

### 8.3 ConfigManager 组件管理

`ConfigManager` 是应用级线程安全单例，管理以下组件的生命周期：

| 组件 | 工厂函数 | 说明 |
|---|---|---|
| `article_store` | `create_article_store()` | PostgresArticleStore |
| `vector_store` | `create_vector_store()` | QdrantVectorStore (chunk 级别) |
| `llm_client` | `create_llm_client()` | 4 种 LLM 客户端 |
| `embedding_client` | `create_embedding_client()` | Embedding 客户端 |
| `rerank_client` | `create_rerank_client()` | Rerank 客户端 (可选，None) |
| `summary_llm_client` | `create_summary_llm_client()` | 摘要专用 LLM (可复用主 LLM) |
| `chunking_service` | `create_chunking_service()` | ChunkingService (父子分块) |

`reload()` 方法支持热重载：读取最新 `.env`，diff 变更字段，只重建受影响的组件。

---

## 9. 异常层次

```
NewsAssistantError (基础异常)
├── CollectorError (抓取相关)
│   └── SourceUnavailableError (单源不可用)
├── StoreError (存储相关)
├── EmbeddingError (向量化相关)
├── RerankError (Rerank 重排序相关)
├── LLMError (LLM 调用)
│   └── RateLimitError (限流)
├── ConfigError (配置错误)
└── ToolError (工具层基础异常, core/exceptions.py)
    ├── ToolNotFoundError (注册中心找不到工具)
    ├── ToolValidationError (参数校验失败)
    ├── ToolExecutionError (执行过程出错)
    ├── ToolTimeoutError (异步执行超时)
    └── ToolChainError (工具链执行失败)
    (详细子类定义在 agent/tools/errors.py)
```

所有外部调用失败通过 `@with_retry` 装饰器自动指数退避重试（默认 3 次，基数 2.0）。

---

## 10. 进程模型

当前系统运行时分为 **基础设施层**（Docker Compose 容器）和 **应用层**（本地进程）：

```
=== 基础设施层 (docker compose up -d) ===

容器 1: logos-postgres (postgres:16-alpine)
  └── 端口 :5432
  └── 文章元数据 + 父 chunk + 全文搜索索引
  └── 数据持久化: Docker Volume postgres_data

容器 2: logos-qdrant (qdrant/qdrant:latest)
  └── 端口 :6333 (REST) / :6334 (gRPC)
  └── 子 chunk 向量存储 (news_chunks collection)
  └── 数据持久化: Docker Volume qdrant_data

容器 3: logos-redis (redis:7-alpine)
  └── 端口 :6379
  └── Celery Broker + Result Backend
  └── 数据持久化: Docker Volume redis_data

=== 应用层 (honcho start / start_dev.bat) ===

进程 1: FastAPI Server (delivery/server.py)
  └── uvicorn 监听 :8005
  └── 处理所有 /api/* 请求

进程 2: Celery Worker (celery -A scheduler.celery_app worker)
  └── 执行异步耗时任务 (Pipeline、生成日报、清理数据库)
  └── 依赖 Redis 队列

进程 3: Celery Beat (celery -A scheduler.celery_app beat)
  └── 每 5 分钟发送心跳任务触发检查
  └── 根据 .env 中的参数决定是否分发实际抓取/生成任务

(开发模式额外) 进程 4: Vite Dev Server (:5173) 代理请求
```

**进程间数据共享**：通过 PostgreSQL（文章元数据 + 父 chunk）、Qdrant（子 chunk 向量）和文件系统（日报 .md 文件、feeds_config.json、webhook_config.json）。

---

## 11. 依赖注入模式

系统使用**工厂函数**（`core/factory.py`）+ **ConfigManager 单例**作为依赖注入：

```python
# factory.py — 8 个工厂函数
def create_article_store(config) -> ArticleStoreProtocol:
    return PostgresArticleStore(dsn=config.pg_dsn)

def create_vector_store(config) -> VectorStoreProtocol:
    return QdrantVectorStore(url=config.qdrant_url, api_key=config.qdrant_api_key,
                             collection_name=config.qdrant_chunk_collection_name)

def create_chunking_service(config):
    return ChunkingService(max_child_tokens=config.chunk_max_child_tokens,
                           target_parent_tokens=config.chunk_target_parent_tokens,
                           overlap_tokens=config.chunk_overlap_tokens)

def create_llm_client(config) -> LLMClientProtocol:
    match config.llm_provider:
        case "openai_compatible" | "openai" | "gemini" | "anthropic": ...

def create_embedding_client(config) -> EmbeddingClientProtocol:
    return OpenAICompatibleEmbeddingClient(...)

def create_rerank_client(config) -> RerankClientProtocol | None:
    if not config.rerank_enabled: return None
    return OpenAICompatibleRerankClient(...)

def create_summary_llm_client(config) -> LLMClientProtocol:
    if config.summary_use_same_llm: return create_llm_client(config)
    # 否则按独立配置创建

# ConfigManager 缓存所有组件实例，支持热重载
```

---

## 12. 数据库 Schema

### PostgreSQL articles 表

```sql
CREATE TABLE IF NOT EXISTS articles (
    id           SERIAL PRIMARY KEY,
    url_hash     TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    content      TEXT,
    html_content TEXT,
    summary      TEXT,
    source       TEXT,
    author       TEXT DEFAULT '',
    language     TEXT,
    published_at TIMESTAMP,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status       TEXT DEFAULT 'stored',
    tags         JSONB DEFAULT '[]'::jsonb
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_status ON articles(status);
CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at);
CREATE INDEX IF NOT EXISTS idx_source ON articles(source);
```

**ArticleStatus 生命周期**：
```
stored → pending_summary → summarized → embedded
```
（无摘要服务时直接 `stored → summarized → embedded`）

### Qdrant Collection (chunk 级别)

- Collection: `news_chunks`
- 距离度量: cosine
- Point ID: UUID5 基于 `chunk_id` 字符串生成
- Vector: 子 chunk 内容的 embedding 向量
- Payload:
  - `chunk_id`: 子 chunk 唯一 ID (格式: `"{article_id}_c{index}"`)
  - `article_id`: 所属文章 ID
  - `parent_chunk_id`: 所属父 chunk ID (格式: `"{article_id}_p{index}"`)
  - `doc_name`: 文档名
  - `heading_path`: 标题层级路径 (JSON array)
  - `content`: 子 chunk 原文
  - `chunk_index`: 在文章内的序号
  - `source`: 新闻来源
  - `url`: 文章 URL

### PostgreSQL parent_chunks 表

```sql
CREATE TABLE IF NOT EXISTS parent_chunks (
    parent_chunk_id TEXT PRIMARY KEY,
    article_id      INTEGER NOT NULL,
    content         TEXT NOT NULL,
    token_count     INTEGER NOT NULL DEFAULT 0,
    child_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    doc_name        TEXT NOT NULL DEFAULT '',
    source          TEXT DEFAULT '',
    url             TEXT DEFAULT '',
    search_vector   tsvector,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_parent_chunks_article_id ON parent_chunks(article_id);
CREATE INDEX IF NOT EXISTS idx_parent_chunks_fts ON parent_chunks USING GIN(search_vector);
```

**分块策略**：
- 子 chunk：按 Markdown 标题结构切分，≤512 token，存入 Qdrant 用于向量检索
- 父 chunk：~1024 token，完整包含若干子 chunk，存入 PostgreSQL 用于 LLM 召回
- 父 chunk 之间通过共享尾部子 chunk 实现 ~100 token overlap
- 子 chunk 明确归属一个父 chunk（通过 `parent_chunk_id`）
- 短文档 (≤1024 token) 同时视为子 chunk 和父 chunk
- 全文索引：父 chunk 写入时自动使用 `jieba` 分词生成 `search_vector` (tsvector)，供关键词检索使用
- `backfill_search_vectors()` 支持为已有数据回填全文索引

---

## 13. Agent 智能体层

Agent 层包含两个子模块：**ReAct 推理-行动循环**（`agent/react/`）和**工具系统**（`agent/tools/`）。ReAct Agent 在多轮对话中自主推理并调用工具，最终基于真实数据生成回答。

### 13.1 ReAct Agent 核心

| 组件 | 文件 | 职责 |
|---|---|---|
| **ReActAgent** | `agent/react/agent.py` | 推理-行动循环核心（run / run_stream）|
| **AgentEvent** | `agent/react/agent.py` | 流式事件数据类（thought/action/observation/answer）|
| **AgentResult** | `agent/react/agent.py` | 完整执行结果封装 |
| **ReActParser** | `agent/react/parser.py` | LLM 输出解析器（Thought/Action/Answer 格式）|
| **StreamingReActParser** | `agent/react/parser.py` | 流式逐 token 解析器 |
| **prompts** | `agent/react/prompts.py` | ReAct system prompt 模板（通用/深度研究/简报） |

**Agent 工作模式**：
- **通用模式** (`build_react_system_prompt`)：自动意图识别，快速问答 vs 深度研究切换，max_steps=5
- **深度研究模式** (`build_deep_research_prompt`)：专用研究流程引导，max_steps=15
- **简报生成模式** (`build_briefing_agent_prompt`)：简报生成引导

**ReAct 循环流程**：

```
1. 构建 system prompt（含所有可用工具描述）
2. messages = [system_prompt, user_question]
3. while steps < max_steps:
   4. llm_output = LLM.generate_with_history(messages)
   5. parsed_steps = ReActParser.parse(llm_output)
   6. for step in parsed_steps:
      a. Thought  → yield AgentEvent("thought")
      b. Action   → 执行工具 → yield AgentEvent("action") + AgentEvent("observation")
                     Observation 追加到 messages 历史
      c. Answer   → yield AgentEvent("answer") → 结束
7. 达到 max_steps → 强制要求 LLM 基于已有 Observation 给出回答
```

> **设计选择**：采用**手动 prompt 构建 + 输出解析**实现 ReAct，而非 OpenAI function calling API。原因：项目支持 4 种 LLM 后端，统一的 ReAct prompt 方式兼容性最好，且 Thought/Observation 过程可透明展示给用户。

### 13.2 工具系统核心组件

| 组件 | 文件 | 职责 |
|---|---|---|
| **BaseTool** | `agent/tools/base.py` | 工具抽象基类（模板方法模式）|
| **ToolParameter** | `agent/tools/base.py` | 参数定义，生成 JSON Schema |
| **ToolResult** | `agent/tools/base.py` | 执行结果标准封装 |
| **ToolRegistry** | `agent/tools/registry.py` | 线程安全单例注册中心 |
| **@register_tool** | `agent/tools/registry.py` | 类装饰器，自动注册工具 |
| **ToolChain** | `agent/tools/chain.py` | 多工具有序编排 |
| **AsyncToolExecutor** | `agent/tools/executor.py` | 异步执行器（ThreadPool 包装）|

### 13.3 内置工具

| 工具名 | 描述 | 依赖层 | 状态 |
|---|---|---|---|
| `query_knowledge_base` | 混合检索（向量+关键词+RRF融合 + 父子分块 + 支持 Rerank 精排）| EmbeddingClient, VectorStore, ArticleStore, RerankClient, HybridSearchService | ✅ 已实现 |
| `get_recent_news` | 获取最近 N 小时新闻列表 | ArticleStore | ✅ 已实现 |
| `get_news_stats` | 新闻库统计信息（总数/来源/状态分布）| ArticleStore | ✅ 已实现 |
| `generate_brief` | 生成新闻简报 | ArticleStore, LLMClient | ✅ 已实现 |
| `read_article` | 通过 ID 阅读文章全文 (深度研究用) | ArticleStore | ✅ 已实现 |
| `web_search` | 互联网多引擎并发搜索 (DuckDuckGo+Tavily) | WebSearchService | ✅ 已实现 |

内置工具需要 Service/Infrastructure 层依赖注入，不使用 `@register_tool` 装饰器。通过 `register_builtin_tools(config_manager)` 函数在**应用启动时**统一构造和注册：

```python
# delivery/server.py — FastAPI 启动时
@app.on_event("startup")
def startup_register_tools():
    from agent.tools.builtin import register_builtin_tools
    from core.config_manager import get_config_manager
    register_builtin_tools(get_config_manager())
```

### 13.4 工具执行流程

```
ReActAgent 决策 → Action: tool_name
    │
    ▼
ToolRegistry.get(tool_name)
    │
    ▼
BaseTool.execute(**params)
    │
    ├── validate_params()    参数校验 (必填/类型/默认值)
    │
    ├── _run(**validated)    子类实际逻辑 (调用 Services 层)
    │
    └── → ToolResult         统一结果封装 (success/data/error/time)
          │
          ▼
        结果文本 → 追加到消息历史作为 Observation
```

### 13.5 工具链编排

`ToolChain` 支持多步工具的有序执行，通过 `$prev` 占位符实现管道传参：

```python
chain = ToolChain("新闻分析链")
chain.add_step("query_knowledge_base", params={"query": "AI 新闻"})
chain.add_step("generate_brief", params={"articles": "$prev"})
result = chain.run()
```

- `stop_on_failure` 参数控制失败后是否中止整条链
- 完整保留每一步的 `ToolResult`，供 Agent 回顾推理

### 13.6 异步执行器

`AsyncToolExecutor` 基于 `asyncio` + `ThreadPoolExecutor`，将同步工具包装为异步调用：

```python
executor = AsyncToolExecutor(max_workers=4, default_timeout=60)
result = await executor.execute("query_knowledge_base", query="AI")
results = await executor.execute_batch([ToolCall(...), ...])
result = await executor.execute_with_timeout("query_knowledge_base", timeout=10, query="AI")
```

---

## 14. 当前已知局限性

| 尚未引入 Celery 重试补偿机制 | 需强化容错处理 | → Celery Task Retries |
| RSS 串行抓取 | 源多时抓取慢 | → ThreadPoolExecutor 并发 |
| ~~父子分块 + Rerank 但无全文搜索~~ | ~~缺少 BM25 混合检索能力~~ | ✅ 已实现 RRF 混合检索 + jieba 中文分词 |
| 标准 logging | 非结构化，难以查询 | → structlog |
| 单环境 .env | 无 dev/prod 区分 | → 多环境 .env |
| ~~无容器化~~ | ~~部署需手动配置~~ | ✅ 已实现 Docker Compose 基础设施容器化 |
| 无认证/授权 | 任何人可访问 API | → 身份认证中间件 |

---

## 15. 运行方式

```bash
# 1. 安装依赖
pip install -r requirements.txt
cd frontend && pnpm install && cd ..

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key 和端点
# 存储/Redis 使用 Docker Compose 默认值，无需修改

# 3. 启动基础设施 (PostgreSQL + Qdrant + Redis)
docker compose up -d
# 验证: docker compose ps  (应显示 3 个容器 healthy)

# 4. 一键启动所有应用服务 (Windows 推荐)
./start_dev.bat
# (自动启动 docker compose + FastAPI + Celery Worker + Celery Beat + Flower + 前端)

# 或分别启动:
# 后端:  python -m delivery.server
# 前端:  cd frontend && pnpm dev
# Worker: celery -A scheduler.celery_app worker -l info -P threads
# Beat:   celery -A scheduler.celery_app beat -l info

# 停止基础设施
docker compose down          # 停止容器 (保留数据)
docker compose down -v       # 停止容器 + 删除数据卷

# CLI 调试
python -m delivery.cli pipeline
python -m delivery.cli ask "今天有什么重要新闻？"
python -m delivery.cli stats
```
