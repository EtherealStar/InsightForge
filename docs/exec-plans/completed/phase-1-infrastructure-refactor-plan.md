# 第一阶段基础设施层重构改造计划

> **状态**：规划文档  
> **撰写日期**：2026-05-23  
> **依据文档**：`docs/exec-plans/enterprise-ai-competitor-analysis-plan.md`、`ARCHITECTURE.md`、`docs/DESIGN.md`、`docs/design-docs/protocol-contracts.md`、`docs/generated/db-schema.md`、`docs/exec-plans/tech-debt-tracker.md`  
> **阶段定位**：企业级 AI 竞品分析改造的第一阶段，面向最底层基础设施层。  
> **核心原则**：允许并鼓励完整重构，严禁最小改动式补丁。现有数据库数据可以清空，不为旧数据兼容牺牲新架构。

---

## 1. 背景

`enterprise-ai-competitor-analysis-plan.md` 将企业级升级第一阶段定义为 **Redis 状态层与任务历史**。在新的项目目标下，第一阶段还必须同时完成两件更底层的架构调整：

1. **向量数据库从 PostgreSQL/pgvector 切换为 Qdrant**。PostgreSQL 继续作为权威关系存储，Qdrant 专职承载向量索引、向量检索与向量 payload 过滤。
2. **为用户上传产品文档、竞品文档、压缩包建立基础设施底座**。未来前端上传的 PDF、Word、Markdown、HTML、文本、CSV、压缩包等文件，必须能被安全接收、暂存、解析、去重、分块、向量化、追踪任务状态并关联到竞品/产品/来源。

因此第一阶段不是“在现有 pgvector 代码上加任务历史”，而是重建基础设施底座：

- PostgreSQL 保存权威元数据、任务历史、文件清单、文档解析结果、报告和审计。
- Qdrant 保存文档 chunk 向量、向量 payload 和后续可扩展的 insight/claim 向量集合。
- Redis 保存执行期状态、锁、幂等、短期缓存、限流和任务事件流。
- 文件存储层保存用户上传原始文件、解包后的子文件、解析中间产物和可追溯 hash。
- 旧的 pgvector、新闻助手遗留命名和过宽 Store 边界要纳入删除计划。

本阶段完成后，Phase 2 的结构化竞品情报、Phase 3 的报告质量门禁和后续前端文档上传能力，都应建立在同一套基础设施契约上，而不是再次重构底层。

---

## 2. 重构目标

### 2.1 阶段目标

第一阶段完成后，基础设施层应具备以下能力：

1. **PostgreSQL 权威存储底座**：统一连接、事务、JSONB 编解码、错误映射、健康检查和 migration 治理。
2. **Qdrant 向量索引底座**：统一 collection 管理、upsert、search、delete、payload 过滤、健康检查和重建索引能力。
3. **Redis 执行期状态层**：统一锁、幂等、缓存、Hash 状态、Stream 事件和限流。
4. **任务历史权威存储**：`task_runs`、`task_stages`、`task_events` 成为异步任务生命周期的 PostgreSQL 权威记录。
5. **上传文件基础设施**：支持原始文件/压缩包接收、校验、解包、去重、暂存、解析状态追踪和后续文档入库。
6. **文档型知识底座**：把外部网页、RSS 文章、用户上传产品文档、竞品文档都抽象为统一的 `SourceDocument`，后续再抽取 `IntelItem`。
7. **基础设施职责拆分清晰**：Document、File、Chunk、VectorIndex、Task、State、Competitor、Report 各自有独立 Store 或 Client。
8. **旧基础设施可删除**：明确哪些 pgvector/新闻助手遗留组件删除、替换、保留或重命名。
9. **可清库重建**：不考虑现有数据库数据迁移，允许通过新 migration 或 reset 脚本重建 schema。

### 2.2 明确非目标

第一阶段不实现以下业务能力：

- 不实现完整前端上传页面。
- 不实现 `IntelItem`、`InsightClaim` 业务抽取逻辑。
- 不实现报告质量门禁。
- 不重写 ReAct Agent 推理循环。
- 不引入 Multi-agent、Temporal、Airflow 等新运行时。

第一阶段只提供这些能力所需的基础设施契约、存储和任务追踪底座。

---

## 3. 新的基础设施边界

### 3.1 存储职责

| 层 | 职责 | 不负责 |
|---|---|---|
| PostgreSQL | 权威元数据、任务历史、文件索引、文档元数据、chunk 文本、竞品、报告、审计 | 向量相似度检索 |
| Qdrant | chunk 向量、向量 payload、向量过滤、向量集合重建 | 权威业务记录、审计历史 |
| Redis | 锁、幂等、任务热状态、事件流、限流、短期缓存 | 长期事实、长期审计 |
| File Storage | 上传原始文件、解包文件、解析中间产物 | 文档业务元数据、向量索引 |

