# Logos 目标架构文档

> [!WARNING]
> 此文档为历史设计方案。文中的 SQLite、ChromaDB 和 APScheduler 均已被完全废弃。最新架构请参考项目根目录的 `ARCHITECTURE.md`。
> **文档版本**：v1.0
> **基于设计方案**：`full_design.md` v2.0 + `Development Plan.md`
> **目标阶段**：生产级系统（Full）
> **核心原则**：所有 Protocol 接口保持不变，只替换 `infrastructure/` 层内部实现

---

## 1. 目标系统概览

在当前 Demo+ 基础上升级为生产级系统，支持：

- **数百个新闻来源**，每天处理数万条文章
- **云端部署**，任何设备可访问
- **并发抓取**，多种来源类型（RSS / API / 网页爬虫）
- **Telegram Bot** 推送早报
- **全平台 Webhook** 推送通知
- **RRF 混合检索**（全文索引 + 向量 + Reciprocal Rank Fusion）
- **多 Agent 分析**，深度研究与报告功能
- 完善的**监控、结构化日志与容器化部署**

---

## 2. 技术选型升级对照

| 模块 | 当前实现 | 目标实现 | 升级理由 |
|---|---|---|---|
| **元数据存储** | SQLite | **PostgreSQL 16** | 并发写入、全文搜索（pg_trgm + tsvector）、云托管 |
| **向量库** | ChromaDB 本地 | **Qdrant Cloud** | 托管服务、亿级向量、payload 过滤 |
| **任务调度** | APScheduler（独立进程） | **Celery + Redis** | 并发执行、任务重试、Flower 监控面板 |
| **日志** | logging 标准库 | **structlog** | 结构化 JSON 日志，便于聚合查询 |
| **正文提取** | trafilatura（串行） | trafilatura + **ThreadPoolExecutor** | 并发抓取，同接口内部并发化 |
| **新闻来源** | RSS only | RSS + **NewsAPI** + **网页爬虫** | 扩大覆盖范围 |
| **推送通知** | 无 | **Telegram Bot** + **Webhook** + **ntfy** | 主动推送，多渠道 |
| **检索策略** | 纯语义检索 | **RRF 混合检索** | 语义 + 关键词 + 排序融合 |
| **配置管理** | 单一 .env | **多环境 .env** (.env.dev / .env.prod) | 环境隔离 |
| **部署** | 本地运行 | **Docker Compose** + 云平台 | 一键部署，弹性扩展 |
| **前端框架** | Vue 3 + Vite | Vue 3 + Vite（保持） | 已满足需求 |
| **Web 框架** | FastAPI | FastAPI（保持） | 已满足需求 |

---

## 3. 目标分层架构

