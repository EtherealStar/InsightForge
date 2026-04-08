# Logos 个人新闻分析助手 — Demo 原型方案

> 本文档定义 Demo 原型的完整技术规格，包含分层架构、统一数据模型、接口协议和各模块实现要求。  
> 与 `full_design.md` 共享相同接口契约（Protocol），升级时只替换内部实现。

---

## 1. 产品定位

一个运行在本地的**个人 AI 新闻分析助手**，具备两种核心能力：

1. **定时 Pipeline**：自动从多个新闻来源抓取内容，清洗、向量化后存储，每天早晨生成一份日报或根据用户需求即使生成日报。
2. **交互查询**：用户可以用自然语言提问，系统通过 RAG（检索增强生成）从历史新闻库中检索相关内容，调用 AI API 给出分析回答。

### 核心约束

- 语言：Python 3.11+
- AI 模型：**OpenAI 格式自定义 API 接口** + **GPT / Gemini / Claude 官方 SDK** 多后端支持
- Embedding 模型：**OpenAI 格式自定义 API**
- 所有模块通过 Protocol 定义接口契约，Demo 和完整方案共享相同 Protocol，只替换内部实现
- Scheduler 与 Streamlit **独立进程**运行，不使用 threading 耦合

---

## 2. 技术选型

| 模块 | 选型 | 理由 |
|---|---|---|
| 新闻抓取 | `feedparser` + `requests` + `trafilatura` | feedparser 解析 RSS；trafilatura 替代 newspaper3k（活跃维护、多语言友好） |
| 存储 | `sqlite3`（标准库） | 单文件数据库，无需安装任何服务 |
| 向量库 | `chromadb`（本地持久化模式） | pip 安装即用，数据存为本地文件夹 |
| 调度 | `APScheduler`（独立进程） | 轻量定时任务，作为独立脚本运行 |
| 界面 | `streamlit` | 纯 Python 写 UI，`streamlit run` 即启动 |
| AI 分析 | `openai` SDK（兼容自定义端点） | 统一接口格式，支持 GPT / Gemini / Claude 官方 + 自定义 API |
| Embedding | `openai` SDK（自定义端点） | OpenAI 格式自定义 API |
| 数据模型 | `dataclass` | 模块间传递类型安全的数据对象，取代 dict |
| 配置管理 | `pydantic-settings` | 类型校验 + .env 加载 + 友好报错 |

---

## 3. 分层架构

```
┌──────────────────────────────────────────────────────┐
│                   表现层 (Delivery)                    │
│   streamlit_app.py  │  cli.py                        │
├──────────────────────────────────────────────────────┤
│                  应用服务层 (Services)                  │
│   pipeline_service  │  query_service  │  brief_service│
├──────────────────────────────────────────────────────┤
│                  领域模型层 (Models)                    │
│   Article  │  DailyBrief  │  SearchResult             │
├──────────────────────────────────────────────────────┤
│               基础设施层 (Infrastructure)               │
│   collector  │  article_store  │  vector_store        │
│   llm_client │  embedding_client                      │
├──────────────────────────────────────────────────────┤
│                  横切关注点 (Core)                      │
│   config  │  exceptions  │  logging  │  retry         │
│   protocols（接口契约）                                │
└──────────────────────────────────────────────────────┘
```

**层间规则**：
- 上层可以依赖下层，下层不得依赖上层
- `services/` 编排 `infrastructure/` 中的组件，不直接操作数据库或 API
- `infrastructure/` 实现 `core/protocols.py` 中定义的 Protocol 接口
- `models/` 是纯数据定义，无任何 I/O 依赖

---

## 4. 目录结构