### 3.2 统一文档模型

未来系统不应继续以 `Article` 作为所有知识来源的核心抽象。第一阶段应引入更通用的文档模型：

| 对象 | 说明 |
|---|---|
| `SourceDocument` | 统一表示网页文章、RSS 文章、用户上传产品文档、竞品文档、解包后的子文件 |
| `DocumentChunk` | 文档分块文本和结构信息，权威文本保存在 PostgreSQL |
| `DocumentBlob` | 原始上传文件或抓取快照的文件对象元数据 |
| `UploadBatch` | 一次上传操作，可能包含多个文件或一个压缩包解出的多个文件 |
| `VectorPointRef` | PostgreSQL chunk 与 Qdrant point 的关联 |

`Article` 可以保留短期适配，但不再作为新基础设施的中心模型。

### 3.3 Qdrant collection 规划

第一阶段至少建立一个主 collection：

```text
insightforge_documents_v1
```

建议 payload：

| payload 字段 | 说明 |
|---|---|
| `document_id` | PostgreSQL `source_documents.id` |
| `chunk_id` | PostgreSQL `document_chunks.id` |
| `source_type` | `rss/web/upload/manual/api` |
| `document_type` | `article/product_doc/competitor_doc/report/other` |
| `competitor_ids` | 关联竞品 ID 数组 |
| `product_ids` | 关联产品线 ID 数组 |
| `upload_batch_id` | 上传批次 ID，可为空 |
| `blob_id` | 原始文件 ID，可为空 |
| `content_hash` | chunk 文本 hash |
| `language` | 语言 |
| `published_at` | 外部发布时间 |
| `created_at` | 入库时间 |
| `visibility` | 后续多租户/权限预留 |

后续阶段可增加：

```text
insightforge_claims_v1
insightforge_reports_v1
```

第一阶段不要把 claim/report 向量混入文档 collection，避免后续过滤和 rerank 语义混乱。

---

## 4. 当前基础设施问题

### 4.1 pgvector 与新目标不匹配

当前项目已将向量合并进 PostgreSQL `child_chunks`，这降低了 Demo 运维复杂度，但在企业级竞品文档场景下会暴露问题：

- 用户上传文档和压缩包后，chunk 数量会快速增长，向量索引和关系元数据混在一个库里扩展性较差。
- Qdrant 的 collection、payload 过滤、向量索引重建、批量 upsert 更适合作为专职向量数据库。
- PostgreSQL 应专注权威业务记录、事务一致性、审计和结构化查询。
- 既然现有数据可清空，就没有必要继续背负 pgvector 表结构和迁移兼容成本。

### 4.2 Store 边界过宽

`PostgresArticleStore` 同时承担文章 CRUD、摘要状态、父 chunk、FTS 搜索、jieba 分词和部分 pipeline 状态。新架构下应拆分为：

- `PostgresDocumentStore`
- `PostgresChunkStore`
- `PostgresUploadStore`
- `PostgresTaskRunStore`
- `QdrantVectorIndex`
- `RedisStateStore`

### 4.3 Redis 使用分散

Redis 当前散落在 `scheduler/tasks.py` 和 `AgentSessionStore` 内。第一阶段后，业务代码不得直接 `redis.Redis.from_url()`，必须通过 `RedisStateStoreProtocol`。

### 4.4 上传文件基础设施缺失

当前系统有网页抓取和 Markdown 转换，但没有企业文档摄入所需的底层能力：

- 上传批次记录。
- 原始文件保存和 hash 去重。
- 压缩包安全解包。
- 文件类型识别。
- 解析状态与错误记录。
- 大文件大小限制。
- 文件到文档、文档到 chunk、chunk 到 Qdrant point 的追踪。

### 4.5 Schema 权威来源不清晰

部分 Store 在 `_init_db()` 中执行 DDL，同时存在 migration。第一阶段后，新表和索引只通过 migration 创建；Store 初始化只做健康检查。

---

## 5. 重构原则

### 5.1 完整重构优先

本阶段不接受：

- 继续在 pgvector 旧结构上扩展新文档摄入。
- 继续在 `PostgresArticleStore` 中添加上传、chunk、搜索或任务方法。
- 为了少改文件而保留 `child_chunks` 向量表作为新架构核心。
- 在 Python Store `_init_db()` 中继续追加生产 DDL。
- 为了兼容旧数据保留复杂迁移路径。

### 5.2 数据可清空

本次重构可以清空现有 PostgreSQL、Qdrant、Redis 和本地运行时数据：

- 不设计旧 `articles/parent_chunks/child_chunks` 到新 `source_documents/document_chunks/Qdrant` 的数据迁移。
- 可以新增 `scripts/reset_infrastructure.py` 或文档化 `docker compose down -v` 重建方式。
- migration 只面向新 schema，不承担历史数据转换。