```
┌────────────────────────────────────────────────────────────────────────┐
│                         前端表现层 (Frontend)                          │
│   Vue 3 SPA (保持当前架构，补充更多统计面板)                            │
├────────────────────────────────────────────────────────────────────────┤
│                        后端表现层 (Delivery)                           │
│   FastAPI Server                                                       │
│   ├── 现有 API 路由（保持不变）                                        │
│   ├── [NEW] Telegram Bot (telegram_bot.py)                             │
│   │     /brief  /ask  /sources  /stats                                 │
│   │     每日定时自动推送简报                                            │
│   ├── [NEW] Webhook 推送 (webhook_delivery.py)                        │
│   │     全平台 Webhook + ntfy                                          │
│   └── CLI (保持)                                                       │
├────────────────────────────────────────────────────────────────────────┤
│                        应用服务层 (Services)                           │
│   PipelineService（不变）│ BriefService（不变）                        │
│   QueryService — 升级 search() 实现完整 RRF 混合检索                   │
│   [FUTURE] DeepResearchService — 多 Agent 深度研究与报告               │
├────────────────────────────────────────────────────────────────────────┤
│                        领域模型层 (Models)                             │
│   Article │ DailyBrief │ SearchQuery │ SearchResult （保持不变）       │
├────────────────────────────────────────────────────────────────────────┤
│                       基础设施层 (Infrastructure)                      │
│   NewsCollector — 并发 ThreadPoolExecutor + NewsAPI + 网页爬虫         │
│   [NEW] PostgreSQLArticleStore — 全文搜索 (tsvector + GIN)            │
│   [NEW] QdrantVectorStore — Cloud 托管 + payload 过滤                 │
│   LLM/Embedding Clients（保持不变）                                    │
├────────────────────────────────────────────────────────────────────────┤
│                       横切关注点 (Core)                                │
│   AppConfig — 多环境支持 + PostgreSQL/Qdrant 连接配置                  │
│   Protocols — 保持不变                                                 │
│   Factory — 新增 postgresql / qdrant 分支                              │
│   Logging — 替换为 structlog                                           │
│   Exceptions / Retry — 保持不变                                        │
├────────────────────────────────────────────────────────────────────────┤
│                        调度层 (Scheduler)                              │
│   [NEW] Celery + Redis (celery_app.py + tasks.py)                     │
│   定时：Pipeline 每 4h │ 日报 每天 8:00 │ 清理 每周日 3:00            │
│   保留 APScheduler 版本作后备                                          │
├────────────────────────────────────────────────────────────────────────┤
│                        基础设施运维 (Infra)                            │
│   [NEW] Docker Compose: PostgreSQL + Redis + Qdrant + Flower          │
│   [NEW] Dockerfile / nginx.conf                                       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 目标目录结构

```
Logos/
├── models/                         #  不变
│   ├── article.py
│   ├── brief.py
│   └── search.py
│
├── core/                           #  升级
│   ├── config.py                   # 新增: 多环境支持, PG DSN, Qdrant URL 等
│   ├── protocols.py                #  不变
│   ├── factory.py                  #  新增: postgresql / qdrant 分支
│   ├── exceptions.py               #  不变
│   ├── logging.py                  #  替换为 structlog
│   └── retry.py                    #  不变
│
├── infrastructure/                 #  新增实现
│   ├── collector.py                #  并发 ThreadPoolExecutor + NewsAPI + 网页爬虫
│   ├── article_store.py            #  新增 PostgreSQLArticleStore
│   ├── vector_store.py             #  新增 QdrantVectorStore
│   ├── llm_client.py               #  不变
│   └── embedding_client.py         #  不变
│
├── services/                       #  局部升级
│   ├── pipeline_service.py         #  不变（依赖 Protocol，自动适配新实现）
│   ├── query_service.py            #  search() 升级为 RRF 混合检索
│   └── brief_service.py            #  不变
│
├── delivery/                       #  新增 Telegram Bot + Webhook
│   ├── server.py                   #  保持
│   ├── cli.py                      #  保持
│   ├── telegram_bot.py             #  Telegram 推送 + 命令
│   ├── webhook_delivery.py         #  全平台 Webhook + ntfy
│   └── api/                        #  保持
│
├── scheduler/                      #  替换为 Celery
│   ├── celery_app.py               #  Celery 应用配置 + beat_schedule
│   ├── tasks.py                    #  Celery 任务定义
│   └── scheduler.py                #  保留 APScheduler 版本作后备
│
├── infra/                          #  部署配置
│   ├── docker-compose.yml          # PostgreSQL + Redis + Qdrant + Flower
│   ├── docker-compose.dev.yml      # 开发环境覆写
│   ├── Dockerfile                  # 应用容器
│   └── nginx.conf                  # 反向代理 (VPS 部署)
│
├── frontend/                       #  保持（补充统计面板）
│
├── tests/                          #  扩展
│   ├── test_article_store.py       # 新增 PostgreSQL 测试
│   ├── test_vector_store.py        # 新增 Qdrant 测试
│   ├── test_telegram_bot.py        # 
│   └── ...                         # 目标覆盖率 > 80%
│
├── .env.example
├── .env.dev                        #  开发环境
├── .env.prod                       #  生产环境
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 5. 模块升级详细设计

### 5.1 core/config.py — 多环境配置

```python
class AppConfig(BaseSettings):
    # 新增: 存储后端选择
    store_backend: Literal["sqlite", "postgresql"] = "sqlite"
    vector_backend: Literal["chroma", "qdrant"] = "chroma"

    # 新增: PostgreSQL 连接
    pg_dsn: str = "postgresql://news:changeme@localhost:5432/news_assistant"

    # 新增: Qdrant Cloud
    qdrant_url: str = ""
    qdrant_api_key: str = ""

    # 新增: Celery / Redis
    celery_broker_url: str = "redis://localhost:6379/0"

    # 新增: Telegram Bot
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # 新增: NewsAPI
    newsapi_key: str = ""

    # 新增: 多环境支持
    environment: Literal["dev", "staging", "prod"] = "dev"

    class Config:
        env_file = ".env"        # 默认
        # 可通过 _env_file 参数指定 .env.dev / .env.prod
```

