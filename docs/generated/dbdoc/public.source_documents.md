# public.source_documents

统一来源文档表。用于 RSS、网页、上传、手工和 API 输入。

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PRIMARY KEY | 文档 ID |
| `blob_id` | UUID NULL | 上传文件来源 |
| `url` | TEXT | 来源 URL |
| `canonical_url` | TEXT | 规范 URL |
| `source_type` | TEXT | `rss/web/upload/manual/api` |
| `document_type` | TEXT | `article/product_doc/competitor_doc/report/other` |
| `title` | TEXT | 标题 |
| `content` | TEXT | 标准化正文 |
| `content_hash` | TEXT | 正文 hash |
| `language` | TEXT | 语言 |
| `metadata` | JSONB | 来源 metadata |
| `competitor_ids` | JSONB | 关联竞品 |
| `product_ids` | JSONB | 关联产品 |
| `parse_status` | TEXT | 解析/分块/向量化状态 |
| `parse_error` | JSONB | 错误信息 |
| `published_at` | TIMESTAMPTZ | 外部发布时间 |
| `created_at` / `updated_at` | TIMESTAMPTZ | 时间字段 |

## 索引

- `idx_source_documents_source_created`
- `idx_source_documents_type_created`
- `idx_source_documents_hash`
- `idx_source_documents_parse_status`
- `idx_source_documents_metadata`
