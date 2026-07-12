# InsightForge 架构文档

> **项目阶段**：Demo+（前后端分离架构 + ReAct Agent + 竞品分析 + 深度研究 + Web 搜索 + AI 摘要 + Rerank + PostgreSQL/Qdrant 混合检索 RAG + 结构化事实层 + 报告质量门禁 + 应用级认证授权 + Webhook 推送）

---

## 最近架构变更

| 时间 | 变更 | 摘要 |
|---|---|---|
| 2026-07 | **来源级采集与版本化清洗目标设计** | 接受按来源 fan-out/fan-in、httpx + Playwright、24 小时 Raw Fetch Artifact、Content Block 权威正文、独立 Celery 队列和 OTel/Prometheus；直接删除 Crawlee 与旧全局 Pipeline，不保留兼容路径 |
| 2026-05 | **Phase 3 报告治理与生产安全验收完成** | 报告生成统一走 `ReportService` + `ReportQualityService`，新增质量审查、审批发布、应用 API Key 角色授权、配置审计和生产 Compose 安全基线，并完成整体测试与运行文档同步 |
| 2026-05 | **Phase 2 Facts/Claims API 收口** | 新增 `/api/intel/facts`、`/api/insights/claims`，竞品详情补充 facts/timeline 口径；API 只调用 service 层，不恢复旧摘要链路 |
| 2026-05 | **Phase 2 服务层与事实抽取 Pipeline** | 新增 Intel/Insight/Report service、ServiceRegistry，并将 full pipeline 改为分块向量化后抽取 `IntelFact` / `EvidenceRef`、执行 fact 级竞品关联 |
| 2026-05 | **Agent 工具注册表重构** | 内置工具改为 `ToolSpec` 定义注册表和 `BuiltinToolFactory` 创建；`search_evidence` 替代旧知识库工具并支持 evidence 过滤下推，fact/claim 工具只通过 service 白名单访问业务层 |
| 2026-05 | **Scheduler 任务审计接入** | Pipeline 和上传批次摄入写入 `task_runs/task_stages/task_events`，Redis 锁保护 Pipeline、上传批次和文档向量化，`/api/tasks/{task_id}` 返回 PostgreSQL 历史与 Celery 状态 |
| 2026-05 | **上传文档摄入底座** | 新增 UploadStore、LocalFileBlobStore、ArchiveExtractor、DocumentParser 和 DocumentIngestionService，支持上传文件进入 SourceDocument/RAG 链路 |
| 2026-05 | **Phase 1 基础设施全量重构** | PostgreSQL 保存权威文档、父块、全文索引和 Qdrant point 状态；Qdrant 保存子块向量、正文 payload 和检索 metadata |
| 2026-05 | **InsightForge 竞品分析改造** | Logos -> InsightForge，新增竞品/报告域模型、Store、Agent 工具、API、前端 |
| 2026-05 | RAGAs 评估框架 | 三维度评估（检索质量 + 端到端问答 + Agent 工具调用），LLM-as-Judge |
| 2026-05 | 混合检索 + RRF | Qdrant 语义检索 + PostgreSQL 父块全文搜索 + Reciprocal Rank Fusion |
| 2026-05 | 父子分块 RAG | Markdown-aware 子块检索，父块召回完整上下文，父块之间通过共享尾部子块 overlap |
| 2026-05 | 基础设施迁移 | SQLite -> PostgreSQL，APScheduler -> Celery+Redis，Docker Compose |

完整变更历史见 [docs/design-docs/changelog.md](docs/design-docs/changelog.md)。

---

## 1. 系统概览

InsightForge 是一个 AI 驱动的竞品分析助手，聚焦 AI 编程工具赛道，核心能力包括：

1. 情报采集 Pipeline：来源级 Connector 发现 -> httpx/Playwright 获取 -> Raw Fetch Artifact -> Content Block 规范化 -> 来源准入与归簇 -> Document Version -> 父子分块/向量化 -> 结构化事实与证据绑定。
2. 竞品管理：竞品档案 CRUD、产品线管理、fact 聚合归因、多竞品横向对比。
3. ReAct Agent 分析：自然语言问答，Agent 自主推理并调用情报检索、竞品查询、报告生成和 Web 搜索工具。
4. 分析报告：生成结构化竞品分析报告，绑定 claim/evidence 关系，经过质量门禁后进入待审或修订状态。
5. 深度研究：Plan-Execute 多步研究任务，自动保存报告。
6. Web 搜索与 Webhook：多引擎搜索聚合，支持飞书/钉钉/企微/Telegram/ntfy 推送。
7. 安全与审计：应用级 API Key 认证、viewer/analyst/admin 授权、配置变更审计和生产健康检查。
8. RAGAs 评估：检索质量、端到端问答、Agent 工具调用三类自动化评估。