### 5.2 core/factory.py — 条件创建

```python
def create_article_store(config: AppConfig) -> ArticleStoreProtocol:
    match config.store_backend:
        case "sqlite":
            from infrastructure.article_store import SQLiteArticleStore
            return SQLiteArticleStore(config.db_path)
        case "postgresql":
            from infrastructure.article_store import PostgreSQLArticleStore
            return PostgreSQLArticleStore(config.pg_dsn)

def create_vector_store(config: AppConfig) -> VectorStoreProtocol:
    match config.vector_backend:
        case "chroma":
            from infrastructure.vector_store import ChromaVectorStore
            return ChromaVectorStore(config.chroma_path)
        case "qdrant":
            from infrastructure.vector_store import QdrantVectorStore
            return QdrantVectorStore(config.qdrant_url, config.qdrant_api_key)
```

### 5.3 infrastructure/article_store.py — PostgreSQLArticleStore

**Protocol 接口不变**，新增 PostgreSQL 实现。

关键升级点：
- 使用 `psycopg2` 连接 PostgreSQL
- 全文搜索：`tsvector` + `GIN` 索引，`search_by_keyword()` 升级为 `to_tsquery`
- 所有方法签名与 `SQLiteArticleStore` 完全一致

```sql
-- 新增全文搜索字段
ALTER TABLE articles ADD COLUMN content_tsv tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title,'') || ' ' || coalesce(content,''))
    ) STORED;

CREATE INDEX idx_content_tsv ON articles USING GIN(content_tsv);
```

### 5.4 infrastructure/vector_store.py — QdrantVectorStore

**Protocol 接口不变**，新增 Qdrant 实现。

```python
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams

class QdrantVectorStore:
    def __init__(self, url: str, api_key: str):
        self.client = QdrantClient(url=url, api_key=api_key)

    def add_articles(self, articles, embeddings) -> int:
        # PointStruct + upsert

    def search(self, query_embedding, top_k, filters) -> list[SearchResult]:
        # 支持 payload 过滤 (source, language, published_at)
```

### 5.5 infrastructure/collector.py — 并发 + 多来源

**Protocol 接口不变**，内部实现升级。

```python
class NewsCollector:
    def fetch_all(self) -> list[Article]:
        # ThreadPoolExecutor(max_workers=5) 并发抓取所有 RSS 源
        # 随机延迟 0.5-2s，每请求超时 30s

    def fetch_newsapi(self, query: str, from_date: str | None = None) -> list[Article]:
        # [NEW] 调用 NewsAPI /everything 端点

    def fetch_webpage(self, url: str) -> Article | None:
        # [NEW] 直接抓取单个网页
```

**未来扩展（Development Plan）**：
- 网页爬虫集成（Crawlee 等），下载并保存 HTML 文件
- AI 调用搜索新闻
- AI 打标签 / 摘要生成

### 5.6 services/query_service.py — RRF 混合检索

```python
def search(self, query: SearchQuery) -> list[SearchResult]:
    """
    完整 RRF (Reciprocal Rank Fusion) 混合检索：
    1. 语义检索：Qdrant 向量搜索，支持 payload 过滤
    2. 关键词检索：PostgreSQL to_tsquery 全文搜索
    3. RRF 合并：score = Σ 1/(k + rank_i)，k=60
    4. 按 RRF 分数降序返回 top_k 条
    """
```

### 5.7 delivery/telegram_bot.py — 新增

```python
class TelegramDelivery:
    """
    命令：
      /brief   — 立即生成并发送今日简报
      /ask <问题> — 触发 RAG 查询
      /sources — 列出当前订阅的新闻来源
      /stats   — 查看数据库统计

    自动推送：
      每天 config.daily_brief_hour 自动推送简报
    """
    def send_brief(self, brief_markdown: str) -> None: ...
    def start_bot(self) -> None: ...
```

使用 `python-telegram-bot` v20+ async 模式。

### 5.8 scheduler/ — Celery 替代

