# Logos 当前架构文档

> **文档版本**：v1.0
> **基于代码快照时间**：2026-04-08
> **项目阶段**：Demo+ （已超越原始 Demo 设计，包含 Vue 前端 + FastAPI 后端）

---

## 1. 系统概览

Logos 是一个**个人 AI 新闻分析助手**，具备两大核心能力：

1. **定时 Pipeline**：自动从多个 RSS 新闻源抓取内容 → 清洗去重 → 向量化存储 → 每日自动生成新闻简报
2. **交互式查询**：用户通过自然语言提问，系统执行 RAG（检索增强生成）从历史新闻库中检索并调用 LLM 给出分析回答

当前系统已从纯 Streamlit Demo 演进为**前后端分离架构**（Vue 3 + FastAPI），同时保留 Streamlit 作为备用界面。

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
| **元数据存储** | SQLite | 单文件数据库，零配置 |
| **向量存储** | ChromaDB（本地持久化） | 余弦相似度检索 |
| **LLM 调用** | openai / google-genai / anthropic SDK | 四种后端：OpenAI Compatible, OpenAI, Gemini, Claude |
| **Embedding** | openai SDK（自定义端点） | OpenAI 格式兼容 API |
| **任务调度** | APScheduler（BlockingScheduler） | 独立进程，interval + cron 触发 |
| **配置管理** | pydantic-settings + .env | 类型校验 + 环境变量加载 |
| **界面（备用）** | Streamlit | 保留兼容，独立进程 |
| **测试** | pytest | 单元测试 + 集成测试 |

---

## 3. 分层架构

```
┌────────────────────────────────────────────────────────────────────┐
│                        前端表现层 (Frontend)                        │
│   Vue 3 SPA: NewsView │ BriefView │ QueryView │ Settings │ Config │
│   通过 Axios 调用 /api/* 端点                                      │
├────────────────────────────────────────────────────────────────────┤
│                     后端表现层 (Delivery)                           │
│   FastAPI Server (server.py)                                       │
│   ├── news_router    ─ /api/news/*     新闻 CRUD + Pipeline        │
│   ├── brief_router   ─ /api/briefs/*   简报列表/查看/生成           │
│   ├── query_router   ─ /api/query/*    RAG 问答 (普通 + SSE 流式)  │
│   ├── config_router  ─ /api/config/*   .env 配置读写               │
│   ├── settings_router─ /api/settings/* RSS 源管理 + 调度参数       │
│   └── health         ─ /api/health     健康检查                    │
│                                                                    │
│   Streamlit (streamlit_app.py) — 备用界面，独立进程                 │
│   CLI (cli.py) — 调试工具                                          │
├────────────────────────────────────────────────────────────────────┤
│                     应用服务层 (Services)                           │
│   PipelineService  │  QueryService  │  BriefService                │
│   编排基础设施组件，不直接操作数据库或外部 API                       │
├────────────────────────────────────────────────────────────────────┤
│                     领域模型层 (Models)                             │
│   Article (dataclass) │ DailyBrief │ SearchQuery │ SearchResult    │
│   纯数据定义，无 I/O 依赖                                          │
├────────────────────────────────────────────────────────────────────┤
│                    基础设施层 (Infrastructure)                      │
│   NewsCollector       │  SQLiteArticleStore   │  ChromaVectorStore │
│   OpenAI*/Gemini*/Anthropic*Client            │  EmbeddingClient   │
│   实现 core/protocols.py 中定义的 Protocol 接口                    │
├────────────────────────────────────────────────────────────────────┤
│                    横切关注点 (Core)                                │
│   AppConfig (pydantic-settings)  │  Protocols (接口契约)           │
│   Factory (工厂函数)             │  Exceptions (异常层次)          │
│   Logging (统一日志)             │  Retry (指数退避重试)           │
├────────────────────────────────────────────────────────────────────┤
│                     调度层 (Scheduler)                              │
│   APScheduler (BlockingScheduler) — 独立进程                       │
│   定时 Pipeline (每 4h) │ 日报生成 (每天 8:00) │ 清理 (每周日 3:00)│
└────────────────────────────────────────────────────────────────────┘
```