```
news_assistant/
├── models/                        # 领域模型层
│   ├── __init__.py
│   ├── article.py                 # Article dataclass
│   ├── brief.py                   # DailyBrief 模型
│   └── search.py                  # SearchResult、SearchQuery 模型
│
├── core/                          # 横切关注点
│   ├── __init__.py
│   ├── config.py                  # Pydantic Settings 配置
│   ├── protocols.py               # Protocol 接口契约定义
│   ├── factory.py                 # 工厂函数（按配置创建组件实例）
│   ├── exceptions.py              # 异常层次定义
│   ├── logging.py                 # 统一日志配置
│   └── retry.py                   # 重试 / 降级装饰器
│
├── infrastructure/                # 基础设施层（可替换实现）
│   ├── __init__.py
│   ├── collector.py               # 新闻抓取（feedparser + trafilatura）
│   ├── article_store.py           # SQLite 文章存储
│   ├── vector_store.py            # ChromaDB 向量存储
│   ├── llm_client.py              # LLM 调用（多后端）
│   └── embedding_client.py        # Embedding 调用（自定义 API）
│
├── services/                      # 应用服务层
│   ├── __init__.py
│   ├── pipeline_service.py        # 抓取 → 存储 → 向量化 编排
│   ├── query_service.py           # 检索 → 分析 编排
│   └── brief_service.py           # 日报生成编排
│
├── delivery/                      # 表现层
│   ├── __init__.py
│   ├── streamlit_app.py           # Streamlit UI（独立进程）
│   └── cli.py                     # CLI 入口，方便调试
│
├── scheduler/                     # 调度层（独立进程）
│   ├── __init__.py
│   └── scheduler.py               # APScheduler 定时任务
│
├── tests/                         # 测试
│   ├── __init__.py
│   ├── conftest.py                # 共享 fixtures
│   ├── test_collector.py
│   ├── test_article_store.py
│   ├── test_vector_store.py
│   ├── test_pipeline_service.py
│   └── test_query_service.py
│
├── data/                          # 运行时数据（.gitignore）
│   ├── news.db                    # SQLite（自动创建）
│   └── chroma/                    # ChromaDB 向量文件（自动创建）
├── output/                        # 日报输出
│   └── daily_brief_YYYY-MM-DD.md
├── .env.example                   # 环境变量模板
├── requirements.txt
├── pyproject.toml                 # 项目元数据
└── README.md
```

---

## 5. requirements.txt

```
# AI
openai>=1.30.0
google-genai>=1.0.0
anthropic>=0.25.0

# 新闻抓取
feedparser>=6.0.0
trafilatura>=1.8.0
requests>=2.31.0

# 存储
chromadb>=0.5.0

# 调度
APScheduler>=3.10.0

# 界面
streamlit>=1.35.0

# 配置与工具
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0

# 测试
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

---

## 6. 环境变量（.env.example）

```bash
# ===== LLM 配置 =====
# 默认使用 OpenAI 格式自定义 API
LLM_PROVIDER=openai_compatible
LLM_API_KEY=your_key_here
LLM_BASE_URL=https://your-custom-endpoint.com/v1
LLM_MODEL=your-model-name

# GPT 官方（可选，设置 LLM_PROVIDER=openai 时使用）
OPENAI_API_KEY=your_openai_key

# Gemini 官方（可选，设置 LLM_PROVIDER=gemini 时使用）
GOOGLE_API_KEY=your_google_key

# Claude 官方（可选，设置 LLM_PROVIDER=anthropic 时使用）
ANTHROPIC_API_KEY=your_anthropic_key

# ===== Embedding 配置 =====
EMBEDDING_API_KEY=your_embedding_key
EMBEDDING_BASE_URL=https://your-embedding-endpoint.com/v1
EMBEDDING_MODEL=your-embedding-model

# ===== 其他 =====
LOG_LEVEL=INFO
ARTICLE_RETENTION_DAYS=90
```

---

## 7. 领域模型（models/）

### models/article.py

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class Language(str, Enum):
    EN = "en"
    ZH = "zh"
    UNKNOWN = "unknown"

class ArticleStatus(str, Enum):
    RAW = "raw"
    STORED = "stored"
    EMBEDDED = "embedded"

@dataclass
class Article:
    """领域核心实体：一篇新闻文章"""
    title: str
    url: str
    content: str = ""
    summary: str = ""
    source: str = ""
    language: Language = Language.UNKNOWN
    published_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)

    # 数据库相关
    id: int | None = None
    url_hash: str = ""
    status: ArticleStatus = ArticleStatus.RAW

    def to_embedding_text(self, max_chars: int = 2000) -> str:
        """生成用于 Embedding 的文本（2000 字符 ≈ 500-700 中文 tokens）"""
        text = f"{self.title}\n{self.content}"
        return text[:max_chars]

    def to_context_str(self) -> str:
        """生成用于 LLM context 的格式化文本"""
        date_str = self.published_at.strftime("%Y-%m-%d") if self.published_at else "未知"
        return (f"[{self.source} | {date_str}] {self.title}\n"
                f"{self.summary or self.content[:300]}\n"
                f"{self.url}")
```

### models/search.py

