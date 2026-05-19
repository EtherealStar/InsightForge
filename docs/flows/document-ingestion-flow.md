# 上传文档摄入流程

> 覆盖上传文件和 zip 解包文件进入 `SourceDocument`、父子分块、Qdrant 向量索引的基础链路。

---

## 触发

当前阶段提供 Service/基础设施能力，不要求完整前端上传页面。触发方可以是后续 API、CLI、Celery 任务或测试入口。

Celery 入口：

- `scheduler.tasks.run_upload_batch_task(batch_id, context=None, task_run_id=None)`
- 若调用方传入 `task_run_id`，摄入服务复用该 run；否则任务内部创建 `upload_batch_ingestion` run。

输入：

- 一个或多个文件流。
- 可选上下文：`document_type`、`competitor_ids`、`product_ids`、`language`、metadata。

---

## 执行链路

```text
receive_upload
  -> validate_files
  -> LocalFileBlobStore.put()
  -> PostgresUploadStore.create_batch/save_blob()
  -> scheduler.tasks.run_upload_batch_task(batch_id)
  -> Redis lock logos:lock:upload:{batch_id}
  -> ArchiveExtractor.extract()       # zip only
  -> DocumentParser.parse()
  -> SourceDocument(source_type=upload)
  -> PostgresDocumentStore.save_document()
  -> ChunkingService.chunk_document()
  -> PostgresDocumentStore.save_parent_chunks()
  -> EmbeddingClient.embed()
  -> QdrantVectorIndex.upsert_child_chunks()
  -> PostgresDocumentStore.mark_points_vectorized()
```

`DocumentIngestionService` 编排解析、分块、向量化和状态回写。Redis 锁可使用：

- `logos:lock:upload:{batch_id}`
- `logos:lock:document_parse:{blob_id}`
- `logos:lock:vectorize:{document_id}`

任务历史写入 `task_runs/task_stages/task_events`，阶段覆盖 upload_batch、parse_documents、chunk_documents 和 vectorize_document。Redis 同步 `logos:task:{run_id}` 与 `logos:task_events:{run_id}`；Redis 不可用时，PostgreSQL 任务历史仍是权威记录。

---

## 持久化

| 产物 | 存储 |
|---|---|
| 上传批次 | `upload_batches` |
| 原始文件/解包文件 metadata | `document_blobs` |
| 文件字节 | `storage/uploads/original`、`storage/uploads/extracted`、`storage/uploads/quarantine` |
| 标准化文档 | `source_documents` |
| 父块上下文和 FTS | `document_parent_chunks` |
| Qdrant point 状态 | `document_vector_points` |
| 子块向量和 payload | Qdrant `insightforge_documents_v1` |

---

## 失败处理

- 空文件、可执行文件、未知高风险类型、超限文件进入 rejected/failed。
- zip slip、绝对路径、超文件数、超单文件大小、超解包总大小会拒绝解包。
- 单个文件解析失败写入 `document_blobs.error`，同批次其他文件继续处理。
- 批次最终状态为 `succeeded`、`partial_failed` 或 `failed`，并写入任务 run result。
- PDF/DOCX 当前返回 unsupported，不生成 `SourceDocument`。
- Embedding 或 Qdrant upsert 失败时，`source_documents.parse_status=failed`，已知 point 写入 `document_vector_points.vector_status=failed`，任务事件记录 `embed`、`qdrant_upsert` 或失败原因。

---

## 输出

成功摄入后，上传文档与 RSS/Web 文章共用同一检索链路：

```text
HybridSearchService
  -> Qdrant child semantic search
  -> PostgreSQL parent FTS
  -> RRF/rerank
  -> parent chunk context
```
