# public.document_parent_chunks

## 说明

Parent chunks stored in PostgreSQL for LLM context and FTS.

## 列一览

| 名称              | 类型                       | 默认值             | Nullable | 子表                                                                | 父表                                                    | 备注                                                                    |
| --------------- | ------------------------ | --------------- | -------- | ----------------------------------------------------------------- | ----------------------------------------------------- | --------------------------------------------------------------------- |
| parent_chunk_id | text                     |                 | false    | [public.document_vector_points](public.document_vector_points.md) |                                                       |                                                                       |
| document_id     | uuid                     |                 | false    |                                                                   | [public.source_documents](public.source_documents.md) |                                                                       |
| content         | text                     |                 | false    |                                                                   |                                                       |                                                                       |
| token_count     | integer                  | 0               | false    |                                                                   |                                                       |                                                                       |
| child_point_ids | jsonb                    | '[]'::jsonb     | false    |                                                                   |                                                       | All child point IDs included in this parent chunk, including overlap. |
| heading_path    | jsonb                    | '[]'::jsonb     | false    |                                                                   |                                                       |                                                                       |
| doc_name        | text                     | ''::text        | false    |                                                                   |                                                       |                                                                       |
| source          | text                     | ''::text        | false    |                                                                   |                                                       |                                                                       |
| url             | text                     | ''::text        | false    |                                                                   |                                                       |                                                                       |
| source_type     | text                     | 'web'::text     | false    |                                                                   |                                                       |                                                                       |
| document_type   | text                     | 'article'::text | false    |                                                                   |                                                       |                                                                       |
| competitor_ids  | jsonb                    | '[]'::jsonb     | false    |                                                                   |                                                       |                                                                       |
| product_ids     | jsonb                    | '[]'::jsonb     | false    |                                                                   |                                                       |                                                                       |
| language        | text                     | ''::text        | false    |                                                                   |                                                       |                                                                       |
| published_at    | timestamp with time zone |                 | true     |                                                                   |                                                       |                                                                       |
| metadata        | jsonb                    | '{}'::jsonb     | false    |                                                                   |                                                       |                                                                       |
| search_vector   | tsvector                 |                 | true     |                                                                   |                                                       |                                                                       |
| created_at      | timestamp with time zone | now()           | false    |                                                                   |                                                       |                                                                       |
| updated_at      | timestamp with time zone | now()           | false    |                                                                   |                                                       |                                                                       |

## 约束一览

| 名称                                      | 类型          | 定义                                                                          |
| --------------------------------------- | ----------- | --------------------------------------------------------------------------- |
| document_parent_chunks_document_id_fkey | FOREIGN KEY | FOREIGN KEY (document_id) REFERENCES source_documents(id) ON DELETE CASCADE |
| document_parent_chunks_pkey             | PRIMARY KEY | PRIMARY KEY (parent_chunk_id)                                               |

## 索引一览

| 名称                                  | 定义                                                                                                             |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| document_parent_chunks_pkey         | CREATE UNIQUE INDEX document_parent_chunks_pkey ON public.document_parent_chunks USING btree (parent_chunk_id) |
| idx_document_parent_chunks_document | CREATE INDEX idx_document_parent_chunks_document ON public.document_parent_chunks USING btree (document_id)    |
| idx_document_parent_chunks_fts      | CREATE INDEX idx_document_parent_chunks_fts ON public.document_parent_chunks USING gin (search_vector)         |

## ER 图

```mermaid
erDiagram

"public.document_vector_points" }o--|| "public.document_parent_chunks" : "FOREIGN KEY (parent_chunk_id) REFERENCES document_parent_chunks(parent_chunk_id) ON DELETE CASCADE"
"public.document_parent_chunks" }o--|| "public.source_documents" : "FOREIGN KEY (document_id) REFERENCES source_documents(id) ON DELETE CASCADE"

"public.document_parent_chunks" {
  text parent_chunk_id ""
  uuid document_id FK ""
  text content ""
  integer token_count ""
  jsonb child_point_ids "All child point IDs included in this parent chunk, including overlap."
  jsonb heading_path ""
  text doc_name ""
  text source ""
  text url ""
  text source_type ""
  text document_type ""
  jsonb competitor_ids ""
  jsonb product_ids ""
  text language ""
  timestamp_with_time_zone published_at ""
  jsonb metadata ""
  tsvector search_vector ""
  timestamp_with_time_zone created_at ""
  timestamp_with_time_zone updated_at ""
}
"public.document_vector_points" {
  text point_id "Qdrant point id. Stable UUID derived from document_id and chunk_index."
  uuid document_id FK ""
  text parent_chunk_id FK ""
  integer chunk_index ""
  text content_hash ""
  integer token_count ""
  text vector_status ""
  jsonb error ""
  timestamp_with_time_zone created_at ""
  timestamp_with_time_zone updated_at ""
}
"public.source_documents" {
  uuid id ""
  uuid blob_id FK ""
  text url ""
  text canonical_url ""
  text source_type ""
  text document_type ""
  text title ""
  text content ""
  text content_hash ""
  text language ""
  jsonb metadata ""
  jsonb competitor_ids ""
  jsonb product_ids ""
  text parse_status ""
  jsonb parse_error ""
  timestamp_with_time_zone published_at ""
  timestamp_with_time_zone created_at ""
  timestamp_with_time_zone updated_at ""
  text intel_type "情报类型: pricing/feature/strategy/partnership/hiring/funding/market/review/general"
  double_precision source_reliability "来源可信度 0.0~1.0"
  text analysis_notes "AI 分析批注"
}
```

---

> Generated by [tbls](https://github.com/k1LoW/tbls)