```python
from dataclasses import dataclass
from datetime import datetime
from models.article import Article, Language

@dataclass
class SearchQuery:
    """封装一次搜索请求"""
    text: str
    top_k: int = 10
    sources: list[str] | None = None
    language: Language | None = None
    date_from: datetime | None = None

@dataclass
class SearchResult:
    """封装一条搜索结果"""
    article: Article
    relevance_score: float = 0.0
    match_type: str = "semantic"   # "semantic" | "keyword" | "hybrid"
```

### models/brief.py

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class DailyBrief:
    """日报模型"""
    date: datetime
    content_markdown: str
    article_count: int = 0
    generated_at: datetime = field(default_factory=datetime.now)

    def save_to_file(self, output_dir: str) -> str:
        """保存为 Markdown 文件，返回文件路径"""
        import os
        os.makedirs(output_dir, exist_ok=True)
        filename = f"daily_brief_{self.date.strftime('%Y-%m-%d')}.md"
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.content_markdown)
        return path
```

---

## 8. 横切关注点（core/）

### core/config.py

```python
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import Literal

class RSSSource(BaseSettings):
    name: str
    url: str

class AppConfig(BaseSettings):
    """应用配置，从 .env 加载并做类型校验"""

    # --- LLM 配置 ---
    llm_provider: Literal["openai_compatible", "openai", "gemini", "anthropic"] = "openai_compatible"
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
    store_backend: Literal["sqlite", "postgresql"] = "sqlite"
    vector_backend: Literal["chroma", "qdrant"] = "chroma"
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
    rss_feeds: list[dict] = Field(default=[
        {"name": "Reuters", "url": "https://www.reutersagency.com/en/reuters-best/rss/"},
        {"name": "BBC News", "url": "https://feeds.bbci.co.uk/news/rss.xml"},
        {"name": "联合早报", "url": "https://www.zaobao.com.sg/rss/realtime/china"},
    ])

    @field_validator("llm_api_key", "embedding_api_key")
    @classmethod
    def warn_empty_key(cls, v, info):
        if not v:
            import logging
            logging.warning(f"⚠ {info.field_name} is empty — related features will be disabled")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

### core/protocols.py

```python
"""接口契约：Demo 和 Full 都实现这些 Protocol"""
from typing import Protocol, Iterator, runtime_checkable
from models.article import Article
from models.search import SearchResult

@runtime_checkable
class ArticleStoreProtocol(Protocol):
    """文章元数据存储（SQLite / PostgreSQL）"""
    def save_articles(self, articles: list[Article]) -> int: ...
    def get_unembedded(self, limit: int = 100) -> list[Article]: ...
    def mark_embedded(self, article_ids: list[int]) -> None: ...
    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Article]: ...
    def get_recent(self, hours: int = 24, limit: int = 50) -> list[Article]: ...
    def get_stats(self) -> dict: ...
    def cleanup_old_articles(self, retention_days: int = 90) -> int: ...

@runtime_checkable
class VectorStoreProtocol(Protocol):
    """向量存储（ChromaDB / Qdrant）"""
    def add_articles(self, articles: list[Article], embeddings: list[list[float]]) -> int: ...
    def search(self, query_embedding: list[float], top_k: int = 10,
               filters: dict | None = None) -> list[SearchResult]: ...

@runtime_checkable
class LLMClientProtocol(Protocol):
    """LLM 调用（OpenAI 兼容 / GPT / Gemini / Claude）"""
    def generate(self, system_prompt: str, user_message: str) -> str: ...
    def generate_stream(self, system_prompt: str, user_message: str) -> Iterator[str]: ...

@runtime_checkable
class EmbeddingClientProtocol(Protocol):
    """Embedding 调用（OpenAI 格式自定义 API）"""
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

### core/factory.py

```python
"""根据配置创建具体实现实例"""
from core.config import AppConfig
from core.protocols import (
    ArticleStoreProtocol, VectorStoreProtocol,
    LLMClientProtocol, EmbeddingClientProtocol
)

def create_article_store(config: AppConfig) -> ArticleStoreProtocol:
    if config.store_backend == "sqlite":
        from infrastructure.article_store import SQLiteArticleStore
        return SQLiteArticleStore(config.db_path)
    elif config.store_backend == "postgresql":
        from infrastructure.article_store import PostgreSQLArticleStore
        return PostgreSQLArticleStore(config.pg_dsn)
    raise ValueError(f"Unknown store backend: {config.store_backend}")

