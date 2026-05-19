# InsightForge 数据库 Schema

> 当前权威 DDL 来自 `migrations/*.sql`。本目录保留人工同步的 schema 摘要；如重新运行 tbls，应以当前 migration 结果为准。

## 核心表

| 表 | 说明 |
|---|---|
| `source_documents` | 统一来源文档，保存标题、正文、来源、hash、语言、metadata、竞品/产品关联和解析状态 |
| `document_parent_chunks` | 父块权威内容，保存 `content`、`child_point_ids`、heading path、metadata 和 `search_vector` |
| `document_vector_points` | Qdrant point 状态，保存 `point_id`、`parent_chunk_id`、`chunk_index`、hash、token 数和错误信息 |
| `task_runs` | 异步任务运行记录 |
| `task_stages` | 异步任务阶段记录 |
| `task_events` | 异步任务事件记录 |
| `upload_batches` | 上传批次记录 |
| `document_blobs` | 上传或解包文件对象记录 |

## RAG 存储边界

```text
source_documents
  -> document_parent_chunks
       content + child_point_ids + search_vector
  -> document_vector_points
       point_id + parent_chunk_id + vector_status

Qdrant insightforge_documents_v1
  -> child chunk vector
  -> payload.content
  -> payload metadata
```

PostgreSQL 不保存子块 embedding，也不创建新的子块正文表。子块正文和向量均进入 Qdrant，PostgreSQL 只保存父块和 point 状态。