### 5.3 PostgreSQL 与 Qdrant 双写边界清晰

向量化写入必须遵循：

1. PostgreSQL 先保存 `source_documents` 和 `document_chunks`。
2. Embedding 生成成功后，Qdrant upsert point。
3. PostgreSQL 保存 `vector_points` 或在 `document_chunks` 上保存 `vector_status/vector_point_id`。
4. Qdrant 写失败时，chunk 保留 `vector_status=failed/pending_retry`，任务阶段失败或降级，不伪装成功。

### 5.4 Protocol 先于实现

新增基础设施能力先定义 Protocol，再实现具体类，再由 `core/factory.py` 装配。Protocol 不暴露 Qdrant SDK、Redis SDK 或 psycopg2 具体类型。

### 5.5 文件摄入默认保守

上传基础设施默认：

- 限制单文件大小、批次大小、压缩包解包总大小和文件数量。
- 防止 zip slip 路径穿越。
- 拒绝可执行文件和未知高风险类型。
- 所有文件以 hash 命名或分层保存，原始文件名只作为元数据。
- 解析失败必须记录原因，不影响同批次其他文件继续处理。

---

## 6. 目标基础设施架构

```text
core/
  protocols.py
  factory.py
  config.py
  exceptions.py

models/
  document.py              # SourceDocument, DocumentChunk
  file_asset.py            # DocumentBlob, UploadBatch
  task_run.py              # TaskRun, TaskStage, TaskEvent

infrastructure/
  db/
    postgres.py            # 连接、事务、健康检查
    json.py
    errors.py
  redis/
    state_store.py         # RedisStateStore
  qdrant/
    vector_index.py        # QdrantVectorIndex
    collections.py         # collection ensure/recreate
  files/
    blob_store.py          # LocalFileBlobStore，后续可换 S3/MinIO
    archive_extractor.py   # zip/tar 安全解包
    type_detector.py       # 文件类型识别
  parsers/
    document_parser.py     # PDF/DOCX/MD/HTML/TXT 解析统一入口
  stores/
    document_store.py      # source_documents/document_chunks
    upload_store.py        # upload_batches/document_blobs
    task_run_store.py
    competitor_store.py
    report_store.py
  search/
    keyword_search_service.py
    hybrid_search_service.py
  clients/
    llm_client.py
    embedding_client.py
    rerank_client.py
    web_search_client.py
    web_crawler.py
```

目录可分步调整，但第一阶段必须完成职责拆分。旧文件可以通过兼容适配短期保留，但不再承载新职责。

---

## 7. 必须新增或重定义的 Protocol

### 7.1 `VectorIndexProtocol`

替代当前 pgvector 方向的 `VectorStoreProtocol`，面向 Qdrant。

| 方法 | 语义 |
|---|---|
| `healthcheck()` | 检查 Qdrant 可用性 |
| `ensure_collection(name, vector_size, distance)` | 确保 collection 存在 |
| `recreate_collection(name, vector_size, distance)` | 清空并重建 collection，仅允许重建场景 |
| `upsert_chunks(collection, chunks, embeddings)` | 批量写入 chunk 向量和 payload |
| `search(collection, query_embedding, top_k, filters)` | 向量检索 |
| `delete_by_document_ids(collection, document_ids)` | 删除文档对应 points |
| `delete_by_chunk_ids(collection, chunk_ids)` | 删除指定 chunk points |
| `scroll(collection, filters, limit, offset)` | 调试和重建校验 |

### 7.2 `DocumentStoreProtocol`

| 方法 | 语义 |
|---|---|
| `save_document(document)` | 保存文档元数据 |
| `get_document(document_id)` | 获取文档 |
| `list_documents(filters, limit, offset)` | 查询文档 |
| `update_parse_status(document_id, status, error)` | 更新解析状态 |
| `save_chunks(document_id, chunks)` | 保存 chunk 文本和结构 |
| `list_chunks(document_id)` | 查询文档 chunks |
| `mark_chunks_vectorized(chunk_ids, point_ids)` | 标记 Qdrant 写入成功 |
| `mark_chunks_vector_failed(chunk_ids, error)` | 标记向量化失败 |
| `delete_document(document_id)` | 删除文档及 chunks |

### 7.3 `UploadStoreProtocol`

| 方法 | 语义 |
|---|---|
| `create_batch(batch)` | 创建上传批次 |
| `finish_batch(batch_id, status, error)` | 结束上传批次 |
| `save_blob(blob)` | 保存文件元数据 |
| `get_blob(blob_id)` | 获取文件元数据 |
| `list_blobs(batch_id)` | 查询批次文件 |
| `update_blob_status(blob_id, status, error)` | 更新文件处理状态 |