def create_vector_store(config: AppConfig) -> VectorStoreProtocol:
    if config.vector_backend == "chroma":
        from infrastructure.vector_store import ChromaVectorStore
        return ChromaVectorStore(config.chroma_path)
    elif config.vector_backend == "qdrant":
        from infrastructure.vector_store import QdrantVectorStore
        return QdrantVectorStore(config.qdrant_url, config.qdrant_api_key)
    raise ValueError(f"Unknown vector backend: {config.vector_backend}")

def create_llm_client(config: AppConfig) -> LLMClientProtocol:
    from infrastructure.llm_client import (
        OpenAICompatibleClient, OpenAIClient,
        GeminiClient, AnthropicClient
    )
    match config.llm_provider:
        case "openai_compatible":
            return OpenAICompatibleClient(
                api_key=config.llm_api_key,
                base_url=config.llm_base_url,
                model=config.llm_model
            )
        case "openai":
            return OpenAIClient(
                api_key=config.openai_api_key,
                model=config.llm_model or "gpt-4o-mini"
            )
        case "gemini":
            return GeminiClient(
                api_key=config.google_api_key,
                model=config.llm_model or "gemini-2.0-flash"
            )
        case "anthropic":
            return AnthropicClient(
                api_key=config.anthropic_api_key,
                model=config.llm_model or "claude-sonnet-4-20250514"
            )
    raise ValueError(f"Unknown LLM provider: {config.llm_provider}")

def create_embedding_client(config: AppConfig) -> EmbeddingClientProtocol:
    from infrastructure.embedding_client import OpenAICompatibleEmbeddingClient
    return OpenAICompatibleEmbeddingClient(
        api_key=config.embedding_api_key,
        base_url=config.embedding_base_url,
        model=config.embedding_model
    )
```

### core/exceptions.py

```python
"""统一异常层次"""

class NewsAssistantError(Exception):
    """基础异常"""

class CollectorError(NewsAssistantError):
    """抓取相关错误"""

class SourceUnavailableError(CollectorError):
    def __init__(self, source: str, reason: str):
        self.source = source
        super().__init__(f"Source '{source}' unavailable: {reason}")

class StoreError(NewsAssistantError):
    """存储相关错误"""

class EmbeddingError(NewsAssistantError):
    """向量化相关错误"""

class LLMError(NewsAssistantError):
    """LLM 调用错误"""

class RateLimitError(LLMError):
    def __init__(self, retry_after: float = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after}s")

class ConfigError(NewsAssistantError):
    """配置错误"""
```

### core/retry.py

```python
"""重试与降级工具"""
import functools, time, logging

logger = logging.getLogger(__name__)