**层间依赖规则**（严格单向）：
- Frontend → Delivery（HTTP API）
- Delivery → Services → Infrastructure
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
│   ├── protocols.py                # 4 个 Protocol 接口契约
│   ├── factory.py                  # 工厂函数：按配置创建组件
│   ├── exceptions.py               # 统一异常层次 (7 个异常类)
│   ├── logging.py                  # logging 标准库配置
│   └── retry.py                    # @with_retry 指数退避装饰器
│
├── models/                         # 领域模型 (纯 dataclass)
│   ├── __init__.py
│   ├── article.py                  # Article + Language + ArticleStatus
│   ├── brief.py                    # DailyBrief
│   └── search.py                   # SearchQuery + SearchResult
│
├── infrastructure/                 # 基础设施层
│   ├── __init__.py
│   ├── collector.py                # NewsCollector (feedparser + trafilatura)
│   ├── article_store.py            # SQLiteArticleStore
│   ├── vector_store.py             # ChromaVectorStore
│   ├── llm_client.py               # 4 个 LLM 客户端实现
│   └── embedding_client.py         # OpenAICompatibleEmbeddingClient
│
├── services/                       # 应用服务层
│   ├── __init__.py
│   ├── pipeline_service.py         # PipelineService (抓取→存储→向量化)
│   ├── query_service.py            # QueryService (RAG 检索+回答)
│   └── brief_service.py            # BriefService (日报生成)
│
├── delivery/                       # 后端表现层
│   ├── __init__.py
│   ├── server.py                   # FastAPI 应用入口
│   ├── streamlit_app.py            # Streamlit 备用界面
│   ├── cli.py                      # CLI 调试工具
│   └── api/                        # FastAPI 路由模块
│       ├── __init__.py
│       ├── news_router.py          # 新闻 CRUD + Pipeline 触发
│       ├── brief_router.py         # 简报管理
│       ├── query_router.py         # AI 问答 (含 SSE 流式)
│       ├── config_router.py        # .env 配置管理
│       └── settings_router.py      # RSS 源 + 调度参数管理
│
├── scheduler/                      # 调度层 (独立进程)
│   ├── __init__.py
│   └── scheduler.py                # APScheduler 定时任务
│
├── frontend/                       # Vue 3 前端
│   ├── package.json                # 依赖: vue, vue-router, axios, marked
│   ├── vite.config.js              # Vite 构建配置 + API 代理
│   ├── index.html
│   └── src/
│       ├── main.js                 # Vue 应用入口
│       ├── App.vue                 # 根组件 (侧边栏+路由视图)
│       ├── api/index.js            # Axios API 封装
│       ├── router/index.js         # Vue Router 路由定义
│       ├── components/
│       │   ├── NavSidebar.vue      # 导航侧边栏
│       │   ├── NewsCard.vue        # 新闻卡片
│       │   └── NewsDetail.vue      # 新闻详情
│       ├── views/
│       │   ├── NewsView.vue        # 新闻列表页
│       │   ├── BriefView.vue       # 简报页
│       │   ├── QueryView.vue       # 智能问答页
│       │   ├── SettingsView.vue    # 功能设置页 (RSS/调度)
│       │   └── ConfigView.vue      # API 配置页
│       └── assets/styles/
│           ├── global.css
│           └── variables.css
│
├── tests/                          # 测试
│   ├── conftest.py                 # 共享 fixtures
│   ├── test_collector.py
│   ├── test_article_store.py
│   ├── test_pipeline_service.py
│   └── test_query_service.py
│
├── document/                       # 设计文档
│   ├── demo_design.md              # Demo 设计方案
│   ├── full_design.md              # 完整方案 (v2)
│   └── Development Plan.md         # 开发计划
│
├── data/                           # 运行时数据 (.gitignore)
│   ├── news.db                     # SQLite 数据库
│   ├── chroma/                     # ChromaDB 向量文件
│   └── feeds_config.json           # 前端管理的 RSS 源列表
│
├── output/                         # 日报输出
│   └── daily_brief_YYYY-MM-DD.md
│
├── .env.example
├── .gitignore
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 5. 核心接口契约 (Protocol)

系统通过 4 个 `typing.Protocol` 定义接口契约，是**架构可替换性的基石**。所有 Protocol 均标记为 `@runtime_checkable`。

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

**当前实现**：`SQLiteArticleStore`
- 去重策略：SHA256(url) → url_hash UNIQUE 约束
- 额外方法（超出 Protocol）：`delete_articles()`, `get_article_by_id()`, `get_articles()` (分页), `count_articles()`

### 5.2 VectorStoreProtocol

```python
class VectorStoreProtocol(Protocol):
    def add_articles(self, articles: list[Article], embeddings: list[list[float]]) -> int: ...
    def search(self, query_embedding: list[float], top_k: int = 10,
               filters: dict | None = None) -> list[SearchResult]: ...
```

**当前实现**：`ChromaVectorStore`
- Collection 名称：`news_articles`
- 距离度量：cosine
- 批量写入大小：50 条
- 额外方法：`delete_articles()`

### 5.3 LLMClientProtocol

```python
class LLMClientProtocol(Protocol):
    def generate(self, system_prompt: str, user_message: str) -> str: ...
    def generate_stream(self, system_prompt: str, user_message: str) -> Iterator[str]: ...
```

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

---

