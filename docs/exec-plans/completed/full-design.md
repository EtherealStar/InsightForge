# Logos 个人新闻分析助手 — 完整方案（v2）

> [!WARNING]
> 此文档为历史设计方案。文中的 SQLite、ChromaDB 和 APScheduler 均已被完全废弃。最新架构请参考项目根目录的 `ARCHITECTURE.md`。
> **文档版本**：v2.0  
> 本文档定义从 Demo 原型到生产级系统的升级路径。  
> 核心原则：**所有 Protocol 接口保持不变**，只替换 `infrastructure/` 层的内部实现，`services/` 和 `delivery/` 层代码不需要修改。

---

## 1. 完整方案目标

在 Demo 基础上支持：
- 数百个新闻来源，每天数万条文章
- 云端部署，任何设备可访问
- 并发抓取，任务队列管理
- Telegram Bot 推送早报
- 更强的搜索能力（全文索引 + 向量 + RRF 混合检索）
- 完善的监控和日志

---

## 2. 技术选型升级对照

| 模块 | Demo 实现 | 完整方案实现 | 升级理由 |
|---|---|---|---|
| 任务调度 | APScheduler（独立进程） | **Celery + Redis** | 并发执行、任务重试、Flower 监控 |
| 元数据存储 | SQLite | **PostgreSQL** | 并发写入、全文搜索（pg_trgm + tsvector）、云托管 |
| 向量库 | ChromaDB 本地 | **Qdrant Cloud** | 托管服务、亿级向量、payload 过滤 |
| 界面部署 | 本地 Streamlit | **Railway / Render** | 随时随地访问 |
| 推送通知 | 无 | **Telegram Bot** | 早报自动推手机 |
| 配置管理 | pydantic-settings + .env | **pydantic-settings + 多环境 .env** | 多环境配置（dev/staging/prod） |
| 日志 | logging 标准库 | **structlog** | 结构化日志，JSON 格式，便于查询 |
| 正文提取 | trafilatura | trafilatura + **并发 ThreadPool** | 同接口，内部并发化 |

---

## 3. 完整方案目录结构

```
news_assistant/
├── models/                        # 不变，与 Demo 共享
│   ├── __init__.py
│   ├── article.py
│   ├── brief.py
│   └── search.py
│
├── core/                          # 升级配置和日志
│   ├── __init__.py
│   ├── config.py                  # 新增多环境支持、PostgreSQL/Qdrant 连接串
│   ├── protocols.py               # 不变，与 Demo 共享
│   ├── factory.py                 # 新增 postgresql / qdrant 分支
│   ├── exceptions.py              # 不变
│   ├── logging.py                 # 替换为 structlog
│   └── retry.py                   # 不变
│
├── infrastructure/                # 新增或替换实现
│   ├── __init__.py
│   ├── collector.py               # 新增并发抓取 + NewsAPI 支持
│   ├── article_store.py           # 新增 PostgreSQLArticleStore
│   ├── vector_store.py            # 新增 QdrantVectorStore
│   ├── llm_client.py              # 不变（已支持多后端）
│   └── embedding_client.py        # 不变
│
├── services/                      # 不变，与 Demo 共享
│   ├── __init__.py
│   ├── pipeline_service.py
│   ├── query_service.py           # 升级：实现完整 RRF 混合检索
│   └── brief_service.py
│
├── delivery/                      # 新增 Telegram Bot
│   ├── __init__.py
│   ├── streamlit_app.py           # 补充更多统计面板
│   ├── telegram_bot.py            # [NEW] Telegram Bot
│   └── cli.py
│
├── scheduler/                     # 替换为 Celery
│   ├── __init__.py
│   ├── celery_app.py              # [NEW] Celery 应用配置
│   ├── tasks.py                   # [NEW] Celery 任务定义
│   └── scheduler.py               # 保留 APScheduler 版本作后备
│
├── infra/                         # [NEW] 部署配置
│   ├── docker-compose.yml         # PostgreSQL + Redis + Qdrant + Flower
│   ├── docker-compose.dev.yml     # 开发环境覆写
│   ├── Dockerfile                 # 应用容器
│   └── nginx.conf                 # 反向代理（VPS 部署用）
│
├── tests/                         # 扩展测试
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_collector.py
│   ├── test_article_store.py      # 新增 PostgreSQL 测试
│   ├── test_vector_store.py       # 新增 Qdrant 测试
│   ├── test_pipeline_service.py
│   ├── test_query_service.py
│   └── test_telegram_bot.py       # [NEW]
│
├── data/
├── output/
├── .env.example
├── .env.dev                       # [NEW] 开发环境配置
├── .env.prod                      # [NEW] 生产环境配置
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 4. 各模块升级说明

### 4.1 infrastructure/collector.py — 并发抓取

**Protocol 接口不变**，内部实现变化：

```python
from concurrent.futures import ThreadPoolExecutor