### 7.4 `FileBlobStoreProtocol`

| 方法 | 语义 |
|---|---|
| `put(stream, metadata)` | 保存原始文件，返回 blob path/hash/size |
| `open(blob_path)` | 读取文件流 |
| `delete(blob_path)` | 删除文件 |
| `exists(blob_path)` | 判断文件存在 |
| `quarantine(blob_path, reason)` | 隔离风险文件 |

第一阶段实现 `LocalFileBlobStore`，路径建议：

```text
storage/uploads/original/
storage/uploads/extracted/
storage/uploads/quarantine/
storage/parsed/
```

后续可替换为 MinIO/S3，但 Protocol 不应绑定本地文件系统。

### 7.5 `ArchiveExtractorProtocol`

| 方法 | 语义 |
|---|---|
| `can_extract(filename, content_type)` | 判断是否支持解包 |
| `extract(blob, output_dir, limits)` | 安全解包并返回子文件列表 |

必须支持 zip；tar/tar.gz 可作为第二优先级。必须防 zip slip。

### 7.6 `DocumentParserProtocol`

| 方法 | 语义 |
|---|---|
| `detect(blob)` | 返回文件类型和解析策略 |
| `parse(blob)` | 返回标准化 Markdown/text、metadata、warnings |

第一阶段至少定义接口和 TXT/MD/HTML 解析；PDF/DOCX 可先预留实现位，后续接入 `pypdf`、`python-docx` 或专门解析服务。

### 7.7 `RedisStateStoreProtocol`

统一 Redis：

- 锁。
- 幂等键。
- JSON cache。
- Hash task status。
- Stream task events。
- 简单限流。

### 7.8 `TaskRunStoreProtocol`

统一任务历史：

- task run。
- stage。
- event。
- retry/error/result。

---

## 8. 数据库 Schema 改造计划

由于现有数据可以清空，建议新增一次面向新架构的 migration，并允许 reset 后重建：

```text
migrations/004_infrastructure_foundation.sql
```

也可以拆成：

```text
migrations/004_task_runs.sql
migrations/005_document_upload_foundation.sql
```

如果选择拆分，仍不做旧数据迁移。

### 8.1 `task_runs/task_stages/task_events`

保留原计划设计，用于 Pipeline、上传解析、向量化、报告生成等所有异步任务。

### 8.2 `upload_batches`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PRIMARY KEY | 上传批次 |
| `source` | TEXT | `frontend/api/system` |
| `status` | TEXT | `received/processing/succeeded/partial_failed/failed/cancelled` |
| `file_count` | INT | 原始文件数 |
| `expanded_file_count` | INT | 解包后文件数 |
| `total_size_bytes` | BIGINT | 总大小 |
| `metadata` | JSONB | 上传上下文，如目标竞品/产品 |
| `error` | JSONB | 批次错误 |
| `created_at/updated_at/finished_at` | TIMESTAMPTZ | 时间 |

### 8.3 `document_blobs`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PRIMARY KEY | 文件对象 ID |
| `upload_batch_id` | UUID | 批次 |
| `parent_blob_id` | UUID NULL | 压缩包内文件指向原压缩包 |
| `original_filename` | TEXT | 原始文件名 |
| `safe_filename` | TEXT | 安全文件名 |
| `content_type` | TEXT | MIME |
| `file_ext` | TEXT | 扩展名 |
| `size_bytes` | BIGINT | 大小 |
| `sha256` | TEXT | 内容 hash |
| `storage_path` | TEXT | 文件存储路径 |
| `status` | TEXT | `stored/extracted/rejected/parsed/failed/quarantined` |
| `error` | JSONB | 错误 |
| `created_at/updated_at` | TIMESTAMPTZ | 时间 |

索引：

- `(sha256)`
- `(upload_batch_id)`
- `(parent_blob_id)`
- `(status, created_at DESC)`

### 8.4 `source_documents`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PRIMARY KEY | 文档 ID |
| `blob_id` | UUID NULL | 上传文件来源 |
| `url` | TEXT | 网页/RSS 来源 URL，可为空 |
| `canonical_url` | TEXT | 标准化 URL |
| `source_type` | TEXT | `rss/web/upload/manual/api` |
| `document_type` | TEXT | `article/product_doc/competitor_doc/report/other` |
| `title` | TEXT | 标题 |
| `content_hash` | TEXT | 标准化正文 hash |
| `language` | TEXT | 语言 |
| `metadata` | JSONB | 来源、作者、文件页数等 |
| `competitor_ids` | JSONB | 预关联竞品 |
| `product_ids` | JSONB | 预关联产品 |
| `parse_status` | TEXT | `pending/parsed/chunked/vectorized/failed` |
| `parse_error` | JSONB | 解析错误 |
| `published_at` | TIMESTAMPTZ | 外部发布时间 |
| `created_at/updated_at` | TIMESTAMPTZ | 时间 |

