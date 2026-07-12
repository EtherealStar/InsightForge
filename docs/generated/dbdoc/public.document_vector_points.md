# public.document_vector_points

## 说明

Qdrant child chunk point status; embeddings and child payloads live in Qdrant.

## 列一览

| 名称              | 类型                       | 默认值             | Nullable | 父表                                                                | 备注                                                                     |
| --------------- | ------------------------ | --------------- | -------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------- |
| point_id        | text                     |                 | false    |                                                                   | Qdrant point id. Stable UUID derived from document_id and chunk_index. |
| document_id     | uuid                     |                 | false    | [public.source_documents](public.source_documents.md)             |                                                                        |
| parent_chunk_id | text                     |                 | false    | [public.document_parent_chunks](public.document_parent_chunks.md) |                                                                        |
| chunk_index     | integer                  | 0               | false    |                                                                   |                                                                        |
| content_hash    | text                     | ''::text        | false    |                                                                   |                                                                        |
| token_count     | integer                  | 0               | false    |                                                                   |                                                                        |
| vector_status   | text                     | 'pending'::text | false    |                                                                   |                                                                        |
| error           | jsonb                    | '{}'::jsonb     | false    |                                                                   |                                                                        |
| created_at      | timestamp with time zone | now()           | false    |                                                                   |                                                                        |
| updated_at      | timestamp with time zone | now()           | false    |                                                                   |                                                                        |

## 约束一览

| 名称                                          | 类型          | 定义                                                                                                 |
| ------------------------------------------- | ----------- | -------------------------------------------------------------------------------------------------- |
| document_vector_points_document_id_fkey     | FOREIGN KEY | FOREIGN KEY (document_id) REFERENCES source_documents(id) ON DELETE CASCADE                        |
| document_vector_points_parent_chunk_id_fkey | FOREIGN KEY | FOREIGN KEY (parent_chunk_id) REFERENCES document_parent_chunks(parent_chunk_id) ON DELETE CASCADE |
| document_vector_points_pkey                 | PRIMARY KEY | PRIMARY KEY (point_id)                                                                             |

## 索引一览

| 名称                                  | 定义                                                                                                            |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| document_vector_points_pkey         | CREATE UNIQUE INDEX document_vector_points_pkey ON public.document_vector_points USING btree (point_id)       |
| idx_document_vector_points_document | CREATE INDEX idx_document_vector_points_document ON public.document_vector_points USING btree (document_id)   |
| idx_document_vector_points_parent   | CREATE INDEX idx_document_vector_points_parent ON public.document_vector_points USING btree (parent_chunk_id) |
| idx_document_vector_points_status   | CREATE INDEX idx_document_vector_points_status ON public.document_vector_points USING btree (vector_status)   |

## ER 图

```mermaid
erDiagram

"public.document_vector_points" }o--|| "public.source_documents" : "FOREIGN KEY (document_id) REFERENCES source_documents(id) ON DELETE CASCADE"
"public.document_vector_points" }o--|| "public.document_parent_chunks" : "FOREIGN KEY (parent_chunk_id) REFERENCES document_parent_chunks(parent_chunk_id) ON DELETE CASCADE"

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
```

---

> Generated by [tbls](https://github.com/k1LoW/tbls)
