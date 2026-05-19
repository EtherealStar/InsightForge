# 技术选型完整论证

> 来源：从 [ARCHITECTURE.md](../../ARCHITECTURE.md) §2 迁出的技术选型对照与 ADR。

---

## 当前技术栈总览

| 模块 | 当前选型 | 说明 |
|---|---|---|
| 语言 | Python 3.11+ | 后端全栈 |
| 前端框架 | Vue 3 + Vue Router 4 + Vite 6 | SPA 单页应用 |
| Web 框架 | FastAPI + Uvicorn | REST API + SSE |
| 元数据与权威内容 | PostgreSQL 16 | 文档、父块、全文索引、point 状态、任务历史、竞品和报告 |
| 向量索引 | Qdrant | 子块向量、子块正文 payload、metadata 过滤 |
| 分块 | tiktoken + ChunkingService | Markdown-aware 父子分块 |
| 中文分词 | jieba | 应用层分词，供 PostgreSQL FTS 使用 |
| 混合检索 | HybridSearchService + RRF | Qdrant 子块语义检索 + PostgreSQL 父块关键词检索 |
| LLM 调用 | openai / google-genai / anthropic SDK | OpenAI Compatible、OpenAI、Gemini、Claude |
| 结构化抽取 | openai / google-genai / anthropic SDK | 独立 provider/model/key 配置，专职 JSON object 抽取 |
| Embedding | openai SDK，自定义端点 | OpenAI 格式兼容 API |
| Rerank | Jina/SiliconFlow 兼容 API | 可选 Cross-Encoder 重排序 |
| Web 搜索 | duckduckgo-search + tavily-python | DuckDuckGo + Tavily |
| NewsAPI | requests 代理 | newsapi.org API 代理 |
| 任务调度 | Celery + Redis | Beat 定时触发 + Worker 异步执行 |
| 配置管理 | pydantic-settings + `.env` | 类型校验 + 环境变量加载 |
| 测试 | pytest | 单元测试 + 集成测试 |

---

## 选型演进

### 元数据存储：SQLite -> PostgreSQL

PostgreSQL 取代 SQLite 的主要原因是并发写入、`JSONB`、`INSERT ... ON CONFLICT`、`tsvector + GIN` 和生产部署可维护性。当前 PostgreSQL 是权威业务层，不承担向量相似度索引。

### 向量索引：PostgreSQL 向量路径 -> Qdrant

| 维度 | PostgreSQL vector 列 | Qdrant |
|---|---|---|
| 角色边界 | 关系数据和向量索引混在同库 | 专职向量索引 |
| payload 过滤 | SQL 可做，但与向量表耦合 | 原生 payload filter |
| 重建索引 | 依赖数据库表和扩展 | collection 可重建 |
| 扩展性 | 随 PostgreSQL 压力增长 | 可独立扩缩容 |
| 当前决策 | 删除旧路径 | 作为唯一向量后端 |

**决策**：Phase 1 全量重构后，Qdrant 保存子 chunk embedding、子块正文和检索 metadata；PostgreSQL 保存 `source_documents`、`document_parent_chunks` 和 `document_vector_points`，不创建 vector extension，不保存 embedding 列。

### 检索策略：纯向量 -> 父子分块混合检索

| 维度 | 纯向量 | Qdrant + PostgreSQL RRF |
|---|---|---|
| 精确关键词 | 弱 | PostgreSQL FTS 补齐 |
| 语义召回 | 强 | Qdrant 子块保留 |
| LLM 上下文 | 易返回整篇长文 | 通过 `parent_chunk_id` 召回父块 |
| 降级 | 单通道失败即失败 | 语义/关键词可互相降级 |

**决策**：子块用于 Qdrant 语义检索，父块用于 LLM 上下文和 PostgreSQL 全文搜索。RRF 负责融合语义通道和关键词通道。

### 分块策略：整篇文章 -> 父子分块

父子分块将检索粒度和上下文粒度解耦：

- 子块 `<=512` tokens，存入 Qdrant point payload 并向量化。
- 父块约 `1024` tokens，保存到 PostgreSQL `document_parent_chunks`。
- 父块由连续子块组成，父块之间通过共享尾部子块 overlap。
- 共享子块仍只有一个主 `parent_chunk_id`，父块 `child_point_ids` 记录 overlap。

### 任务调度：APScheduler -> Celery + Redis

Pipeline、报告生成和清理任务是分钟级异步任务。Celery 允许 API 立即返回 `task_id`，Worker 负责耗时执行，Redis 作为 broker/result backend。

### 日志：logging -> structlog

结构化 JSON 日志便于跨 FastAPI、Celery 和外部调用追踪请求链路。

### 结构化事实层：业务事实表而非第二套 RAG

Phase 2 新增 `intel_facts`、`evidence_refs` 和 `insight_claims`，用于稳定过滤、聚合、事实归因和 claim 溯源。父子分块 RAG 仍负责原文证据召回和开放式检索，`IntelFact` 不向量化为第二套语义检索主路径。

结构化抽取使用独立 `StructuredExtractionClientProtocol` 和 `structured_extraction_*` 配置。用户如需复用主 LLM，必须显式配置为同一 provider/model/key；系统不做隐式 fallback。

---

## ADR

### ADR-001：Protocol 优先

新增基础设施先定义 `Protocol`，实现层不得向服务层泄露 Qdrant SDK、psycopg2 游标或 Redis SDK 类型。

### ADR-002：Qdrant 是唯一向量后端

不保留旧向量 Store 协议、旧 PostgreSQL 向量实现、旧向量工厂函数或 PostgreSQL embedding 列兼容路径。后续若新增向量集合，应扩展 `VectorIndexProtocol` 或新增专门协议，而不是恢复旧 PostgreSQL 向量表。

### ADR-003：PostgreSQL 只保存父块和 point 状态

PostgreSQL 不新增子块正文表。子块正文进入 Qdrant payload，PostgreSQL 通过 `document_vector_points` 追踪 point 状态，通过 `document_parent_chunks` 保存完整父块上下文和 FTS。

### ADR-004：工厂函数而非 DI 容器

继续使用 `core/factory.py` 和 `ConfigManager`，当前项目规模下工厂函数足够明确。`ConfigManager` 暴露 `document_store` 与 `vector_index`，不暴露旧向量 Store 属性。

### ADR-005：手动 ReAct Prompt 而非 Function Calling

项目支持多个 LLM 后端，统一 ReAct prompt + parser 的方式兼容性更好，且 Thought/Observation 过程可透明展示给用户。

### ADR-006：结构化抽取客户端独立于主 LLM

事实抽取是高频、批处理、格式约束强的任务，成本和延迟目标不同于 Agent 问答、报告撰写和后续质量审查。`StructuredExtractionClientProtocol` 因此独立于 `LLMClientProtocol`，并只接受 JSON object 输出；解析失败抛出结构化抽取异常，不创建半结构化事实。