索引：

- `(source_type, created_at DESC)`
- `(document_type, created_at DESC)`
- `(content_hash)`
- `(parse_status)`
- GIN `metadata`

### 8.5 `document_chunks`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PRIMARY KEY | chunk ID |
| `document_id` | UUID | 所属文档 |
| `chunk_index` | INT | 顺序 |
| `parent_chunk_id` | UUID NULL | 父子分块预留 |
| `heading_path` | JSONB | Markdown 标题路径 |
| `content` | TEXT | chunk 文本权威内容 |
| `token_count` | INT | token 数 |
| `content_hash` | TEXT | 文本 hash |
| `search_vector` | TSVECTOR | 关键词检索 |
| `vector_status` | TEXT | `pending/vectorized/failed/deleted` |
| `vector_point_id` | TEXT | Qdrant point id |
| `created_at/updated_at` | TIMESTAMPTZ | 时间 |

索引：

- `(document_id, chunk_index)`
- `(vector_status)`
- GIN `search_vector`

注意：`document_chunks` 保存文本和关键词索引，Qdrant 保存向量。不再使用 `child_chunks.embedding`。

### 8.6 可删除旧表

由于可清空数据，第一阶段 reset 后不需要保留：

- `parent_chunks`
- `child_chunks`
- 旧 `articles` 可删除或重建为兼容 view/临时适配表

如果短期 API 仍依赖 `articles`，可以保留一个兼容视图或适配 Store，但新 Pipeline 应写 `source_documents`。

---

## 9. Qdrant 改造计划

### 9.1 Docker Compose

本地基础设施应从：

```text
PostgreSQL(pgvector) + Redis
```

改为：

```text
PostgreSQL + Qdrant + Redis
```

建议：

- PostgreSQL 使用官方 `postgres:16`，不再依赖 `pgvector/pgvector:pg16`。
- 新增 Qdrant 服务，暴露 `6333` REST 和可选 `6334` gRPC。
- 新增 `qdrant_data` volume。
- 生产 compose 同步调整。

### 9.2 Python 依赖

新增：

```text
qdrant-client
```

删除或停止依赖：

- PostgreSQL pgvector 扩展相关代码。
- 任何直接写 embedding 到 PostgreSQL vector 列的逻辑。

### 9.3 Config

`core/config.py` 新增：

| 配置 | 默认 |
|---|---|
| `qdrant_url` | `http://localhost:6333` |
| `qdrant_api_key` | 空 |
| `qdrant_documents_collection` | `insightforge_documents_v1` |
| `qdrant_distance` | `Cosine` |
| `vector_backend` | `qdrant` |

保留 `embedding_vector_size`，它决定 Qdrant collection vector size。

### 9.4 Qdrant 写入策略

- point id 使用 `document_chunks.id`，保证 PostgreSQL 与 Qdrant 一一对应。
- payload 冗余保存检索过滤需要的字段，不保存长正文。
- 批量 upsert，失败后记录失败 chunk 并支持重试。
- 删除文档时先标记 PostgreSQL `deleted`，再删除 Qdrant points；Qdrant 删除失败则进入 retry。
- 提供 `rebuild_collection_from_postgres()` 运维能力：清空 collection，按 `document_chunks` 重建向量索引。

---

## 10. Redis 改造计划

Redis 仍定位为执行期状态层。

### 10.1 Key 命名

| 场景 | Key |
|---|---|
| pipeline 全局锁 | `logos:lock:pipeline` |
| 上传批次锁 | `logos:lock:upload:{batch_id}` |
| 文档解析锁 | `logos:lock:document_parse:{document_id}` |
| 向量化锁 | `logos:lock:vectorize:{document_id}` |
| 报告生成锁 | `logos:lock:report:{dedupe_hash}` |
| 任务热状态 | `logos:task:{run_id}` |
| 任务事件流 | `logos:task_events:{run_id}` |
| 文件 hash 幂等 | `logos:idempotency:file:{sha256}` |
| 文档解析缓存 | `logos:cache:parse:{sha256}:{parser_version}` |
| Embedding 缓存 | `logos:cache:embed:{text_hash}:{model}` |
| Web 搜索缓存 | `logos:cache:web_search:{query_hash}` |

### 10.2 降级

Redis 不可用时：

- 上传、解析、向量化仍可执行。
- 分布式锁降级为不可用告警；对必须互斥的任务，调用方可选择失败而不是无锁执行。
- 任务热状态和实时事件丢失，但 PostgreSQL `task_events` 必须完整记录。

---

## 11. 文件上传基础设施计划

### 11.1 支持范围

第一阶段基础设施预留支持：