def with_retry(max_retries: int = 3, backoff_base: float = 2.0,
               exceptions: tuple = (Exception,)):
    """指数退避重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        raise
                    wait = backoff_base ** attempt
                    logger.warning(
                        f"Retry {attempt+1}/{max_retries} for {func.__name__}: {e}, "
                        f"wait {wait:.1f}s"
                    )
                    time.sleep(wait)
        return wrapper
    return decorator
```

### core/logging.py

```python
"""统一日志配置"""
import logging, sys

def setup_logging(level: str = "INFO", log_file: str | None = None):
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(level=level, format=fmt, handlers=handlers)
    # 降低第三方库噪音
    for lib in ("httpx", "chromadb", "httpcore", "urllib3"):
        logging.getLogger(lib).setLevel(logging.WARNING)
```

---

## 9. 基础设施层（infrastructure/）

### infrastructure/collector.py

**职责**：从 RSS 和网页抓取原始新闻，返回 `Article` 列表。

```python
import feedparser
import trafilatura
from models.article import Article, Language
from core.config import AppConfig
from core.exceptions import CollectorError, SourceUnavailableError
from core.retry import with_retry

class NewsCollector:
    def __init__(self, config: AppConfig):
        self.config = config

    def fetch_all(self) -> list[Article]:
        """
        从所有 RSS 源抓取文章。
        - 每个源独立 try/except，单源失败不影响整体
        - 每源最多返回 config.max_articles_per_fetch 条
        """
        pass

    def fetch_source(self, name: str, url: str) -> list[Article]:
        """抓取单个 RSS 源，供调试用"""
        pass

    @with_retry(max_retries=2, exceptions=(Exception,))
    def _extract_full_text(self, url: str) -> str | None:
        """
        用 trafilatura 提取正文全文。
        trafilatura.fetch_url() + trafilatura.extract()
        失败返回 None，由调用方回退到 RSS summary。
        """
        pass
```

**实现要求**：
- 用 `feedparser.parse(url)` 解析 RSS
- 对每条 entry，用 `trafilatura.fetch_url(url)` 下载页面，再用 `trafilatura.extract(downloaded)` 提取正文
- 提取失败时回退到 `entry.summary`
- `published_at` 优先用 `entry.published_parsed`，转为 `datetime` 对象；缺失则用 `datetime.now()`
- 返回 `Article` 对象列表（而非 dict）
- 所有网络请求加入重试和异常处理

---

### infrastructure/article_store.py

**职责**：SQLite 文章元数据存储，实现 `ArticleStoreProtocol`。

**数据库表结构**：

```sql
CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash     TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    content      TEXT,
    summary      TEXT,
    source       TEXT,
    language     TEXT,
    published_at TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    status       TEXT DEFAULT 'stored'    -- raw / stored / embedded
);

CREATE INDEX IF NOT EXISTS idx_status ON articles(status);
CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at);
CREATE INDEX IF NOT EXISTS idx_source ON articles(source);
```

```python
import sqlite3, hashlib
from models.article import Article
from core.protocols import ArticleStoreProtocol

class SQLiteArticleStore:
    """实现 ArticleStoreProtocol"""

    def __init__(self, db_path: str):
        """初始化时自动创建数据库和表"""
        pass

    def save_articles(self, articles: list[Article]) -> int:
        """
        去重后写入数据库。
        去重：SHA256(url) → url_hash，存在则跳过。
        返回实际新增数量。
        必须使用参数化查询（? 占位符），防止 SQL 注入。
        """
        pass

    def get_unembedded(self, limit: int = 100) -> list[Article]:
        """返回 status != 'embedded' 的文章"""
        pass

    def mark_embedded(self, article_ids: list[int]) -> None:
        """将指定 id 的文章 status 设为 'embedded'"""
        pass

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Article]:
        """LIKE 关键词搜索 title + content"""
        pass

    def get_recent(self, hours: int = 24, limit: int = 50) -> list[Article]:
        """返回最近 N 小时内的文章"""
        pass

    def get_stats(self) -> dict:
        """
        返回统计信息：
        {"total": int, "embedded": int, "today_new": int,
         "oldest_date": str, "sources": list[str]}
        """
        pass

    def cleanup_old_articles(self, retention_days: int = 90) -> int:
        """删除超过 retention_days 天的文章，返回删除数量"""
        pass
```

---

### infrastructure/vector_store.py

**职责**：ChromaDB 向量存储，实现 `VectorStoreProtocol`。

```python
import chromadb
from models.article import Article
from models.search import SearchResult
from core.protocols import VectorStoreProtocol

class ChromaVectorStore:
    """实现 VectorStoreProtocol"""

    def __init__(self, chroma_path: str):
        """
        初始化 PersistentClient。
        获取或创建名为 "news_articles" 的 collection。
        """
        pass

    def add_articles(self, articles: list[Article],
                     embeddings: list[list[float]]) -> int:
        """
        将文章和对应向量写入 ChromaDB。
        - document = article.to_embedding_text()
        - metadata: {id, title, url, source, published_at, language}
        - ids: "article_{id}"
        - 批量大小 50 条
        返回成功写入的数量。
        """
        pass

    def search(self, query_embedding: list[float], top_k: int = 10,
               filters: dict | None = None) -> list[SearchResult]:
        """
        向量相似度检索。
        filters 示例：{"source": "BBC News"}
        返回 SearchResult 列表（包含 article 和 relevance_score）。
        """
        pass
```

---

### infrastructure/llm_client.py

**职责**：封装多 LLM 后端调用，统一实现 `LLMClientProtocol`。

```python
from typing import Iterator
from core.protocols import LLMClientProtocol
from core.retry import with_retry
from core.exceptions import LLMError, RateLimitError

class OpenAICompatibleClient:
    """OpenAI 格式自定义 API（默认后端）"""

    def __init__(self, api_key: str, base_url: str, model: str):
        """使用 openai SDK，设置 base_url 指向自定义端点"""
        # self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        pass

    @with_retry(max_retries=2)
    def generate(self, system_prompt: str, user_message: str) -> str:
        """调用 chat.completions.create()"""
        pass

    def generate_stream(self, system_prompt: str, user_message: str) -> Iterator[str]:
        """调用 chat.completions.create(stream=True)，yield 每个 text chunk"""
        pass


class OpenAIClient:
    """GPT 官方 API"""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        pass

    @with_retry(max_retries=2)
    def generate(self, system_prompt: str, user_message: str) -> str:
        pass

    def generate_stream(self, system_prompt: str, user_message: str) -> Iterator[str]:
        pass


class GeminiClient:
    """Google Gemini 官方 API"""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        """使用 google-genai SDK"""
        pass

    @with_retry(max_retries=2)
    def generate(self, system_prompt: str, user_message: str) -> str:
        """
        使用 genai.Client.models.generate_content()
        system_instruction 传入 system_prompt
        """
        pass

    def generate_stream(self, system_prompt: str, user_message: str) -> Iterator[str]:
        """使用 generate_content(stream=True)"""
        pass


class AnthropicClient:
    """Claude 官方 API"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        """使用 anthropic SDK"""
        pass

    @with_retry(max_retries=2)
    def generate(self, system_prompt: str, user_message: str) -> str:
        """
        使用 messages.create()
        system 参数传入 system_prompt
        """
        pass

    def generate_stream(self, system_prompt: str, user_message: str) -> Iterator[str]:
        """使用 messages.stream()"""
        pass
```

---

### infrastructure/embedding_client.py

**职责**：Embedding 向量生成，使用 OpenAI 格式自定义 API。

```python
from core.protocols import EmbeddingClientProtocol
from core.retry import with_retry

class OpenAICompatibleEmbeddingClient:
    """实现 EmbeddingClientProtocol，调用 OpenAI 格式自定义 Embedding API"""

    def __init__(self, api_key: str, base_url: str, model: str):
        """
        使用 openai SDK，设置 base_url 指向自定义 Embedding 端点。
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        """
        pass

    @with_retry(max_retries=2)
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量生成向量。
        调用 self.client.embeddings.create(model=self.model, input=texts)
        批量大小：每次最多 50 条文本。
        对超出的部分自动分批处理。
        返回与 texts 顺序对应的向量列表。
        """
        pass