---

## 2. 技术选型

| 模块 | 选型 | 一句话理由 |
|---|---|---|
| 后端语言 | Python 3.11+ | AI 生态完善，后端实现直接 |
| 前端 | Vue 3 + Vite 6 | 轻量 SPA，开发效率高 |
| Web 框架 | FastAPI + Uvicorn | REST + SSE 流式支持 |
| 权威存储 | PostgreSQL 16 | JSONB、事务、全文索引、任务历史 |
| 向量索引 | Qdrant | 专职向量检索、payload 过滤、collection 重建 |
| 来源采集 | httpx + Playwright | 静态异步获取为默认路径，动态渲染按来源启用；删除 Crawlee |
| 内容清洗 | feedparser + trafilatura + markdownify + Content Block | 已获取 body 的确定性、版本化规范化，不使用统一清洗分数 |
| 任务调度 | Celery + Redis + PostgreSQL 状态机 | 来源级扇出、独立队列执行、PostgreSQL 权威汇合 |
| LLM / 结构化抽取 | openai / google-genai / anthropic SDK | 主 LLM 和结构化抽取分离配置，均通过 Protocol |
| 报告质量 Judge | openai / google-genai / anthropic SDK | 独立于主 LLM 和结构化抽取的 JSON Judge |
| 检索 | HybridSearchService + RRF | Qdrant 子块语义检索 + PostgreSQL 父块关键词检索 |
| 分块 | tiktoken + ChunkingService | Markdown-aware 父子分块，metadata 全链路保留 |
| 评估 | RAGAs + LLM-as-Judge | 自动化质量评估 |
| 可观测性 | structlog + OpenTelemetry + Prometheus | 结构化日志、跨阶段 trace、来源健康度和采集漏斗 |

完整选型论证见 [docs/design-docs/tech-decisions.md](docs/design-docs/tech-decisions.md)。

---

## 3. 分层架构

```text
Frontend (Vue 3)
  -> Delivery (FastAPI API / CLI)
  -> Agent + Tools (ReActAgent, ToolRegistry, built-in tools)
  -> Services (Collection Orchestrator, Normalize, Ingest, Query, Intel, Insight, Competitor, Report, ReportQuality, Webhook)
  -> Infrastructure
       - Source Connectors：RSS、Sitemap、Listing、API、Search 发现
       - HttpFetchEngine / BrowserFetchEngine：httpx 静态获取与 Playwright 动态渲染
       - CollectionRunStore / FetchArtifactStore：来源任务、artifact metadata 与权威状态
       - FetchBlobStore：Raw/Retained Fetch Artifact body
       - NormalizedDocumentStore：Normalized Document 与 Content Block
       - PostgresUploadStore：upload_batches、document_blobs 上传元数据
       - LocalFileBlobStore / ArchiveExtractor / DocumentParser：文件保存、安全解包和标准化解析
       - PostgresDocumentStore：source_documents、document_parent_chunks、document_vector_points
       - QdrantVectorIndex：子块向量与 payload 检索
       - ChunkingService：SourceDocument -> ParentDocumentChunk + ChildChunkPoint
       - HybridSearchService：Qdrant semantic + PostgreSQL keyword + RRF
       - PostgresIntelStore / PostgresInsightStore：结构化事实、证据和 claim
       - PostgresReportStore：报告、report-claim/report-evidence 关系、质量审查和审计
       - PostgresAuthStore / PostgresConfigAuditStore：API Key 哈希和配置审计
       - LLM / Structured Extraction / Judge / Embedding / Rerank / Web Search clients
  -> Core (Config, Protocols, Factory, Exceptions, Retry, Logging)
  -> Scheduler (Celery queues + Redis broker/rate limit + PostgreSQL fan-in)
```