```python
# scheduler/celery_app.py
app = Celery('news_assistant', broker='redis://localhost:6379/0')

app.conf.beat_schedule = {
    'pipeline-every-4h': {
        'task': 'scheduler.tasks.run_pipeline',
        'schedule': crontab(minute=0, hour='*/4'),
    },
    'daily-brief': {
        'task': 'scheduler.tasks.run_daily_brief',
        'schedule': crontab(minute=0, hour=8),
    },
    'weekly-cleanup': {
        'task': 'scheduler.tasks.run_cleanup',
        'schedule': crontab(minute=0, hour=3, day_of_week='sun'),
    },
}

# scheduler/tasks.py
@app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_pipeline(self): ...

@app.task
def run_daily_brief(): ...

@app.task
def run_cleanup(): ...
```

---

## 6. 部署架构

### 6.1 Docker Compose 全景

```
                    ┌──────────────────────────────────────────────┐
                    │              Docker Compose                   │
                    │                                              │
  Browser ────▶     │  ┌──────┐      ┌──────────────────────┐     │
                    │  │nginx │─────▶│  web (FastAPI+Vue)   │     │
                    │  │:80   │      │  :8005               │     │
                    │  └──────┘      └─────────┬────────────┘     │
                    │                          │                   │
                    │         ┌────────────────┼────────┐         │
                    │         ▼                ▼        ▼         │
                    │  ┌───────────┐  ┌──────────┐  ┌────────┐   │
                    │  │PostgreSQL │  │ Qdrant   │  │ Redis  │   │
                    │  │ :5432     │  │ :6333    │  │ :6379  │   │
                    │  └───────────┘  └──────────┘  └───┬────┘   │
                    │                                    │        │
                    │         ┌──────────────────────────┤        │
                    │         ▼                          ▼        │
                    │  ┌───────────┐            ┌──────────────┐  │
                    │  │ worker    │            │ beat         │  │
                    │  │ (Celery)  │            │ (Celery Beat)│  │
                    │  └───────────┘            └──────────────┘  │
                    │         │                                    │
                    │         ▼                                    │
                    │  ┌───────────┐                               │
                    │  │ flower    │  (Celery 监控面板 :5555)       │
                    │  └───────────┘                               │
                    └──────────────────────────────────────────────┘

  Telegram ◄──── TelegramDelivery (可集成在 web 或独立进程)
```

### 6.2 docker-compose.yml 服务清单

| 服务 | 镜像 | 端口 | 用途 |
|---|---|---|---|
| `postgres` | postgres:16 | 5432 | 文章元数据 + 全文索引 |
| `redis` | redis:7 | 6379 | Celery Broker |
| `qdrant` | qdrant/qdrant | 6333 | 向量检索 |
| `web` | 自定义 Dockerfile | 8501 | FastAPI + Vue 静态资源 |
| `worker` | 自定义 Dockerfile | — | Celery Worker (Pipeline/Brief/Cleanup) |
| `beat` | 自定义 Dockerfile | — | Celery Beat (定时触发) |
| `flower` | 自定义 Dockerfile | 5555 | Celery 任务监控 UI |

### 6.3 云部署选项

| 方案 | 优势 | 适用场景 |
|---|---|---|
| **Railway** | GitHub 连接自动部署、内置 PG+Redis 插件 | 新手推荐 |
| **Render** | Web Service + Background Worker 分离 | 简单部署 |
| **VPS (DO/Vultr)** | docker-compose 一键部署、完全可控 | $6/月起 |

---

## 7. Protocol 接口对照表 — 当前 vs 目标

| Protocol | 方法 | 当前实现 | 目标实现 | 接口是否变化 |
|---|---|---|---|---|
| `ArticleStoreProtocol` | `save_articles()` | SQLiteArticleStore | PostgreSQLArticleStore |  不变 |
| `ArticleStoreProtocol` | `search_by_keyword()` | LIKE 查询 | to_tsquery 全文搜索 |  不变 |
| `VectorStoreProtocol` | `add_articles()` | ChromaVectorStore | QdrantVectorStore |  不变 |
| `VectorStoreProtocol` | `search()` | 本地向量搜索 | Qdrant Cloud + payload 过滤 |  不变 |
| `LLMClientProtocol` | `generate()` | 多后端（4 种） | 多后端（保持不变） |  不变 |
| `EmbeddingClientProtocol` | `embed()` | 自定义 API | 自定义 API（保持） |  不变 |
| — | Scheduler | APScheduler | Celery Beat + Worker | N/A (非 Protocol) |
| — | 检索策略 | 纯语义检索 | RRF 混合检索 | N/A (服务内部逻辑) |
| — | 推送 | 无 | Telegram Bot + Webhook | N/A (新增 Delivery) |

