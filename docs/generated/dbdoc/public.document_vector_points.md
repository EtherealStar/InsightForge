# public.document_vector_points

Qdrant 子块 point 状态表。该表不保存 embedding，也不保存子块正文。

| 列 | 类型 | 说明 |
|---|---|---|
| `point_id` | TEXT PRIMARY KEY | Qdrant point id，格式 `{document_id}:c:{chunk_index}` |
| `document_id` | UUID | 所属 `source_documents.id` |
| `parent_chunk_id` | TEXT | 主归属父块 |
| `chunk_index` | INT | 子块顺序 |
| `content_hash` | TEXT | 子块正文 hash |
| `token_count` | INT | token 数 |
| `vector_status` | TEXT | `pending/vectorized/failed` |
| `error` | JSONB | Qdrant/embedding 错误 |
| `created_at` / `updated_at` | TIMESTAMPTZ | 时间字段 |

## 索引

- `idx_document_vector_points_document`
- `idx_document_vector_points_parent`
- `idx_document_vector_points_status`