层间依赖保持单向：Delivery -> Agent/Tools -> Services -> Infrastructure；Infrastructure 只实现 `core/protocols.py` 中的接口；`models/` 为纯 dataclass。Delivery 层的结构化事实和 claim API 只调用 `IntelService`、`InsightService`、`CompetitorService`，不直接访问 Store、Qdrant、LLM、Redis 或任意 SQL/DDL。

---

## 4. 关键目录

```text
core/
  config.py                 # AppConfig，含 Qdrant 配置和 embedding vector size
  config_manager.py         # ConfigManager，缓存 document/vector/task/redis 等基础设施
  protocols.py              # DocumentStoreProtocol / VectorIndexProtocol / IntelStoreProtocol 等
  factory.py                # 基础设施与 Service 工厂

models/
  document.py               # SourceDocument, ParentDocumentChunk, ChildChunkPoint
  intel.py                  # IntelFact / fact 类型 / 维度
  evidence.py               # EvidenceRef
  insight.py                # InsightClaim
  task_run.py               # TaskRun, TaskStage, TaskEvent
  file_asset.py             # UploadBatch, DocumentBlob, ParsedDocument
  article.py                # 新闻 UI/API 文章模型
  competitor.py             # 竞品 + 产品线
  report.py                 # 分析报告 + 来源引用 + 质量审查 + 审计
  search.py                 # 查询/检索结果 DTO

infrastructure/
  document_store.py         # PostgreSQL 文档、父块、point 状态权威存储
  upload_store.py           # PostgreSQL 上传批次与文件对象 metadata
  task_run_store.py         # PostgreSQL 任务 run/stage/event 权威存储
  redis/state_store.py      # Redis 锁、热状态、事件 stream、幂等和缓存
  files/blob_store.py       # 本地文件对象存储，按 hash 保存
  files/archive_extractor.py# zip 安全解包
  files/type_detector.py    # 保守文件类型识别
  parsers/document_parser.py# TXT/MD/HTML/CSV/TSV 标准化解析
  qdrant/vector_index.py    # QdrantVectorIndex
  chunking_service.py       # Markdown-aware 父子分块
  hybrid_search_service.py  # Qdrant + PostgreSQL keyword RRF
  keyword_search_service.py # PostgreSQL document_parent_chunks FTS
  postgres_article_store.py # 文章列表、摘要状态、旧新闻 API 支撑
  intel_store.py            # 结构化事实、fact 归因和 evidence_refs
  insight_store.py          # insight_claims 和 claim evidence
  report_store.py           # analysis_reports、报告关系表、质量审查和审计
  auth_store.py             # API Key 哈希、角色和最近使用时间
  config_audit_store.py     # 配置变更审计
  structured_extraction_client.py # 独立结构化抽取 AI 客户端
  judge_client.py           # 独立报告质量 Judge 客户端

migrations/
  001_infrastructure_foundation.sql # 新基础 schema，无 vector extension
  003_competitive_analysis_schema.sql
  004_intel_fact_schema.sql
  005_report_quality_security_schema.sql
```

---

## 5. 核心接口契约