> **核心保证**：升级时只修改 `core/factory.py` 的创建逻辑和 `infrastructure/` 的实现类。
> `services/` 层通过 Protocol 接口调用，**几乎不动**（仅 QueryService.search() 内部逻辑升级为 RRF）。
> `delivery/` 层调用 `services/`，**不动**（仅新增 Telegram/Webhook Delivery）。

---

## 8. 升级路线图

### Phase 0 → Phase 1：基础设施替换（影响范围最小）

```
当前状态:  SQLite + ChromaDB + APScheduler + logging

Phase 0 - 配置基建:
  ├── config.py 新增 store_backend / vector_backend / pg_dsn 等字段
  ├── factory.py 新增条件分支
  └── logging.py 替换为 structlog

Phase 1 - 存储替换:
  ├── 实现 PostgreSQLArticleStore (同接口)
  ├── 实现 QdrantVectorStore (同接口)
  ├── factory.py 按 config 选择实现
  └── 验证: 所有现有测试在新实现下通过
```

### Phase 2：抓取能力增强

```
Phase 2 - Collector 升级:
  ├── ThreadPoolExecutor 并发抓取
  ├── NewsAPI 集成
  ├── 网页爬虫研究与集成 (Crawlee 等)
  └── 验证: fetch_all() 性能提升 3-5x
```

### Phase 3：检索与分析升级

```
Phase 3 - 智能升级:
  ├── QueryService.search() → RRF 混合检索
  ├── AI 标签打标 / 多 Agent 分析 (远期)
  └── 验证: 检索召回率显著提升
```

### Phase 4：交付渠道扩展

```
Phase 4 - 新 Delivery:
  ├── Telegram Bot (命令 + 自动推送)
  ├── 全平台 Webhook + ntfy
  └── 验证: Bot 能推送日报、响应命令
```

### Phase 5：调度与部署

```
Phase 5 - 生产化:
  ├── Celery + Redis 替换 APScheduler
  ├── Docker Compose 编排
  ├── 多环境 .env 配置
  ├── 测试覆盖率 > 80%
  └── 验证: docker-compose up 一键启动全部服务
```

---

## 9. 升级影响矩阵

### 需要修改的文件

| 文件 | 修改类型 | 升级阶段 | 风险 |
|---|---|---|---|
| `core/config.py` | 新增字段 | Phase 0 | 低 |
| `core/factory.py` | 新增分支 | Phase 0 | 低 |
| `core/logging.py` | 替换实现 | Phase 0 | 低 |
| `infrastructure/article_store.py` | 新增类 | Phase 1 | 中 |
| `infrastructure/vector_store.py` | 新增类 | Phase 1 | 中 |
| `infrastructure/collector.py` | 内部并发化 + 新方法 | Phase 2 | 中 |
| `services/query_service.py` | search() 内部逻辑 | Phase 3 | 中 |
| `delivery/telegram_bot.py` | 新增文件 | Phase 4 | 低 |
| `scheduler/celery_app.py` | 新增文件 | Phase 5 | 中 |
| `scheduler/tasks.py` | 新增文件 | Phase 5 | 中 |
| `infra/docker-compose.yml` | 新增文件 | Phase 5 | 低 |
| `infra/Dockerfile` | 新增文件 | Phase 5 | 低 |

### 完全不需要修改的文件

| 文件 | 原因 |
|---|---|
| `models/*.py` | 纯数据定义，与实现无关 |
| `core/protocols.py` | 接口契约保持不变 |
| `core/exceptions.py` | 异常层次不变 |
| `core/retry.py` | 工具函数不变 |
| `infrastructure/llm_client.py` | LLM 调用不变 |
| `infrastructure/embedding_client.py` | Embedding 调用不变 |
| `services/pipeline_service.py` | 依赖 Protocol，自动适配 |
| `services/brief_service.py` | 依赖 Protocol，自动适配 |
| `delivery/server.py` | API 入口不变 |
| `delivery/api/*.py` | API 路由不变 |
| `delivery/cli.py` | CLI 不变 |
| `frontend/**` | 前端不变（可补充统计面板） |

---

## 10. 新增依赖