class NewsCollector:
    # fetch_all() 接口不变
    # 内部使用 ThreadPoolExecutor 并发抓取所有 RSS 源
    # 新增方法：

    def fetch_newsapi(self, query: str, from_date: str | None = None) -> list[Article]:
        """调用 NewsAPI /everything 端点，返回统一 Article 格式"""
        pass

    def fetch_webpage(self, url: str) -> Article | None:
        """直接抓取单个网页，用 trafilatura 提取正文"""
        pass
```

实现要点：
- `ThreadPoolExecutor(max_workers=5)` 并发抓取
- 所有请求加入随机延迟（0.5-2 秒），避免被封
- 超时控制：每个请求最多 30 秒

---

### 4.2 infrastructure/article_store.py — PostgreSQL

**Protocol 接口不变**，新增 `PostgreSQLArticleStore` 实现：

```python
class PostgreSQLArticleStore:
    """实现 ArticleStoreProtocol，后端为 PostgreSQL"""

    def __init__(self, dsn: str):
        """使用 psycopg2 连接 PostgreSQL"""
        pass

    # 所有方法签名与 SQLiteArticleStore 完全一致
    # 内部改用 PostgreSQL 语法
```

新增 PostgreSQL 特性：

```sql
-- 全文搜索字段
ALTER TABLE articles ADD COLUMN content_tsv tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title,'') || ' ' || coalesce(content,''))
    ) STORED;

CREATE INDEX idx_content_tsv ON articles USING GIN(content_tsv);
```

`search_by_keyword` 升级为 `to_tsquery` 全文搜索。

---

### 4.3 infrastructure/vector_store.py — Qdrant

**Protocol 接口不变**，新增 `QdrantVectorStore` 实现：

```python
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams

class QdrantVectorStore:
    """实现 VectorStoreProtocol，后端为 Qdrant Cloud"""

    def __init__(self, url: str, api_key: str):
        """连接 Qdrant Cloud"""
        pass

    # add_articles / search 与 ChromaVectorStore 签名一致
    # 内部使用 PointStruct + upsert
    # search 支持 payload 过滤（source, language, published_at）
```

---

### 4.4 services/query_service.py — RRF 混合检索

升级 `search()` 方法实现完整 RRF：

```python
def search(self, query: SearchQuery) -> list[SearchResult]:
    """
    完整 RRF（Reciprocal Rank Fusion）混合检索：
    1. 语义检索：Qdrant 向量搜索，支持 payload 过滤
    2. 关键词检索：PostgreSQL to_tsquery 全文搜索
    3. RRF 合并：score = Σ 1/(k + rank_i)，k=60
    4. 按 RRF 分数降序返回 top_k 条
    """
    pass
```

---

### 4.5 delivery/telegram_bot.py — 新增

```python
"""Telegram Bot — 接收命令、推送简报"""
from core.protocols import LLMClientProtocol
from services.query_service import QueryService
from services.brief_service import BriefService

class TelegramDelivery:
    """
    命令：
    /brief  — 立即生成并发送今日简报
    /ask <问题> — 触发 RAG 查询
    /sources — 列出当前订阅的新闻来源
    /stats — 查看数据库统计

    自动推送：
    每天 config.daily_brief_hour 自动推送简报
    """

    def __init__(self, query_service: QueryService,
                 brief_service: BriefService,
                 bot_token: str, chat_id: str):
        pass

    def send_brief(self, brief_markdown: str) -> None:
        """将 Markdown 简报转为 Telegram HTML 格式发送"""
        pass

    def start_bot(self) -> None:
        """
        注册命令处理器，启动 polling。
        使用 python-telegram-bot v20+ async 模式。
        """
        pass