| Protocol | 核心方法 | 当前实现 |
|---|---|---|
| `DocumentStoreProtocol` | `save_document`, `save_parent_chunks`, `get_parent_chunks_by_ids`, `list_parent_chunks`, `search_parent_chunks_by_keyword`, `mark_points_vectorized`, `mark_points_vector_failed` | `PostgresDocumentStore` |
| `VectorIndexProtocol` | `healthcheck`, `ensure_collection`, `recreate_collection`, `upsert_child_chunks`, `search_child_chunks`, `delete_by_document_ids`, `delete_by_point_ids` | `QdrantVectorIndex` |
| `UploadStoreProtocol` | `create_batch`, `finish_batch`, `save_blob`, `get_blob`, `list_blobs`, `find_blobs_by_sha256`, `update_blob_status` | `PostgresUploadStore` |
| `FileBlobStoreProtocol` | `put`, `open`, `delete`, `exists`, `quarantine` | `LocalFileBlobStore` |
| `ArchiveExtractorProtocol` | `can_extract`, `extract` | `ArchiveExtractor` |
| `DocumentParserProtocol` | `detect`, `parse` | `DocumentParser` |
| `TaskRunStoreProtocol` | `create_run`, `start_run`, `finish_run`, `create_stage`, `finish_stage`, `append_event`, `get_run`, `list_stages`, `list_events` | `PostgresTaskRunStore` |
| `RedisStateStoreProtocol` | `acquire_lock`, `release_lock`, `set_json`, `get_json`, `set_task_status`, `append_task_event`, `set_idempotency_key` | `RedisStateStore` |
| `ArticleStoreProtocol` | 新闻文章保存、摘要状态、列表查询、统计；不作为 Phase 2 事实层依赖 | `PostgresArticleStore` |
| `EmbeddingClientProtocol` | `embed` | `OpenAICompatibleEmbeddingClient` |
| `RerankClientProtocol` | `rerank` | `OpenAICompatibleRerankClient` |
| `LLMClientProtocol` | `generate`, `generate_stream`, `generate_with_history` | 4 个 LLM 客户端 |
| `StructuredExtractionClientProtocol` | `extract_json` | 4 个结构化抽取客户端 |
| `JudgeClientProtocol` | `judge_json` | 4 个报告质量 Judge 客户端 |
| `AuthStoreProtocol` | `create_api_key`, `get_api_key_by_hash`, `update_last_used` | `PostgresAuthStore` |
| `ConfigAuditStoreProtocol` | `append_config_audit`, `list_config_audit` | `PostgresConfigAuditStore` |
| `IntelStoreProtocol` | `save_fact`, `get_fact`, `list_facts`, `update_fact_status`, fact 竞品/产品 link，evidence 保存/查询 | `PostgresIntelStore` |
| `InsightStoreProtocol` | `save_claim`, `get_claim`, `list_claims`, `update_claim_status`, `attach_evidence` | `PostgresInsightStore` |
| `CompetitorStoreProtocol` | 竞品、产品线、情报关联 | `PostgresCompetitorStore` |
| `ReportStoreProtocol` | 报告、report-claim/report-evidence 关系、质量审查、审计链路 | `PostgresReportStore` |
| `AgentSessionStoreProtocol` / `MemoryStoreProtocol` | Agent 会话与记忆 | PostgreSQL + Redis 实现 |

旧向量 Store 协议、旧 PostgreSQL 向量实现和旧向量工厂函数已从当前基础设施契约中移除。

---

### 5.1 报告生成与质量门禁

`ReportService.generate_analysis_report()` 是 API 和 Agent 工具共用的唯一报告生成入口。工作流为：构建报告上下文包 -> 选择或生成 draft claims -> 调用主 LLM 起草 Markdown -> 保存 `analysis_reports`、`report_claims`、`report_evidence_refs` -> 调用 `ReportQualityService` -> 根据审查结果更新状态。

`ReportQualityService` 先执行规则门禁，再按配置调用独立 `JudgeClientProtocol`。规则门禁会阻断空报告、无 evidence、无效 citation、不可追踪 evidence、无效竞品和未声明的数据限制；Judge 不可用时，规则通过的报告进入 `waiting_review/needs_human`，不会自动发布。默认状态流转为 `draft -> quality_reviewing -> revision_required|waiting_review`。

审批发布由 `ReportService.approve_report()`、`reject_report()` 和 `publish_report()` 统一处理，Delivery 层不得直接修改报告状态。只有 `waiting_review + passed` 可审批通过或退回修订，只有 `approved + passed` 可发布；每次审批、拒绝和发布都会写入 `analysis_audit_log`。

Phase 3 Step 8 验收要求这些约束同时由自动化测试和生产 smoke 流程覆盖：无证据关键结论、无效 citation、Judge JSON 解析失败或低分不得进入 `approved/published`；`generate_analysis_report` Agent 工具只能调用 `ReportService`，不能绕过质量门禁。

### 5.2 应用级认证、授权与配置审计

FastAPI 使用 `delivery/auth.py` 提供的 API Key 认证和角色依赖。请求优先读取 `Authorization: Bearer <api_key>`，兼容 `X-API-Key`；明文 key 只在创建时出现一次，数据库 `api_keys` 仅保存 SHA-256 hash。`APP_ENV=development` 且 `AUTH_ENABLED=false` 时注入 `system/admin`，生产环境必须启用认证。

角色权限：