```txt
# Phase 0
structlog>=24.0.0

# Phase 1
psycopg2-binary>=2.9.0        # PostgreSQL 驱动
qdrant-client>=1.9.0           # Qdrant 客户端

# Phase 2
newsapi-python>=0.2.7          # NewsAPI 客户端

# Phase 4
python-telegram-bot>=20.0      # Telegram Bot

# Phase 5
celery[redis]>=5.3.0           # 任务队列
flower>=2.0.0                  # Celery 监控
redis>=5.0.0                   # Redis 客户端
```

---

## 11. 数据库 Schema 演进

### PostgreSQL articles 表（目标）

```sql
CREATE TABLE articles (
    id           SERIAL PRIMARY KEY,
    url_hash     TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    content      TEXT,
    html_content TEXT,
    summary      TEXT,
    source       TEXT,
    language     TEXT,
    published_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT now(),
    status       TEXT DEFAULT 'stored',

    -- 全文搜索 (自动生成)
    content_tsv  TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title,'') || ' ' || coalesce(content,''))
    ) STORED
);

-- 索引
CREATE INDEX idx_status ON articles(status);
CREATE INDEX idx_created_at ON articles(created_at);
CREATE INDEX idx_source ON articles(source);
CREATE INDEX idx_content_tsv ON articles USING GIN(content_tsv);   -- 全文搜索
CREATE INDEX idx_url_hash ON articles(url_hash);                   -- 去重加速
```

### Qdrant Collection（目标）

```
Collection: news_articles
  Vector: 维度由 Embedding 模型决定 (如 1536)
  Distance: Cosine
  Payload:
    - article_id: int
    - title: str
    - url: str
    - source: str
    - language: str
    - published_at: str (ISO 8601)
  Payload Index: source, language, published_at
```

---

## 12. 监控与可观测性（目标）

| 组件 | 工具 | 用途 |
|---|---|---|
| 任务监控 | Flower (:5555) | Celery Worker/Beat 状态、任务历史 |
| 结构化日志 | structlog → JSON | 所有服务统一 JSON 格式日志 |
| 健康检查 | `/api/health` + Docker HEALTHCHECK | 服务存活检测 |
| 数据统计 | `/api/news/stats` + Streamlit 面板 | 文章数量、来源分布 |

---

## 13. Development Plan 远期规划

以下需求来自 `Development Plan.md`，属于超越 `full_design.md` 的远期目标：

| 需求 | 说明 | 优先级 |
|---|---|---|
| 网页爬虫 (Crawlee) | 抓取网页新闻，下载并保存 HTML | P1 |
| AI 搜索新闻 | LLM 驱动的新闻发现 | P2 |
| AI 打标签 | AI 给缺少标签的新闻自动分类 | P2 |
| AI 摘要 (Multi-Agent) | 多 Agent 协作生成概要 | P3 |
| 可编辑提示词（世界书化） | 用户自定义分析模板 | P2 |
| Deep Research | 深度研究与报告功能 | P3 |
| 平台机器人对接 | 多平台 Bot 检索+回答 | P2 |
| 全平台 Webhook | 推送到各种平台 | P1 |
| ntfy 推送 | 轻量推送通道 | P1 |

---

## 14. 架构决策记录 (ADR)

### ADR-001: Protocol 接口保持不变

**决策**：升级过程中所有 4 个 Protocol 接口签名不变。
**理由**：确保 `services/` 和 `delivery/` 层零修改，降低升级风险。
**影响**：新实现必须严格遵循现有接口契约。

### ADR-002: 工厂函数而非 DI 容器

**决策**：继续使用 `core/factory.py` 工厂函数，不引入 DI 框架。
**理由**：项目规模适中，工厂函数已足够；避免引入额外复杂度。
**影响**：新增实现时只需修改工厂函数的条件分支。

### ADR-003: 保留 APScheduler 作后备

**决策**：引入 Celery 后保留 `scheduler/scheduler.py`。
**理由**：Celery 需要 Redis 基础设施；本地开发或轻量部署场景仍可使用 APScheduler。
**影响**：两套调度方案并存，通过启动脚本选择。

### ADR-004: 前后端分离保持现状

**决策**：前端继续使用 Vue 3 + Vite，不迁移到其他框架。
**理由**：当前架构已满足需求，迁移成本大于收益。
**影响**：仅在现有框架上补充功能（统计面板等）。
