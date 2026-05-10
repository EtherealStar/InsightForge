# 技术选型完整论证

> **来源**：从 [ARCHITECTURE.md](../../ARCHITECTURE.md) §2 迁出的完整技术选型对照与论证。

---

## 当前技术栈总览

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
| **向量存储** | PostgreSQL + pgvector | 子 chunk 向量与文章数据统一存储 |
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

## 选型演进对照

以下记录从 Demo 原型到当前版本的技术选型演进及决策理由。

### 元数据存储：SQLite → PostgreSQL

| 维度 | SQLite | PostgreSQL |
|---|---|---|
| 并发写入 | 单写者锁，多进程冲突 | 多连接并发 MVCC |
| 全文搜索 | FTS5 (需手动维护) | tsvector + GIN 原生支持 |
| JSON 支持 | json_extract (有限) | JSONB 原生类型 + 索引 |
| 云托管 | 不适合 | 多种托管选项 |
| 运维复杂度 | 零 | 需要 Docker 容器 |

**决策**：项目引入 Celery 多进程后，SQLite 的单写者锁成为瓶颈。PostgreSQL 的 `INSERT ... ON CONFLICT DO NOTHING` 提供了更安全的并发去重，`JSONB` 原生支持标签存储。通过 Docker Compose 管理，运维成本可控。

### 向量数据库：ChromaDB → Qdrant → pgvector

| 维度 | ChromaDB | Qdrant | pgvector |
|---|---|---|
| 部署模式 | 本地持久化 | Docker / Cloud 托管 | 随 PostgreSQL 部署 |
| 数据一致性 | 独立文件 | 独立服务 | 与文章/chunk 同库事务边界 |
| Payload 过滤 | metadata 过滤（有限） | 强大的 payload 过滤 + 索引 | SQL 条件过滤 |
| 运维风险 | 低 | 需要额外服务 | 少一个基础设施组件 |

**决策**：Qdrant 曾用于独立向量检索，但当前项目优先降低本地部署和数据一致性风险。子 chunk embedding 合并进 PostgreSQL `child_chunks` 表，由 pgvector 提供 cosine 检索，关键词检索继续使用 PostgreSQL FTS。

### 任务调度：APScheduler → Celery + Redis

| 维度 | APScheduler | Celery + Redis |
|---|---|---|
| 执行模式 | 单进程内调度 | 分布式，多 Worker 并行 |
| 任务重试 | 需手动实现 | 内置 `max_retries` + `default_retry_delay` |
| 监控 | 无 | Flower 监控面板 |
| 异步返回 | 不支持 | `task_id` + 状态轮询 |

**决策**：Pipeline 和日报生成是耗时任务（分钟级），在 APScheduler 中会阻塞主进程。Celery 允许 Worker 异步执行，API 立即返回 `task_id`，前端通过轮询获取结果。Redis 作为轻量 Broker，Docker Compose 中一行配置即可启动。

### 日志：logging → structlog

| 维度 | logging 标准库 | structlog |
|---|---|---|
| 输出格式 | 纯文本，难以解析 | JSON 结构化，可机器读取 |
| 上下文追踪 | 需手动传递 | `bind()` 自动注入 request_id 等 |
| 第三方集成 | 各库自行配置 | 统一拦截所有 logger |

**决策**：系统引入 Celery 多进程后，纯文本日志无法有效关联请求链路。structlog 的 `bind(request_id=...)` + JSON 输出使得日志可查询、可聚合。

### 检索策略：纯向量 → RRF 混合检索

| 维度 | 纯向量语义检索 | 混合检索 (向量 + 关键词 + RRF) |
|---|---|---|
| 精确匹配 | 弱（语义近似可能漏掉精确关键词） | 强（关键词通道覆盖） |
| 语义理解 | 强 | 强（向量通道保留） |
| 中文支持 | 依赖 Embedding 模型 | jieba 分词 + tsvector 补充 |
| 鲁棒性 | 单通道，无降级 | 双通道，任一故障可降级 |

**决策**：纯向量检索对专有名词（如 "FSD"、"GPT-4o"）召回不稳定。引入 PostgreSQL 全文搜索通道 + RRF 融合，在保持语义检索优势的同时补充精确匹配能力。jieba 分词解决中文 tsvector 的分词问题。

### 分块策略：整篇文章 → 父子分块

| 维度 | 整篇文章 Embedding | 父子分块 (Parent-Child) |
|---|---|---|
| 检索粒度 | 粗（整篇文章） | 细（子 chunk ≤512 token） |
| LLM 上下文 | 可能过长或不相关 | 父 chunk ~1024 token，精准相关 |
| 存储效率 | 每篇一个向量 | 子 chunk 向量 + 父 chunk 文本（零冗余） |

**决策**：整篇文章的 Embedding 在长文档上效果差，检索返回整篇文章浪费 LLM context window。父子分块将检索（子 chunk 精准匹配）和召回（父 chunk 提供上下文）解耦，显著提升 RAG 效果。

---

## 架构决策记录 (ADR)

### ADR-001: Protocol 接口保持不变

**决策**：升级过程中所有 Protocol 接口签名不变。
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

### ADR-005: 手动 ReAct Prompt 而非 Function Calling

**决策**：采用手动 prompt 构建 + 输出解析实现 ReAct，而非 OpenAI function calling API。
**理由**：项目支持 4 种 LLM 后端，统一的 ReAct prompt 方式兼容性最好，且 Thought/Observation 过程可透明展示给用户。
**影响**：需维护自定义解析器 (`ReActParser`)，但获得了跨模型兼容性。