| 角色 | 权限 |
|---|---|
| `viewer` | 读取 facts、claims、competitors、reports、tasks、report audit/quality |
| `analyst` | viewer 权限 + 生成报告、重跑质量门禁、运行 Pipeline、创建/更新 draft facts/claims、Agent/Research 分析 |
| `admin` | 全部权限 + 配置修改/重载、配置审计、报告 approve/reject/publish/delete、Webhook 管理和推送 |

配置修改由 `ConfigAuditService` 计算 diff、脱敏 secret 并写入 `config_audit_log`。生产环境下 `APP_ENV`、`AUTH_ENABLED`、数据库/Redis/Qdrant 连接和本地存储路径属于只读部署配置，只能通过部署环境变量变更。

---

## 6. RAG 数据流

### 6.1 来源采集与知识写入

```text
Celery Beat / API / CLI
  -> Collection Orchestrator
  -> PostgreSQL Collection Run + per-source tasks
  -> Source Connectors -> Fetch Candidates
  -> fetch.http (httpx) / fetch.browser (Playwright)
  -> Raw Fetch Artifact (PostgreSQL metadata + Blob Store body)
  -> normalize -> Normalized Document + Content Blocks
  -> accepted / retry_render / review_required / rejected
  -> ingest: Source Governance + SHA-256/SimHash/shingles
  -> Source Occurrence + Document Cluster
  -> new/promoted Document Version
  -> enrich queue
  -> ChunkingService.chunk_documents()
       子块: ChildChunkPoint，<=512 tokens，有且只有一个 parent_chunk_id
       父块: ParentDocumentChunk，约 1024 tokens，连续子块组成
       overlap: 相邻父块共享尾部子块，父块 child_point_ids 保留 overlap 关系
  -> PostgresDocumentStore.save_parent_chunks()
  -> EmbeddingClient.embed(child contents)
  -> QdrantVectorIndex.upsert_child_chunks()
  -> PostgresDocumentStore.mark_points_vectorized()
  -> IntelService.extract_facts_from_document()
  -> Evidence Reference binding
  -> CompetitorService.auto_link_facts()
```

采集 fan-in 由 PostgreSQL Collection Run 状态机完成，不使用全局 Pipeline 锁或统一抓取间隔。Redis 只承担 Celery broker、来源 token bucket、短期租约、熔断冷却和进度缓存。Raw Fetch Artifact body 默认保留 24 小时；形成 Document Version 或 Evidence Reference 后晋升为长期保留产物。

`fetch.http`、`fetch.browser`、`normalize`、`ingest`、`enrich` 和 `ocr` 使用独立 Worker 预算。详细时序见 [docs/flows/pipeline-flow.md](docs/flows/pipeline-flow.md)，完整目标设计见 [docs/design-docs/collection-and-normalization.md](docs/design-docs/collection-and-normalization.md)。

### 6.2 混合检索

```text
Query
  -> EmbeddingClient.embed([query])
  -> QdrantVectorIndex.search_child_chunks()
       返回子块命中和 parent_chunk_id
  -> DocumentStore.search_parent_chunks_by_keyword()
       在 document_parent_chunks.search_vector 上做全文搜索
  -> HybridSearchService RRF 融合
  -> 按 parent_chunk_id 去重
  -> DocumentStore.get_parent_chunks_by_ids()
  -> 可选 Rerank
  -> LLM 使用完整父块上下文回答
```

语义通道失败时可降级到关键词通道；关键词通道失败时可保留语义通道；双通道失败才返回空结果或上层错误。

### 6.3 上传文档摄入

```text
Uploaded files / zip archives
  -> scheduler.tasks.run_upload_batch_task(batch_id)
  -> Redis lock logos:lock:upload:{batch_id}
  -> LocalFileBlobStore.put()
  -> PostgresUploadStore.save_blob()
  -> ArchiveExtractor.extract() for zip
  -> DocumentParser.parse()
       TXT/MD/HTML/CSV/TSV -> normalized Markdown/text
  -> SourceDocument(source_type="upload")
  -> PostgresDocumentStore.save_document()
  -> ChunkingService.chunk_document()
       子块: ChildChunkPoint -> Qdrant payload/vector
       父块: ParentDocumentChunk -> PostgreSQL FTS/context
  -> EmbeddingClient.embed(child contents)
  -> QdrantVectorIndex.upsert_child_chunks()
  -> PostgresDocumentStore.mark_points_vectorized()
```

