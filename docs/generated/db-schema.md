# 数据库业务规则补充说明

> `docs/generated/dbdoc/` 为数据库表结构说明。当前权威 DDL 是 [migrations/001_infrastructure_foundation.sql](../../migrations/001_infrastructure_foundation.sql) 和后续 migration；本文件只记录 tbls 难以表达的业务规则。

---

## 文档 RAG 存储边界

PostgreSQL 保存权威业务记录：

- `upload_batches`：一次上传操作的批次状态、文件数量、总大小、上下文 metadata 和批次错误。
- `document_blobs`：上传原始文件或解包子文件的 metadata、sha256、存储路径、父子文件关系和处理状态。
- `source_documents`：统一来源文档 metadata、正文、来源 URL、语言、hash、竞品/产品关联和解析状态。
- `document_parent_chunks`：父块正文、token 数、`child_point_ids`、标题路径、metadata 和 `search_vector`。
- `document_vector_points`：Qdrant point 状态、`point_id`、`parent_chunk_id`、`chunk_index`、hash、token 数和错误信息。

Qdrant 保存子块索引：

- vector：子块 embedding。
- payload：子块正文和检索 metadata。

PostgreSQL 不保存子块 embedding，也不创建新的子块正文表。

---

## 核心实体关系

```text
SourceDocument (1) -> (N) ParentDocumentChunk
SourceDocument (1) -> (N) document_vector_points
SourceDocument (1) -> (N) IntelFact
ParentDocumentChunk (1) -> (N) EvidenceRef
IntelFact (1) -> (N) EvidenceRef
IntelFact (N) -> (N) Competitor via intel_fact_competitors
IntelFact (N) -> (N) CompetitorProduct via intel_fact_products
InsightClaim (N) -> (N) IntelFact via fact_ids JSONB
InsightClaim (1) -> (N) EvidenceRef
AnalysisReport (N) -> (N) InsightClaim via report_claims
AnalysisReport (1) -> (N) ReportEvidenceRef
AnalysisReport (1) -> (N) ReportQualityReview
UploadBatch (1) -> (N) DocumentBlob
DocumentBlob (1) -> (N) DocumentBlob extracted children
DocumentBlob (1) -> (0..1) SourceDocument
ParentDocumentChunk (1) -> (N) ChildChunkPoint primary ownership
ParentDocumentChunk (N) -> (N) ChildChunkPoint overlap via child_point_ids
ChildChunkPoint -> Qdrant point

AgentSession (1) -> general_query / research_plan_execute session
Competitor (1) -> (N) CompetitorProduct
AnalysisReport -> source_refs + audit_trail (legacy compatibility)
TaskRun (1) -> (N) TaskStage
TaskRun (1) -> (N) TaskEvent
TaskStage (1) -> (N) TaskEvent
```

`document_parent_chunks.document_id` 和 `document_vector_points.document_id` 均级联引用 `source_documents.id`。`document_vector_points.parent_chunk_id` 级联引用 `document_parent_chunks.parent_chunk_id`。
`intel_facts.source_document_id` 级联引用 `source_documents.id`；`evidence_refs` 通过 `owner_type/owner_id` 挂到 `intel_fact` 或 `insight_claim`，并可选引用 `source_documents.id` 与 `document_parent_chunks.parent_chunk_id`。
`report_claims.report_id`、`report_evidence_refs.report_id` 和 `report_quality_reviews.report_id` 均级联引用 `analysis_reports.id`。`report_claims.claim_id` 级联引用 `insight_claims.id`；`report_evidence_refs` 可选引用 `evidence_refs`、`insight_claims` 和 `intel_facts`，引用目标删除时保留报告证据快照并将对应外键置空。
`task_stages.task_run_id` 和 `task_events.task_run_id` 均级联引用 `task_runs.id`；`task_events.stage_id` 在阶段删除时置空，保留任务事件审计记录。

---

## 父子分块规则