## 6. 数据流架构

### 6.1 Pipeline 数据流（定时/手动触发）

```
RSS 源 (feeds_config.json)
    │
    ▼
NewsCollector.fetch_all()
    │  feedparser 解析 RSS → trafilatura 提取正文
    │  反爬检测 / 微信链接特殊处理 / HTML 内容保存
    ▼
list[Article]  (内存)
    │
    ▼
SQLiteArticleStore.save_articles()
    │  SHA256(url) 去重 → INSERT OR SKIP
    ▼
SQLite articles 表
    │
    ▼
SQLiteArticleStore.get_unembedded()
    │  SELECT WHERE status != 'embedded'
    ▼
EmbeddingClient.embed()
    │  批量生成向量 (50条/批)
    ▼
ChromaVectorStore.add_articles()
    │  upsert 到 ChromaDB
    ▼
SQLiteArticleStore.mark_embedded()
    │  UPDATE status = 'embedded'
    ▼
完成 ✓
```

### 6.2 RAG 查询数据流

```
用户问题 (前端/CLI)
    │
    ▼
QueryService.answer() / answer_stream()
    │
    ├─ EmbeddingClient.embed([question])  → 查询向量
    │
    ├─ ChromaVectorStore.search(query_embedding, top_k)
    │     cosine 相似度检索 → list[SearchResult]
    │
    ├─ 回退：若向量化失败 → ArticleStore.search_by_keyword()
    │
    ├─ _build_context(results)
    │     格式化为 "[来源|日期] 标题\n摘要\nURL" 的 Markdown
    │
    └─ LLMClient.generate(QA_SYSTEM_PROMPT, context + question)
          │  或 generate_stream() 用于 SSE 流式
          ▼
        AI 回答 → 返回前端
```

### 6.3 简报生成数据流

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
    └─ DailyBrief.save_to_file(output_path)
          → output/daily_brief_YYYY-MM-DD.md
```

---

## 7. 前后端交互架构

### 7.1 API 路由一览

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/news` | 分页获取新闻列表（支持来源/语言/关键词筛选） |
| GET | `/api/news/stats` | 数据库统计 |
| GET | `/api/news/sources` | 所有新闻来源 |
| GET | `/api/news/{id}` | 单篇新闻全文 |
| POST | `/api/news/pipeline` | 手动触发 Pipeline |
| POST | `/api/news/batch-delete` | 批量删除文章（含向量记录） |
| GET | `/api/briefs` | 简报文件列表 |
| GET | `/api/briefs/{filename}` | 单份简报内容 |
| POST | `/api/briefs/generate` | 手动生成简报 |
| POST | `/api/query` | 非流式问答 |
| POST | `/api/query/stream` | SSE 流式问答 |
| GET | `/api/config` | 获取配置（API Key 脱敏） |
| PUT | `/api/config` | 更新 .env 配置 |
| GET | `/api/config/providers` | LLM 提供商列表 |
| POST | `/api/config/models` | 远程获取可用模型列表 |
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
| `/query` | `QueryView.vue` | 智能问答（SSE 流式输出） |
| `/settings` | `SettingsView.vue` | RSS 源管理 + 调度参数配置 |
| `/config` | `ConfigView.vue` | LLM/Embedding API 配置管理 |

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
| LLM/Embedding API 参数 | `.env` 文件 | 前端 ConfigView 通过 API 读写 |
| RSS 源列表 | `data/feeds_config.json` | 前端 SettingsView 通过 API 增删 |
| 调度参数 | `.env` 文件 | 前端 SettingsView 通过 API 读写 |
| 应用默认值 | `core/config.py` AppConfig | 代码内 pydantic Field default |

### 8.2 AppConfig 关键字段

```python
class AppConfig(BaseSettings):
    llm_provider: Literal["openai_compatible", "openai", "gemini", "anthropic"]
    llm_api_key / llm_base_url / llm_model: str
    openai_api_key / google_api_key / anthropic_api_key: str
    embedding_api_key / embedding_base_url / embedding_model: str
    db_path: str = "data/news.db"
    chroma_path: str = "data/chroma"
    output_path: str = "output"
    fetch_interval_hours: int = 4
    daily_brief_hour: int = 8
    max_articles_per_fetch: int = 20
    article_retention_days: int = 90
    log_level: str = "INFO"
    rss_feeds: list[dict]   # 默认 3 个源
```

---

## 9. 异常层次

```
NewsAssistantError (基础异常)
├── CollectorError (抓取相关)
│   └── SourceUnavailableError (单源不可用)
├── StoreError (存储相关)
├── EmbeddingError (向量化相关)
├── LLMError (LLM 调用)
│   └── RateLimitError (限流)
└── ConfigError (配置错误)
```