上传批次摄入复用同一个 `task_runs` 记录；单个 blob 解析失败写入 blob error 和任务事件，同批次其他文件继续处理。文档向量化阶段使用 `logos:lock:vectorize:{document_id}`，Qdrant upsert 成功后才把 PostgreSQL point 状态标为 `vectorized`。

PDF/DOCX 目前只做类型识别并返回 unsupported，不伪装为解析成功。压缩包只启用 zip，且拒绝路径穿越、绝对路径、空文件和超限解包。

---

## 7. 数据模型与存储边界

### 7.1 当前实体关系

```text
SourceDocument (1) -> (N) ParentDocumentChunk
SourceDocument (1) -> (N) document_vector_points
SourceDocument (1) -> (N) IntelFact
ParentDocumentChunk (1) -> (N) EvidenceRef
ParentDocumentChunk (1) -> (N) ChildChunkPoint primary ownership
ParentDocumentChunk (N) -> (N) ChildChunkPoint overlap via child_point_ids
ChildChunkPoint -> Qdrant point payload + vector

Competitor (1) -> (N) Product
IntelFact (N) -> (N) Competitor/Product
IntelFact (1) -> (N) EvidenceRef
InsightClaim (N) -> (N) IntelFact via fact_ids
InsightClaim (1) -> (N) EvidenceRef
AnalysisReport (N) -> report_claims/report_evidence_refs/report_quality_reviews + source refs + audit trail
```

#### 已接受的结构化情报目标

上述关系描述当前实现。ADR-0002 已接受新的三层核心模型，顶层领域图固定为：

```text
Evidence Reference  <->  Intel Fact  <->  Insight Claim
```

数据库内部通过 fact-evidence、claim-fact 和事实归因关联表表达多对多关系，但这些关联表不是新的领域层。目标设计取消 claim 直连 evidence、JSON ID 数组、多态 evidence owner 和三层业务 score，并让 active fact 与 supported claim 使用不可变语义。完整设计和当前差异见 [结构化情报三层模型](docs/design-docs/structured-intelligence-model.md)；在实现迁移完成前，本节上方的“当前实体关系”和 [生成的数据库文档](docs/generated/db-schema.md) 仍作为现状参考。

### 7.2 PostgreSQL

PostgreSQL 是权威业务层：

- `source_documents`：统一来源文档 metadata、正文、来源、关联竞品/产品、解析状态。
- `document_parent_chunks`：父块权威正文、token 数、`child_point_ids`、heading path、全文索引 `search_vector`。
- `document_vector_points`：Qdrant point 状态、`point_id`、`parent_chunk_id`、`chunk_index`、hash、token 数、错误信息。
- `task_runs` / `task_stages` / `task_events`：异步任务历史、阶段结果和 append-only 审计事件。
- `upload_batches` / `document_blobs`：上传与文件对象基础表。
- `competitors` / `competitor_products` / `analysis_reports`：竞品和报告业务表。
- `report_claims` / `report_evidence_refs` / `report_quality_reviews`：报告到 claim/evidence 的关系、引用快照和质量审查结果。
- `config_audit_log` / `api_keys`：配置变更审计和应用 API Key 哈希。
- `intel_facts` / `intel_fact_competitors` / `intel_fact_products`：结构化事实、事件、信号及事实级竞品/产品归因。
- `evidence_refs` / `insight_claims`：事实/claim 证据引用和分析结论。

PostgreSQL 不保存子块 embedding，也不创建新的子块正文表；子块正文作为 Qdrant payload 保存。

### 7.3 Qdrant

主 collection：

```text
insightforge_documents_v1
```

point id 使用稳定 UUID，由 `document_id` 和 `chunk_index` 派生，满足 Qdrant 对 point id 的整数/UUID 约束。业务追踪字段保存在 payload 中：

```text
document_id, parent_chunk_id, chunk_index
```

Qdrant vector 保存子块 embedding；payload 保存子块正文和检索 metadata：`document_id`、`parent_chunk_id`、`chunk_index`、`content`、`content_hash`、`token_count`、`heading_path`、`doc_name`、`source`、`url`、`source_type`、`document_type`、`competitor_ids`、`product_ids`、`language`、`published_at`、`created_at`、`metadata`。

---

### 7.4 Redis

Redis 是执行期状态层，不保存长期事实：