```

---

## 10. 应用服务层（services/）

### services/pipeline_service.py

```python
import logging
from core.protocols import (
    ArticleStoreProtocol, VectorStoreProtocol, EmbeddingClientProtocol
)
from infrastructure.collector import NewsCollector

logger = logging.getLogger(__name__)

class PipelineService:
    """编排 抓取 → 存储 → 向量化 的完整流水线"""

    def __init__(self, collector: NewsCollector,
                 article_store: ArticleStoreProtocol,
                 vector_store: VectorStoreProtocol,
                 embedding_client: EmbeddingClientProtocol):
        self.collector = collector
        self.article_store = article_store
        self.vector_store = vector_store
        self.embedding_client = embedding_client

    def run(self) -> dict:
        """
        执行完整 Pipeline：
        1. collector.fetch_all() → articles
        2. article_store.save_articles(articles) → new_count
        3. pending = article_store.get_unembedded()
        4. embeddings = embedding_client.embed([a.to_embedding_text() for a in pending])
        5. vector_store.add_articles(pending, embeddings) → embedded_count
        6. article_store.mark_embedded([a.id for a in pending])

        每步独立 try/except，失败记日志但不终止后续步骤。
        返回 {"fetched": int, "new": int, "embedded": int, "errors": list[str]}
        """
        pass
```

### services/query_service.py

```python
import logging
from typing import Iterator
from core.protocols import (
    ArticleStoreProtocol, VectorStoreProtocol,
    LLMClientProtocol, EmbeddingClientProtocol
)
from models.article import Article
from models.search import SearchQuery, SearchResult

logger = logging.getLogger(__name__)

# Prompt 模板
QA_SYSTEM_PROMPT = """你是一位专业的新闻分析师。请基于以下提供的新闻文章内容回答用户的问题。

规则：
1. 只基于提供的文章内容回答，不要编造信息
2. 如果文章中没有相关信息，请如实说明
3. 回答要客观、简洁、有洞察力
4. 回答末尾列出参考来源（标题 + URL）"""

