# public.document_parent_chunks

父块权威内容表。父块用于 LLM 上下文召回和 PostgreSQL 全文搜索。

| 列 | 类型 | 说明 |
|---|---|---|
| `parent_chunk_id` | TEXT PRIMARY KEY | 父块 ID |
| `document_id` | UUID | 所属 `source_documents.id` |
| `content` | TEXT | 父块正文 |
| `token_count` | INT | token 数 |
| `child_point_ids` | JSONB | 该父块包含的 Qdrant point IDs，包含 overlap 关系 |
| `heading_path` | JSONB | Markdown 标题路径 |
| `doc_name` | TEXT | 文档名 |
| `source` | TEXT | 来源名称 |
| `url` | TEXT | 来源 URL |
| `source_type` | TEXT | 来源类型 |
| `document_type` | TEXT | 文档类型 |
| `competitor_ids` | JSONB | 关联竞品 |
| `product_ids` | JSONB | 关联产品 |
| `language` | TEXT | 语言 |
| `published_at` | TIMESTAMPTZ | 外部发布时间 |
| `metadata` | JSONB | metadata |
| `search_vector` | TSVECTOR | 父块全文索引 |
| `created_at` / `updated_at` | TIMESTAMPTZ | 时间字段 |

## 索引

- `idx_document_parent_chunks_document`
- `idx_document_parent_chunks_fts`，GIN on `search_vector`