| 类型 | 第一阶段策略 |
|---|---|
| `.txt` | 直接解析 |
| `.md/.markdown` | 直接解析 |
| `.html/.htm` | 复用 HTML -> Markdown |
| `.pdf` | 预留 parser，可先标记 unsupported 或接入轻量解析 |
| `.docx` | 预留 parser，可先标记 unsupported 或接入轻量解析 |
| `.csv/.tsv` | 预留表格文本化 |
| `.zip` | 必须支持安全解包 |
| `.tar/.tar.gz` | 可选 |

### 11.2 安全限制

基础设施配置项：

| 配置 | 建议默认 |
|---|---|
| `upload_max_file_size_mb` | 50 |
| `upload_max_batch_size_mb` | 200 |
| `upload_max_archive_files` | 200 |
| `upload_max_archive_unpacked_mb` | 500 |
| `upload_allowed_extensions` | txt,md,html,pdf,docx,csv,tsv,zip |

必须拒绝：

- 路径穿越。
- 绝对路径。
- 解包后超限。
- 可执行文件。
- 空文件。

### 11.3 文档摄入任务阶段

上传/解包/解析/向量化建议使用统一任务阶段：

```text
receive_upload
  -> validate_files
  -> store_blobs
  -> extract_archives
  -> parse_documents
  -> chunk_documents
  -> embed_chunks
  -> upsert_qdrant
  -> mark_vectorized
```

每个阶段写入 `task_stages` 和 `task_events`。

---

## 12. 旧基础设施删除与替换计划

### 12.1 必须删除或废弃

| 旧内容 | 处理 | 原因 |
|---|---|---|
| `infrastructure/pgvector_store.py` | 删除 | 向量库改为 Qdrant |
| `PgVectorStore` | 删除 | 不再作为 VectorStore 实现 |
| `child_chunks` 表中的 embedding 设计 | 删除 | 向量进入 Qdrant |
| `parent_chunks` / `child_chunks` 旧 schema | 删除或重建为 `document_chunks` | 新文档模型统一 chunk |
| `pgvector/pgvector:pg16` 镜像 | 替换为 `postgres:16` + `qdrant` | 职责拆分 |
| `test_pgvector_store.py` | 删除或改写为 `test_qdrant_vector_index.py` | 测试目标变化 |
| `VectorStoreProtocol` 的 pgvector 语义 | 重定义为 `VectorIndexProtocol` | 不再绑定数据库向量表 |

### 12.2 需要重写

| 旧内容 | 新方向 |
|---|---|
| `infrastructure/hybrid_search_service.py` | 改为 Qdrant semantic + PostgreSQL keyword RRF |
| `infrastructure/keyword_search_service.py` | 改为查询 `document_chunks.search_vector` |
| `services/pipeline_service.py` 中向量化写入 | 改为保存 document chunks 后 upsert Qdrant |
| `core/factory.py:create_vector_store` | 改为 `create_vector_index` |
| `core/config.py` pgvector 相关注释/配置 | 改为 Qdrant 配置 |
| `ARCHITECTURE.md` 和 Protocol 文档 | 改为 PostgreSQL + Qdrant |

### 12.3 可保留但应改名或泛化

| 旧内容 | 处理 |
|---|---|
| `collector.py` | 保留能力，后续改名为 RSS/source collector |
| `web_crawler.py` | 保留，作为 web source collector |
| `markdown_converter.py` | 保留并泛化为 HTML 文档解析器的一部分 |
| `chunking_service.py` | 保留，但输入输出改为 `SourceDocument/DocumentChunk` |
| `embedding_client.py` | 保留，Qdrant upsert 前仍需要 embedding |
| `rerank_client.py` | 保留，可用于 Qdrant + keyword 召回后的精排 |
| `competitor_store.py` | 保留，后续接入上传文档关联 |
| `report_store.py` | 保留，后续质量门禁扩展 |

### 12.4 可短期兼容

如果前端或 API 暂时仍依赖 `Article`：

- 可以用 `SourceDocument` 适配出 article-like DTO。
- 可以短期保留 `models/article.py` 的兼容别名。
- 不允许新逻辑继续写旧 `articles` 作为主表。

---

## 13. Factory 与 ConfigManager 改造

### 13.1 新增工厂函数

| 函数 | 返回 |
|---|---|
| `create_postgres_provider(config)` | `PostgresConnectionProviderProtocol` |
| `create_redis_state_store(config)` | `RedisStateStoreProtocol` |
| `create_qdrant_vector_index(config)` | `VectorIndexProtocol` |
| `create_task_run_store(provider)` | `TaskRunStoreProtocol` |
| `create_document_store(provider)` | `DocumentStoreProtocol` |
| `create_upload_store(provider)` | `UploadStoreProtocol` |
| `create_file_blob_store(config)` | `FileBlobStoreProtocol` |
| `create_archive_extractor(config)` | `ArchiveExtractorProtocol` |
| `create_document_parser(config)` | `DocumentParserProtocol` |