class QueryService:
    """编排 检索 → 分析 的查询流程"""

    def __init__(self, article_store: ArticleStoreProtocol,
                 vector_store: VectorStoreProtocol,
                 llm_client: LLMClientProtocol,
                 embedding_client: EmbeddingClientProtocol):
        self.article_store = article_store
        self.vector_store = vector_store
        self.llm_client = llm_client
        self.embedding_client = embedding_client

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """
        混合检索：
        1. 语义检索：query.text → Embedding → vector_store.search(top_k * 2)
        2. 关键词检索：article_store.search_by_keyword(query.text, top_k)
        3. 合并去重（以 url 为 key），语义结果优先
        4. 返回前 top_k 条

        Demo 阶段简化：只用语义检索。
        """
        pass

    def answer(self, question: str, top_k: int = 10) -> str:
        """
        完整 RAG 流程：检索 + LLM 生成回答
        1. search(SearchQuery(text=question, top_k=top_k))
        2. 将结果文章格式化为 context（article.to_context_str()）
        3. llm_client.generate(QA_SYSTEM_PROMPT, context + question)
        """
        pass

    def answer_stream(self, question: str, top_k: int = 10) -> Iterator[str]:
        """同 answer，但使用 streaming"""
        pass
```

### services/brief_service.py

```python
import logging
from core.protocols import ArticleStoreProtocol, LLMClientProtocol
from models.brief import DailyBrief
from datetime import datetime

logger = logging.getLogger(__name__)

BRIEF_SYSTEM_PROMPT = """你是一位资深新闻编辑。请根据以下新闻文章生成一份中文每日简报。

简报格式要求：
# 每日新闻简报 — {日期}
## 📌 今日要闻
（3-5条最重要的新闻，每条含标题、来源、一句话摘要）
## 🔍 深度分析
（选取 1-2 个值得关注的趋势或事件，200字以内的分析）
## ⚡ 快讯
（其余新闻标题列表 + 来源）

要求：客观、简洁、有洞察力。"""

class BriefService:
    """日报生成服务"""

    def __init__(self, article_store: ArticleStoreProtocol,
                 llm_client: LLMClientProtocol,
                 output_path: str):
        self.article_store = article_store
        self.llm_client = llm_client
        self.output_path = output_path

    def generate(self, hours: int = 24) -> DailyBrief:
        """
        1. article_store.get_recent(hours) → articles
        2. 格式化文章为 context：[article.to_context_str() for each]
        3. 控制 context 总长度不超过 80000 tokens（约 50 篇）
        4. llm_client.generate(BRIEF_SYSTEM_PROMPT, context)
        5. 构造 DailyBrief 对象并保存文件
        """
        pass
```

---

## 11. 调度层（scheduler/  —  独立进程）

```python
# scheduler/scheduler.py
"""
独立进程运行的定时调度器。
启动方式：python -m scheduler.scheduler
不与 Streamlit 进程耦合。
"""
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from core.config import AppConfig
from core.logging import setup_logging
from core.factory import (
    create_article_store, create_vector_store,
    create_llm_client, create_embedding_client
)
from infrastructure.collector import NewsCollector
from services.pipeline_service import PipelineService
from services.brief_service import BriefService

logger = logging.getLogger(__name__)

def run_pipeline(pipeline_service: PipelineService):
    """定时任务：执行抓取 → 存储 → 向量化"""
    logger.info("=== Pipeline 开始 ===")
    result = pipeline_service.run()
    logger.info(f"Pipeline 完成: {result}")

def run_daily_brief(brief_service: BriefService):
    """定时任务：生成日报"""
    logger.info("=== 日报生成开始 ===")
    brief = brief_service.generate(hours=24)
    logger.info(f"日报已生成：{brief.generated_at}")

def run_cleanup(article_store, retention_days: int):
    """定时任务：清理旧文章"""
    deleted = article_store.cleanup_old_articles(retention_days)
    logger.info(f"清理完成，删除 {deleted} 篇旧文章")

