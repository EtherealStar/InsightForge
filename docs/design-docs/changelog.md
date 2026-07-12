# 架构变更历史

## 2026-07 来源级采集与版本化清洗目标设计

- 接受 [ADR-0003](../adr/0003-source-fanout-fetch-architecture.md)：直接删除 Crawlee 与旧全局 Pipeline，使用 Source Connector、异步 httpx、按来源 Playwright、PostgreSQL Collection Run 状态机和独立 Celery 队列。
- Raw Fetch Artifact body 默认保留 24 小时；形成 Document Version 或 Evidence Reference 后晋升为 Retained Fetch Artifact。
- 接受 [ADR-0004](../adr/0004-versioned-deterministic-normalization.md)：Content Block 是权威正文，Markdown 是派生表示，Normalization Outcome 只使用离散状态和原因码，不保存统一清洗分数。
- 引入来源级自适应调度/并发、Redis 降级语义、PDF/OCR、OpenTelemetry trace、Prometheus 漏斗和单机容量基线。
- 完整设计见 [collection-and-normalization.md](collection-and-normalization.md)，流程见 [pipeline-flow.md](../flows/pipeline-flow.md)。

> 来源：从 [ARCHITECTURE.md](../../ARCHITECTURE.md) 顶部“最近架构变更”迁出的完整变更记录。

---

## 2026-07 结构化情报三层模型收敛

- 接受 ADR-0002，将 Evidence Reference、Intel Fact 和 Insight Claim 固定为三个核心领域概念；内部关联表不增加领域层级。
- Intel Fact 收敛为七个粗类型和渐进式 `normalized_data`，删除 event/signal 混用、重复分类和业务 score。
- Evidence Reference 收敛为不可变原文锚点，fact-evidence stance 进入真实关系；搜索摘要和裸 URL 仅作为 Evidence Candidate。
- supported Insight Claim 必须通过 facts 间接溯源，不直接关联 evidence；fact 和 claim 激活后均采用不可变语义与显式取代关系。
- 目标设计见 [structured-intelligence-model.md](structured-intelligence-model.md)。当前代码、API 和数据库仍待按该设计迁移。

---

## 2026-05 Phase 2 Facts/Claims API 收口

- 新增 `/api/intel/facts` 和 `/api/insights/claims`，用于查询详情和创建 draft facts/claims。
- 竞品 API 新增 `/api/competitors/{competitor_id}/facts` 和 `/api/competitors/{competitor_id}/timeline`，详情主字段改为 `fact_count`。
- API 层只调用 service，不暴露 Store、Qdrant、LLM、Redis、SQL/DDL 等底层能力；旧 `/api/competitors/{id}/intel` 仅保留为 fact 口径别名。

---

## 2026-05 Phase 2 结构化事实层地基

本次落地 Phase 2 的前 4 步，只铺设结构化事实层底座，不接入 Pipeline、Agent 工具或 API 运行路径：

- 新增 `IntelFact`、`EvidenceRef`、`InsightClaim` 领域模型，事实、证据和 claim 均保持 dataclass 纯数据。
- 新增 `004_intel_fact_schema.sql`，创建 `intel_facts`、`intel_fact_competitors`、`intel_fact_products`、`evidence_refs` 和 `insight_claims`。
- 清理旧文档级情报字段和关联表：`source_documents.intel_type`、`source_documents.analysis_notes`、`source_documents.source_reliability`、`intel_competitors`、`intel_products`。
- 新增 `StructuredExtractionClientProtocol`、`IntelStoreProtocol`、`InsightStoreProtocol` 及 PostgreSQL 实现。
- 新增独立结构化抽取配置和客户端，结构化事实抽取不隐式复用 Agent/报告主 LLM。

---

## 2026-05 Phase 1 基础设施全量重构

本次重构替换了旧向量基础设施和 chunk schema：