| 参数 | 默认值 | 说明 |
|---|---|---|
| `chunk_max_child_tokens` | 512 | 子块最大 token 数 |
| `chunk_target_parent_tokens` | 1024 | 父块目标 token 数 |
| `chunk_overlap_tokens` | 100 | 父块间 overlap token 数 |
| `embedding_vector_size` | 1536 | Qdrant collection vector size |

关键规则：

- 子块按 Markdown 标题、段落、列表、表格、代码块等结构边界切分。
- 超长 block 才按句子切分，token 截断只作为兜底。
- 子块 metadata 保留 `heading_path`、`doc_name`、`source`、`url`、`document_type`、`competitor_ids`、`product_ids`、`language`。
- 父块由连续子块贪心组合到约 `1024` tokens，不拆碎子块。
- 相邻父块通过共享尾部子块实现约 `100` tokens overlap。
- 共享子块的 Qdrant point 仍只归属一个主 `parent_chunk_id`。
- 父块 `child_point_ids` 保留 overlap 关系。
- 短文档仍生成一个父块和至少一个子块。

---

## 存储示意

```text
SourceDocument
  -> ChunkingService
       -> ParentDocumentChunk[] -> PostgreSQL document_parent_chunks
            content + child_point_ids + search_vector
       -> ChildChunkPoint[] -> EmbeddingClient -> QdrantVectorIndex
            vector + payload.content + payload metadata
       -> document_vector_points
            point_id + vector_status + error
```

---

## SourceDocument 生命周期

```text
pending -> parsed -> chunked -> vectorized
                     \-> failed
```

- `pending`：文档已记录，等待解析或分块。
- `parsed`：正文和 metadata 可用。
- `chunked`：父块和 point 状态已写入 PostgreSQL。
- `vectorized`：Qdrant upsert 成功。
- `failed`：解析、分块、embedding 或 Qdrant 写入失败。

旧新闻列表层仍可保留 `ArticleStatus`：

```text
stored -> pending_summary -> summarized -> embedded
```

该状态只服务新闻 UI/API，不是新 RAG 存储权威；full pipeline 不再依赖 `pending_summary/summarized/embedded` 推进。

---

## 结构化事实与证据边界

Phase 2 后，结构化情报事实不再保存到 `source_documents.intel_type`、`source_documents.analysis_notes` 或 `articles.summary`。事实层使用独立业务表：

- `intel_facts`：保存原子事实/事件/信号，含事实类型、维度、重要度、置信度和来源可靠度。
- `intel_fact_competitors` / `intel_fact_products`：保存事实级竞品和产品归因。
- `evidence_refs`：保存短 snippet 和定位信息，回链 `source_documents` 与 `document_parent_chunks`。
- `insight_claims`：保存基于事实和证据形成的分析结论。

RAG 继续负责原文证据召回和开放式检索，`IntelFact` 不向量化为第二套语义检索主路径。

---

## 报告质量与安全基线

Phase 3 整体验收后，报告治理与安全基础表由 `005_report_quality_security_schema.sql` 提供：

- `analysis_reports`：新增 `version`、`review_status`、`quality_score`、`quality_summary`、`generation_context_hash`、审批和发布时间字段。
- `report_claims`：保存报告与 `InsightClaim` 的章节级关系。
- `report_evidence_refs`：保存报告正文引用到 evidence/fact/claim 的关系和 URL/title/snippet 快照。
- `report_quality_reviews`：保存规则、LLM Judge 或人工审查结果、分项评分、问题和修订建议。
- `config_audit_log`：独立保存配置变更审计，不混入报告审计。
- `api_keys`：保存应用 API Key 哈希、角色和状态，不保存明文密钥。

报告状态扩展为：

```text
draft -> quality_reviewing -> revision_required/waiting_review -> approved -> published
                         \-> rejected
published -> archived
```

`analysis_reports.source_refs` 和 `audit_trail` 继续保留为旧报告兼容字段；新报告写入路径应优先使用 `report_claims`、`report_evidence_refs` 和 `report_quality_reviews`。

发布规则由服务层执行：报告生成后必须先写入质量审查记录；无证据关键结论、无效 citation、Judge JSON 解析失败或低于质量阈值时不得进入 `approved` 或 `published`。默认发布路径是 `waiting_review + passed -> approved -> published`，`REPORT_QUALITY_AUTO_PUBLISH=false` 是生产默认。