所有外部调用失败通过 `@with_retry` 装饰器自动指数退避重试（默认 3 次，基数 2.0）。

---

## 10. 进程模型

当前系统运行时包含 **3 个独立进程**：

```
进程 1: FastAPI Server (delivery/server.py)
  └── uvicorn 监听 :8005
  └── 处理所有 /api/* 请求
  └── 可选：托管 Vue 静态资源

进程 2: Scheduler (scheduler/scheduler.py)
  └── APScheduler BlockingScheduler
  └── 启动时自动执行一次 fetch_and_store()
  └── 定时任务：Pipeline / 日报 / 清理

进程 3 (开发模式): Vite Dev Server
  └── 监听 :5173
  └── 代理 /api/* 到 :8005

进程 3 (备用): Streamlit (delivery/streamlit_app.py)
  └── 独立 UI 界面，通过 SQLite 文件共享数据
```

**进程间数据共享**：通过 SQLite 文件（支持并发读 + 单写）和文件系统（日报 .md 文件、feeds_config.json）。

---

## 11. 依赖注入模式

系统使用**工厂函数**（`core/factory.py`）作为简化版依赖注入：

```python
# 当前 factory.py — 硬编码为 Demo 实现
def create_article_store(config) -> ArticleStoreProtocol:
    return SQLiteArticleStore(config.db_path)        # 唯一实现

def create_vector_store(config) -> VectorStoreProtocol:
    return ChromaVectorStore(config.chroma_path)      # 唯一实现

def create_llm_client(config) -> LLMClientProtocol:
    match config.llm_provider:                        # 4 种实现
        case "openai_compatible": ...
        case "openai": ...
        case "gemini": ...
        case "anthropic": ...

def create_embedding_client(config) -> EmbeddingClientProtocol:
    return OpenAICompatibleEmbeddingClient(...)       # 唯一实现
```

> **注意**：当前 `factory.py` 中 `create_article_store` 和 `create_vector_store` 没有条件分支，直接返回 SQLite/ChromaDB 实现。原始 `demo_design.md` 中设计的 `store_backend` / `vector_backend` 配置字段**未在当前 config.py 中实现**。

---

## 12. 数据库 Schema

### SQLite articles 表

```sql
CREATE TABLE articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash     TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    content      TEXT,
    html_content TEXT,           -- 超出 Demo 设计，已支持 HTML 原文存储
    summary      TEXT,
    source       TEXT,
    language     TEXT,           -- "en" | "zh" | "unknown"
    published_at TEXT,           -- ISO 8601 格式
    created_at   TEXT DEFAULT (datetime('now')),
    status       TEXT DEFAULT 'stored'  -- raw | stored | embedded
);

-- 索引
CREATE INDEX idx_status ON articles(status);
CREATE INDEX idx_created_at ON articles(created_at);
CREATE INDEX idx_source ON articles(source);
```

### ChromaDB Collection

- Collection: `news_articles`
- 距离度量: cosine
- Document: `article.to_embedding_text()` (标题+正文, max 2000 字符)
- Metadata: `{article_id, title, url, source, published_at, language}`
- ID 格式: `article_{db_id}`

---

## 13. 当前已知局限性

| 局限 | 影响 | 对应目标方案升级 |
|---|---|---|
| SQLite 单写锁 | Pipeline 运行时阻塞查询写入 | → PostgreSQL |
| ChromaDB 本地单机 | 无法分布式部署 | → Qdrant Cloud |
| APScheduler 单进程 | 无并发任务、无持久化队列 | → Celery + Redis |
| RSS 串行抓取 | 源多时抓取慢 | → ThreadPoolExecutor 并发 |
| 仅语义检索 | 缺少全文搜索能力 | → RRF 混合检索 |
| 标准 logging | 非结构化，难以查询 | → structlog |
| 无推送通知 | 用户需主动查看 | → Telegram Bot |
| 单环境 .env | 无 dev/prod 区分 | → 多环境 .env |
| 无容器化 | 部署需手动配置 | → Docker Compose |
| API Router 每次请求重建服务实例 | 重复初始化开销 | → 应用级单例 / DI 容器 |
| 无认证/授权 | 任何人可访问 API | → 身份认证中间件 |

---

## 14. 运行方式

```bash
# 1. 安装依赖
pip install -r requirements.txt
cd frontend && pnpm install && cd ..

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key 和端点

# 3. 启动后端 (终端 1)
python -m delivery.server

# 4. 启动前端开发服务器 (终端 2)
cd frontend && pnpm dev

# 5. 启动调度器 (终端 3)
python -m scheduler.scheduler

# 或使用 CLI 调试
python -m delivery.cli pipeline
python -m delivery.cli ask "今天有什么重要新闻？"
python -m delivery.cli stats
```