### 13.2 ConfigManager 缓存

`ConfigManager` 应缓存：

- `postgres_provider`
- `redis_state_store`
- `vector_index`
- `task_run_store`
- `document_store`
- `upload_store`
- `file_blob_store`
- `document_parser`

配置 reload 规则：

- PostgreSQL DSN 变化，清空依赖 PostgreSQL 的 Store。
- Qdrant URL/API key/collection/vector size 变化，清空 vector index。
- Redis URL 变化，清空 state store。
- 上传路径/限制变化，清空 file blob store 和 extractor。
- LLM/Embedding 变化不应重建 PostgreSQL/Redis/Qdrant Store，但会影响后续 embedding 任务。

---

## 14. 实施步骤

### Step 1：冻结新基础设施契约

产物：

- 新增/重定义 `VectorIndexProtocol`、`DocumentStoreProtocol`、`UploadStoreProtocol`、`FileBlobStoreProtocol`、`ArchiveExtractorProtocol`、`DocumentParserProtocol`、`RedisStateStoreProtocol`、`TaskRunStoreProtocol`。
- 明确 `VectorStoreProtocol/PgVectorStore` 废弃。
- 明确 `ArticleStore` 不再承载新文档摄入。

验收：

- Protocol 不泄露 Qdrant、Redis、psycopg2 具体类型。
- 新上传文件和网页/RSS 来源都能映射到 `SourceDocument`。

### Step 2：调整基础设施依赖与 Compose

产物：

- `docker-compose.yml` 增加 Qdrant，PostgreSQL 改官方镜像。
- `docker-compose.prod.yml` 同步调整。
- `requirements.txt` 增加 `qdrant-client`。
- `core/config.py` 增加 Qdrant 和上传限制配置。

验收：

- `docker compose up -d` 后 PostgreSQL、Redis、Qdrant 均健康。
- 应用启动能检查 Qdrant collection。

### Step 3：新增 PostgreSQL 基础 schema

产物：

- `migrations/004_infrastructure_foundation.sql` 或拆分 migration。
- 新增 `task_runs/task_stages/task_events`。
- 新增 `upload_batches/document_blobs/source_documents/document_chunks`。
- 删除或不再创建旧 `parent_chunks/child_chunks`。

验收：

- 可在空库重复执行 migration。
- 不要求旧数据迁移。
- 表、索引、注释完整。

### Step 4：实现 QdrantVectorIndex

产物：

- `infrastructure/qdrant/vector_index.py`
- `tests/test_qdrant_vector_index.py`

验收：

- ensure/recreate collection 成功。
- upsert/search/delete 成功。
- payload filter 能按 document_id、competitor_ids、document_type 过滤。
- Qdrant 不可用时抛出统一基础设施异常。

### Step 5：实现任务和 Redis 底座

产物：

- `models/task_run.py`
- `infrastructure/task_run_store.py`
- `infrastructure/redis/state_store.py`

验收：

- 任务 run/stage/event 可写可查。
- Redis 锁 owner 校验释放正确。
- Redis 不可用时可降级。

### Step 6：实现上传文件底座

产物：

- `models/file_asset.py`
- `infrastructure/files/blob_store.py`
- `infrastructure/files/archive_extractor.py`
- `infrastructure/files/type_detector.py`
- `infrastructure/stores/upload_store.py`

验收：

- 文件按 hash 保存。
- zip 安全解包，防路径穿越。
- 超限文件被拒绝并记录原因。
- 同一 sha256 可识别重复。

### Step 7：实现文档存储、解析与分块底座

产物：

- `models/document.py`
- `infrastructure/stores/document_store.py`
- `infrastructure/parsers/document_parser.py`
- `chunking_service.py` 适配 `SourceDocument`。

验收：

- TXT/MD/HTML 可解析为标准化内容。
- 文档可保存为 `source_documents`。
- chunk 文本写入 `document_chunks`。
- `document_chunks.search_vector` 可用于关键词检索。

### Step 8：改造混合检索

产物：

- `hybrid_search_service.py` 改为 Qdrant semantic + PostgreSQL keyword + RRF。
- `keyword_search_service.py` 改为查询 `document_chunks`。

验收：

- 语义检索来自 Qdrant。
- 关键词检索来自 PostgreSQL。
- 任一通道失败可降级到另一通道。

### Step 9：接入 Scheduler 验证

产物：

- Pipeline、上传解析、向量化任务写入 `task_runs/task_stages/task_events`。
- Redis 锁保护 pipeline、上传批次和文档向量化。

验收：

- 手动触发 pipeline 或上传处理任务后，可查询完整任务历史。
- Qdrant 中存在对应 points。
- PostgreSQL chunk 与 Qdrant point 一一对应。