应用 API Key 只保存 hash，角色值为 `viewer`、`analyst`、`admin`。配置修改记录写入 `config_audit_log`，`before_masked` 和 `after_masked` 不能包含 secret 原文。

Phase 3 Step 8 验收口径：

- `ReportQualityReview.status=failed` 的报告只能进入 `revision_required`。
- `ReportQualityReview.status=passed` 的报告默认进入 `waiting_review`，仍需 admin 审批后才能发布。
- `api_keys.key_hash` 是认证查找字段，明文 key 只在创建时返回一次。
- `config_audit_log` 与 `analysis_audit_log` 分离，配置审计不得混入报告生成、审批或发布事件。

---

## 上传文件生命周期

`upload_batches.status`：

```text
received -> processing -> succeeded/partial_failed/failed/cancelled
```

`document_blobs.status`：

```text
stored -> extracted/parsed/failed/rejected/quarantined
```

关键规则：

- 文件字节保存在 FileBlobStore；`document_blobs.storage_path` 保存可追踪路径。
- `document_blobs.sha256` 用于重复文件识别，不要求数据库唯一。
- zip 解包后的子文件使用 `parent_blob_id` 指回原压缩包。
- 解析成功的 blob 通过 `source_documents.blob_id` 进入文档 RAG 链路。
- 单个 blob 失败时必须写入 `document_blobs.error`，同批次其他文件可继续处理。
- PDF/DOCX 当前只识别为 unsupported，不进入 `source_documents`。

---

## AgentSession 通用 Agent 会话

`agent_sessions` 同时保存普通问答和 Plan-Execute 深度研究会话。普通问答使用 `session_type=general_query` 和 `active` 状态；深度研究使用 planned/approved/running/completed 状态流。

状态流转：

```text
active -> completed/failed/cancelled
planned -> approved -> running -> completed
                     \-> failed
planned -> cancelled
```

执行期 Redis 可缓存会话热数据，PostgreSQL 是权威存储。

---

## 任务历史与 Redis 状态

`task_runs`、`task_stages`、`task_events` 是所有异步任务生命周期的 PostgreSQL 权威记录：

- `task_runs`：保存任务类型、幂等键、输入、结果、错误、尝试次数和整体时间戳。
- `task_stages`：保存任务阶段名称、阶段状态、阶段结果、阶段错误和阶段时间戳。
- `task_events`：append-only 事件流，用于审计和后续实时状态回放。
- 手动 Pipeline API 以 `task_runs.id` 作为 Celery task id；`/api/tasks/{task_id}` 读取 run、stages、events 并附带 Celery 状态。
- Pipeline 阶段包括 collect、markdown、store_source_documents、chunk_and_vectorize、extract_intel_facts 和 link_facts；上传批次阶段包括 upload_batch、parse_documents、chunk_documents 和 vectorize_document。

任务状态统一使用：

```text
pending -> running -> succeeded/failed/cancelled/skipped
```

Redis 只保存执行期状态：

- `logos:task:{run_id}`：任务热状态。
- `logos:task_events:{run_id}`：任务事件 stream。
- `logos:lock:pipeline`：Pipeline 全局执行锁。
- `logos:lock:upload:{batch_id}`：上传批次执行锁。
- `logos:lock:document_parse:{blob_id}`：单 blob 解析锁。
- `logos:lock:vectorize:{document_id}`：文档向量化锁。
- `logos:idempotency:*` / `logos:cache:*`：短期幂等键和缓存。

Redis 不可用时，热状态、事件 stream、幂等和缓存可以丢失；PostgreSQL 任务历史必须保持完整。

---

## 三层记忆系统

- `core_memory_revisions`：核心记忆版本表，不物理删除。
- `persistent_memories`：跨会话记忆，默认 `pending`，用户确认后变为 `active`。
- `agent_sessions.summary`：会话摘要，用于后续 prompt 注入。

MEMORY 索引以数据库中 `status=active` 的持久记忆为准。