def main():
    config = AppConfig()
    setup_logging(config.log_level)

    # 用工厂函数创建组件
    article_store = create_article_store(config)
    vector_store = create_vector_store(config)
    llm_client = create_llm_client(config)
    embedding_client = create_embedding_client(config)
    collector = NewsCollector(config)

    pipeline_service = PipelineService(collector, article_store, vector_store, embedding_client)
    brief_service = BriefService(article_store, llm_client, config.output_path)

    # 立即执行一次 Pipeline
    run_pipeline(pipeline_service)

    # 设置定时任务
    scheduler = BlockingScheduler()
    scheduler.add_job(run_pipeline, 'interval',
                      hours=config.fetch_interval_hours,
                      args=[pipeline_service],
                      id='pipeline')
    scheduler.add_job(run_daily_brief, 'cron',
                      hour=config.daily_brief_hour,
                      args=[brief_service],
                      id='daily_brief')
    scheduler.add_job(run_cleanup, 'cron',
                      day_of_week='sun', hour=3,
                      args=[article_store, config.article_retention_days],
                      id='weekly_cleanup')

    logger.info(f"调度器启动 — Pipeline 间隔 {config.fetch_interval_hours}h，"
                f"日报时间 每天 {config.daily_brief_hour}:00")
    scheduler.start()

if __name__ == "__main__":
    main()
```

---

## 12. 表现层（delivery/）

### delivery/streamlit_app.py

```python
"""
Streamlit UI — 独立进程
启动方式：streamlit run delivery/streamlit_app.py
数据通过 SQLite 文件与 scheduler 进程共享（SQLite 支持并发读 + 单写）
"""

# Tab 1：对话查询
#   - st.chat_input() 接收用户问题
#   - query_service.answer_stream(question) → streaming 输出
#   - 在回答下方展示参考文章列表（标题 + 来源 + 链接）
#   - 保留对话历史（st.session_state）
#
# Tab 2：今日简报
#   - 读取最新的 output/daily_brief_*.md 文件
#   - st.markdown() 渲染展示
#   - 显示简报生成时间
#   - 「立即刷新」按钮 → brief_service.generate()
#
# 侧边栏（Sidebar）：
#   - 数据库统计（article_store.get_stats()）
#   - LLM Provider 状态显示
#   - 来源筛选器（multiselect）
#   - 语言筛选器
```

### delivery/cli.py

```python
"""
CLI 工具 — 方便调试各模块
用法：
    python -m delivery.cli pipeline          # 手动执行一次 Pipeline
    python -m delivery.cli brief             # 手动生成日报
    python -m delivery.cli ask "最近AI有什么进展？"  # 命令行提问
    python -m delivery.cli stats             # 查看数据库统计
    python -m delivery.cli cleanup           # 手动清理旧文章
"""
pass
```

---

## 13. 运行方式（Demo 阶段）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key 和自定义端点

# 3. 启动调度器（终端 1 — 独立进程）
python -m scheduler.scheduler

# 4. 启动 Streamlit UI（终端 2 — 独立进程）
streamlit run delivery/streamlit_app.py

# 5. 或使用 CLI 调试
python -m delivery.cli pipeline        # 手动执行 Pipeline
python -m delivery.cli ask "今天有什么重要新闻？"
python -m delivery.cli stats
```

---

## 14. 测试策略

### 测试分层

```
单元测试（infrastructure/）
├── test_collector.py          — mock feedparser + trafilatura
├── test_article_store.py      — 内存 SQLite（:memory:）
├── test_vector_store.py       — mock ChromaDB
├── test_llm_client.py         — mock API 响应
└── test_embedding_client.py   — mock Embedding 响应

集成测试（services/）
├── test_pipeline_service.py   — 真实 SQLite + mock 外部 API
└── test_query_service.py      — 预置数据 + mock LLM

E2E 测试
└── test_streamlit.py          — Streamlit AppTest 框架
```

### conftest.py 示例

```python
import pytest
from models.article import Article, Language
from datetime import datetime

@pytest.fixture
def sample_articles():
    return [
        Article(title="AI breakthrough", url="https://example.com/1",
                content="Content...", source="TestSource",
                language=Language.EN, published_at=datetime.now()),
        Article(title="测试新闻", url="https://example.com/2",
                content="内容...", source="测试来源",
                language=Language.ZH, published_at=datetime.now()),
    ]

@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "test.db")

@pytest.fixture
def mock_embedding_client():
    class FakeEmbedding:
        def embed(self, texts):
            return [[0.1] * 1536 for _ in texts]
    return FakeEmbedding()
```

---

## 15. 安全注意事项

| 风险 | 措施 |
|---|---|
| API Key 泄露 | `.env` + `.gitignore`；提供 `.env.example` |
| SQL 注入 | 参数化查询（`?` 占位符） |
| 爬虫滥用 | 遵守 `robots.txt`；合理 User-Agent；请求间隔 |
| 内容合规 | 只存摘要/正文片段，注意版权 |