- 来源级 token bucket、短期租约和熔断冷却。
- 分布式锁：如 `logos:lock:upload:{batch_id}`；采集不再使用全局 Pipeline 锁。
- 任务热状态：`logos:task:{run_id}`。
- 任务事件 stream：`logos:task_events:{run_id}`。
- 幂等键和短期缓存：如 `logos:idempotency:*`、`logos:cache:*`。

`RedisStateStore` 在 Redis 不可用时降级返回 `False`/`None`，长期任务历史仍以 PostgreSQL `task_runs/task_stages/task_events` 为准。

---

## 8. 父子分块保证

1. 子块按 Markdown 标题、段落、列表、表格、代码块等结构边界切分；超长 block 才按句子拆分，token 截断只作为兜底。
2. 子块最大 512 tokens，必须保留 `heading_path`、`doc_name`、`source`、`url`、`document_type`、`competitor_ids`、`product_ids`、`language` 等 metadata。
3. 父块由连续子块贪心组合到约 1024 tokens，不拆碎子块。
4. 相邻父块通过共享尾部子块达到约 100 tokens overlap。
5. 共享子块的 Qdrant point 仍只有一个主 `parent_chunk_id`；父块的 `child_point_ids` 保留 overlap 关系。
6. 短文档仍生成一个父块和至少一个子块，保证检索路径一致。

---

## 9. 进程与部署模型

本地开发：

```text
docker compose up -d
  logos-postgres :5432  PostgreSQL 16
  logos-redis    :6379  Celery broker/result、来源限速与短期协调
  logos-qdrant   :6333  Qdrant REST

start_dev.bat
  FastAPI Server  :8005
  Celery Workers  fetch.http/fetch.browser/normalize/ingest/enrich/ocr
  Celery Beat
  Vite Dev Server :5173

optional observability profile
  Prometheus
  OpenTelemetry Collector
  Grafana
```

生产部署：

```text
公网 80/443
  -> caddy (Basic Auth + reverse proxy)
  -> web (FastAPI + Vue 静态资源)

内部服务:
  migrate  一次性执行 SQL migration
  workers  Celery Workers，按队列独立并发预算
  beat     Celery Beat
  postgres PostgreSQL 16
  redis    Redis 7
  qdrant   Qdrant，不公开端口
```

生产环境只公开 Caddy；PostgreSQL、Redis、Qdrant、Worker、Beat 不直接暴露到公网。

---

## 10. 依赖注入

系统使用 `core/factory.py` 工厂函数和 `ConfigManager` 单例缓存：

```python
create_article_store(config)       -> PostgresArticleStore
create_document_store(config)      -> PostgresDocumentStore
create_task_run_store(config)      -> PostgresTaskRunStore
create_redis_state_store(config)   -> RedisStateStore
create_upload_store(config)        -> PostgresUploadStore
create_file_blob_store(config)     -> LocalFileBlobStore
create_archive_extractor(config)   -> ArchiveExtractor
create_document_parser(config)     -> DocumentParser
create_qdrant_vector_index(config) -> QdrantVectorIndex
create_intel_store(config)         -> PostgresIntelStore
create_insight_store(config)       -> PostgresInsightStore
create_structured_extraction_client(config) -> StructuredExtractionClient
create_judge_client(config)      -> JudgeClient
create_embedding_client(config)    -> OpenAICompatibleEmbeddingClient
create_rerank_client(config)       -> RerankClient | None
create_llm_client(config)          -> LLMClient
create_chunking_service(config)    -> ChunkingService
create_intel_service(config, mgr)  -> IntelService
create_insight_service(config, mgr)-> InsightService
create_competitor_service(config, mgr) -> CompetitorService
create_report_service(config, mgr) -> ReportService  # 内部组装 ReportQualityService
create_auth_store(config)          -> PostgresAuthStore
create_config_audit_store(config)  -> PostgresConfigAuditStore
create_service_registry(config, mgr) -> ServiceRegistry
create_builtin_tool_definition_registry() -> ToolDefinitionRegistry
create_builtin_tool_factory(config, mgr) -> BuiltinToolFactory
```