- PostgreSQL 使用官方 `postgres:16`，不再依赖 vector extension。
- 新增 Qdrant，作为唯一子块向量索引。
- 删除旧向量 Store 协议、旧 PostgreSQL 向量实现、旧向量工厂函数和旧子块 embedding 语义。
- 新增 `VectorIndexProtocol` 与 `QdrantVectorIndex`，负责 collection、upsert、search、delete 和健康检查。
- 新增 `DocumentStoreProtocol` 与 `PostgresDocumentStore`，负责 `source_documents`、`document_parent_chunks`、`document_vector_points`。
- 新增文档模型 `SourceDocument`、`ParentDocumentChunk`、`ChildChunkPoint`、`ChildChunkSearchResult`。
- `ChunkingService` 改为输出 PostgreSQL 父块和 Qdrant 子块 point。
- 父子分块保证延续：子块 `<=512` tokens，父块约 `1024` tokens，父块由连续子块组成，父块之间通过共享尾部子块 overlap。
- Qdrant point id 固定为 `{document_id}:c:{chunk_index}`，payload 保存子块正文和 metadata。
- PostgreSQL 不保存子块 embedding，也不创建新的子块正文表。
- Scheduler 验证链路接入：Pipeline 和上传批次摄入写入 `task_runs/task_stages/task_events`，Redis 锁保护 Pipeline、上传批次和文档向量化，`/api/tasks/{task_id}` 返回 PostgreSQL 任务历史与 Celery 状态。
- Step 10 收尾清理完成：当前运行路径只保留 PostgreSQL、Redis、Qdrant 和本地文件存储；旧任务监控面板入口与 Windows 包管理器安装入口不作为项目依赖保留。

---

## 2026-05 InsightForge 竞品分析改造

- Logos 产品定位升级为 InsightForge，聚焦 AI 编程工具赛道竞品分析。
- 新增 `Competitor`、`CompetitorProduct`、`AnalysisReport`、`SourceRef`、`AuditLog` 等域模型；Phase 2 后新增 `EvidenceRef` 承接事实和 claim 的证据引用。
- 新增竞品 Store、报告 Store、API 路由、前端视图和 Agent 工具。
- Pipeline 支持情报自动关联竞品和产品线。

---

## 2026-05 Pipeline 抓取与任务反馈修复

- `/api/intel/pipeline` 返回 `task_id`，前端轮询 `/api/tasks/{task_id}`。
- RSS 抓取改为 `ThreadPoolExecutor` 并发，保留单源失败隔离。
- RSS/网页爬取源配置抽到 `core/source_config.py`。
- `WebCrawler` 的 per-site `max_pages` 改为显式参数。
- Pipeline/日报/清理 Celery 任务启用 autoretry、backoff 与 jitter。

---

## 2026-05 RAGAs 评估框架

- 新增 `evals/` 独立评估模块，依赖通过 `requirements-eval.txt` 隔离。
- 实现检索质量、端到端问答、Agent 工具调用三类评估。
- `evals/adapters.py` 将内部检索结果、Agent 事件和回答转换为 RAGAs sample。
- `evals/eval_config.json` 支持 OpenAI 兼容评判 LLM 和 embedding。
- 提供 `python -m evals.scripts.run_eval` 和合成测试集生成脚本。

---

## 2026-05 基础设施迁移

- SQLite 迁移到 PostgreSQL，解决多进程写入、JSONB 和全文搜索能力问题。
- APScheduler 迁移到 Celery + Redis，耗时任务异步执行，API 返回 `task_id`。
- 引入 Docker Compose 管理 PostgreSQL、Redis、Qdrant 等基础设施。
- 替换标准 logging 为 structlog，支持结构化日志和 request/task 上下文。

---

## 2026-05 检索架构升级

- 整篇文章 embedding 改为父子分块 RAG。
- 子块用于语义检索，父块用于 LLM 召回上下文。
- 混合检索采用 Qdrant 子块语义检索 + PostgreSQL 父块 FTS + RRF。
- 支持 `hybrid`、`semantic`、`keyword` 检索模式和可选 rerank。