### Step 10：删除旧基础设施

产物：

- 删除 `infrastructure/pgvector_store.py`。
- 删除或改写 pgvector 测试。
- 移除 pgvector docker 镜像。
- 移除 `create_vector_store` 或改名为 `create_vector_index`。
- 文档更新为 PostgreSQL + Qdrant + Redis + File Storage。

验收：

- `rg "pgvector|PgVector|child_chunks|parent_chunks"` 仅剩历史文档或明确废弃说明。
- 核心测试通过。

---

## 15. 测试计划

### 15.1 单元测试

| 模块 | 测试重点 |
|---|---|
| `QdrantVectorIndex` | collection、upsert、search、delete、filter |
| `PostgresTaskRunStore` | run/stage/event、JSONB、错误记录 |
| `RedisStateStore` | 锁、缓存、Hash、Stream、限流、降级 |
| `LocalFileBlobStore` | hash 保存、路径安全、删除 |
| `ArchiveExtractor` | zip slip、防超限、部分失败 |
| `DocumentParser` | TXT/MD/HTML 解析和错误 |
| `DocumentStore` | document/chunk 保存、vector_status |

### 15.2 集成测试

| 场景 | 验收 |
|---|---|
| 文档上传摄入 | blob、document、chunks、task history 均落库 |
| 压缩包摄入 | 子文件拆分并独立记录 |
| 文档向量化 | Qdrant points 与 PostgreSQL chunks 对齐 |
| 混合检索 | Qdrant + PostgreSQL keyword RRF 可用 |
| Qdrant 不可用 | 向量阶段失败并可重试，文档元数据不丢 |
| Redis 不可用 | 任务终态仍写 PostgreSQL |
| reset 后重建 | 空库和空 Qdrant 可一键初始化 |

### 15.3 回归测试

优先运行：

```bash
pytest tests/
```

重点替换：

- `test_pgvector_store.py` -> `test_qdrant_vector_index.py`
- `test_hybrid_search.py` 更新为 Qdrant 语义通道。
- `test_pipeline_service.py` 更新为 DocumentStore + Qdrant。

---

## 16. 验收标准

第一阶段完成的硬性标准：

1. 本地和生产 Compose 均包含 PostgreSQL、Redis、Qdrant。
2. PostgreSQL 不再依赖 pgvector 镜像或 vector 列。
3. Qdrant collection 可初始化、清空重建、写入、搜索、删除。
4. 新文档模型 `SourceDocument/DocumentChunk` 可承载网页、RSS 和上传文件。
5. 上传文件、压缩包和解包文件有独立元数据表和文件存储抽象。
6. 任务历史可记录 pipeline、上传解析、向量化阶段。
7. Redis 操作统一通过 `RedisStateStore`。
8. pgvector 旧 Store、测试和 compose 依赖被删除或明确废弃。
9. 现有数据清空后，系统可从空库、空 Qdrant、空 Redis 启动并跑通基础摄入链路。

---

## 17. 风险与处理

| 风险 | 说明 | 处理 |
|---|---|---|
| Qdrant 增加部署复杂度 | 从两组件变三组件 | Compose 和健康检查统一，收益大于复杂度 |
| 双写一致性 | PostgreSQL chunk 与 Qdrant point 可能不一致 | vector_status + 重建 collection 工具 |
| 上传压缩包风险 | 路径穿越、超限、恶意文件 | 安全解包、限制、隔离、拒绝可执行文件 |
| 旧 API 依赖 Article | 前端/工具可能仍查文章 | 短期 DTO 适配，不让新逻辑写旧主表 |
| Qdrant 测试依赖服务 | 单元测试可能需要容器 | 抽象 Protocol，集成测试标记依赖 Qdrant |
| 清库重建误用于生产 | 用户允许当前不保留数据，但生产需谨慎 | reset 脚本必须显式确认环境 |

---

## 18. 推荐落地顺序

1. 重定义 Protocol 和模型：Document、Upload、Task、VectorIndex。
2. 调整 Compose、requirements、config，引入 Qdrant。
3. 新建 PostgreSQL foundation migration，允许空库重建。
4. 实现 `QdrantVectorIndex`。
5. 实现 `TaskRunStore` 与 `RedisStateStore`。
6. 实现文件上传与压缩包基础设施。
7. 实现 `DocumentStore`、解析、分块和 Qdrant upsert。
8. 改造混合检索为 Qdrant + PostgreSQL keyword。
9. 接入 pipeline/upload/vectorize 任务历史。
10. 删除 pgvector 旧实现、旧测试和旧 compose 依赖。

这个顺序先确立新底座，再迁移摄入与检索，最后清理旧实现，避免在旧 pgvector 结构上继续堆出第二套需要重构的基础设施。