`ConfigManager` 暴露 `document_store`、`vector_index`、`task_run_store`、`redis_state_store`、`intel_store`、`insight_store`、`report_store`、`auth_store`、`config_audit_store`、`structured_extraction_client`、`judge_client`、`intel_service`、`insight_service`、`competitor_service`、`report_service`、`service_registry`、`builtin_tool_definition_registry` 和 `builtin_tool_factory`，不再暴露旧向量 Store 属性。`service_registry` 只允许 Agent 工具解析 service 级依赖，不暴露 Store、LLM、Qdrant、Redis 或原始配置对象。

---

## 11. 配置

关键基础设施配置：

| 配置项 | 默认/说明 |
|---|---|
| `pg_dsn` | PostgreSQL 连接串 |
| `celery_broker_url` / `celery_result_backend` | Redis/Celery 连接串 |
| `qdrant_url` | `http://localhost:6333` |
| `qdrant_api_key` | 本地为空，生产可设置 |
| `qdrant_documents_collection` | `insightforge_documents_v1` |
| `qdrant_distance` | `Cosine` |
| `vector_backend` | `qdrant` |
| `embedding_vector_size` | Qdrant collection vector size |
| `upload_storage_root` | 本地上传文件存储根目录，默认 `storage` |
| `upload_max_file_size_mb` | 单文件大小限制，默认 `50` |
| `upload_max_batch_size_mb` | 上传批次大小限制，默认 `200` |
| `upload_max_archive_files` | 单个 zip 最多解包文件数，默认 `200` |
| `upload_max_archive_unpacked_mb` | zip 解包后总大小限制，默认 `500` |
| `upload_allowed_extensions` | `txt,md,markdown,html,htm,csv,tsv,zip` |
| `structured_extraction_provider` | 结构化抽取 provider，独立于主 LLM |
| `structured_extraction_model` | 结构化抽取模型 |
| `structured_extraction_base_url` / `structured_extraction_api_key` | 结构化抽取独立连接配置 |
| `structured_extraction_temperature` / `structured_extraction_max_tokens` | 结构化抽取默认温度和输出 token 限制 |
| `judge_provider` / `judge_model` | 报告质量 Judge provider 和模型 |
| `judge_base_url` / `judge_api_key` | Judge 独立连接配置 |
| `app_env` / `auth_enabled` / `app_api_keys` | 应用环境与 API Key 认证基线 |
| `report_quality_min_score` / `report_quality_auto_publish` | 报告质量阈值和自动发布策略，生产默认不自动发布 |
| `chunk_max_child_tokens` | 512 |
| `chunk_target_parent_tokens` | 1024 |
| `chunk_overlap_tokens` | 100 |

---

## 12. 测试与验证

当前基础设施重构覆盖：

- schema 测试：无 `CREATE EXTENSION vector`，无 embedding 列，父块 GIN FTS 索引存在。
- 分块回归测试：标题路径、metadata、父块 overlap、短文档父子双生成、子块唯一 `parent_chunk_id`。
- Qdrant 测试：ensure/recreate、upsert/search/delete、payload filter、异常映射。
- 任务/Redis 测试：run/stage/event 持久化、Redis owner 校验释放锁、Redis 不可用降级。
- 结构化事实层测试：`IntelFact` / `EvidenceRef` / `InsightClaim` 模型、结构化抽取 JSON 解析、ConfigManager 新组件缓存；PostgreSQL Store 和 migration 测试在 `TEST_PG_DSN` 存在时运行。
- 报告治理测试：质量规则门禁、Judge 异常降级、报告状态流转、审批发布、Agent 工具调用 `ReportService`、报告 API 质量 payload。
- 安全与配置测试：API Key 认证、viewer/analyst/admin 权限矩阵、配置脱敏、配置审计、生产健康检查和部署 compose 配置。
- 端到端基础测试：分块后父块进入 PostgreSQL，子块进入 Qdrant，Qdrant 命中可通过 `parent_chunk_id` 召回父块。

---

## 13. 运行方式

```bash
pip install -r requirements.txt
cd frontend && pnpm install && cd ..

cp .env.example .env
docker compose up -d

python -m delivery.server
celery -A scheduler.celery_app worker -l info -P threads
celery -A scheduler.celery_app beat -l info
cd frontend && pnpm dev
```

VPS 部署：

```bash
cp .env.deploy.example .env
docker compose -f docker-compose.prod.yml up -d --build
```

详细部署说明见 [docs/deployment/docker-vps.md](docs/deployment/docker-vps.md)。