```

---

### 4.6 scheduler/ — Celery 替代

```python
# scheduler/celery_app.py
from celery import Celery
from celery.schedules import crontab

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
```

```python
# scheduler/tasks.py
from scheduler.celery_app import app

@app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_pipeline(self):
    """Celery 任务：执行 Pipeline"""
    pass

@app.task
def run_daily_brief():
    """Celery 任务：生成日报"""
    pass

@app.task
def run_cleanup():
    """Celery 任务：清理旧文章"""
    pass
```

---

## 5. infra/docker-compose.yml

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: news_assistant
      POSTGRES_USER: news
      POSTGRES_PASSWORD: ${PG_PASSWORD:-changeme}
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports: ["6379:6379"]

  qdrant:
    image: qdrant/qdrant
    ports: ["6333:6333"]
    volumes:
      - qdrant_data:/qdrant/storage

  worker:
    build: .
    command: celery -A scheduler.celery_app worker --loglevel=info
    depends_on: [postgres, redis, qdrant]
    env_file: .env.prod

  beat:
    build: .
    command: celery -A scheduler.celery_app beat --loglevel=info
    depends_on: [redis]
    env_file: .env.prod

  web:
    build: .
    command: streamlit run delivery/streamlit_app.py --server.port=8501
    ports: ["8501:8501"]
    depends_on: [postgres, qdrant]
    env_file: .env.prod

  flower:
    build: .
    command: celery -A scheduler.celery_app flower --port=5555
    ports: ["5555:5555"]
    depends_on: [redis]

volumes:
  pgdata:
  qdrant_data:
```

---

## 6. 部署方案

### 选项 A：Railway（推荐新手）
- 连 GitHub 仓库，push 自动部署
- 内置 PostgreSQL 和 Redis 插件，免费额度够个人用
- 环境变量在控制台配置

### 选项 B：Render
- Web Service + Background Worker 分开部署
- 注意免费层会休眠

### 选项 C：自建 VPS（DigitalOcean / Vultr）
- $6/月最低配置
- docker-compose 一键部署
- 需自行配 nginx 反向代理

---

## 7. Protocol 接口对照表 — Demo vs Full

| Protocol | 方法 | Demo 实现 | Full 实现 |
|---|---|---|---|
| `ArticleStoreProtocol` | `save_articles()` | SQLiteArticleStore | PostgreSQLArticleStore |
| `ArticleStoreProtocol` | `search_by_keyword()` | LIKE 查询 | to_tsquery 全文搜索 |
| `VectorStoreProtocol` | `add_articles()` | ChromaVectorStore | QdrantVectorStore |
| `VectorStoreProtocol` | `search()` | 本地向量搜索 | Qdrant Cloud + 过滤 |
| `LLMClientProtocol` | `generate()` | 多后端（不变） | 多后端（不变） |
| `EmbeddingClientProtocol` | `embed()` | 自定义 API（不变） | 自定义 API（不变） |
| — | Scheduler | APScheduler 独立进程 | Celery Beat + Worker |
| — | 检索策略 | 语义检索 | RRF 混合检索 |
| — | `QueryService.answer_stream()` | 单轮 | 多轮对话（带历史） |

> **核心原则**：升级时只修改 `core/factory.py` 的创建逻辑和 `infrastructure/` 的实现类。  
> `services/` 层通过 Protocol 接口调用，**一行不动**。  
> `delivery/` 层调用 `services/`，同样**一行不动**。

---

## 8. 开发路线图

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **Phase 0** | 项目结构 + 数据模型 + Config + 日志 + 异常框架 | `from models.article import Article` 成功 |
| **Phase 1** | Collector + ArticleStore + Embedder + VectorStore + Pipeline | `python -m delivery.cli pipeline` 能跑通 |
| **Phase 2** | QueryService + BriefService + Streamlit UI | Streamlit 能提问并获得回答 |
| **Phase 3** | Scheduler 独立进程 + CLI + 日报自动生成 | 两终端分别启动，4 小时后自动抓取 |
| **Phase 4** | Telegram Bot + 数据清理 | Bot 能推送日报 |
| **Phase 5** | PostgreSQL + Qdrant + Docker + 测试覆盖 > 80% | `docker-compose up` 一键启动 |
