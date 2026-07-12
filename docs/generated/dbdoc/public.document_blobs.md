# public.document_blobs

## 列一览

| 名称                | 类型                       | 默认值            | Nullable | 子表                                                                                                      | 父表                                                | 备注   |
| ----------------- | ------------------------ | -------------- | -------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------- | ---- |
| id                | uuid                     |                | false    | [public.document_blobs](public.document_blobs.md) [public.source_documents](public.source_documents.md) |                                                   |      |
| upload_batch_id   | uuid                     |                | true     |                                                                                                         | [public.upload_batches](public.upload_batches.md) |      |
| parent_blob_id    | uuid                     |                | true     |                                                                                                         | [public.document_blobs](public.document_blobs.md) |      |
| original_filename | text                     |                | false    |                                                                                                         |                                                   |      |
| safe_filename     | text                     |                | false    |                                                                                                         |                                                   |      |
| content_type      | text                     | ''::text       | false    |                                                                                                         |                                                   |      |
| file_ext          | text                     | ''::text       | false    |                                                                                                         |                                                   |      |
| size_bytes        | bigint                   | 0              | false    |                                                                                                         |                                                   |      |
| sha256            | text                     |                | false    |                                                                                                         |                                                   |      |
| storage_path      | text                     |                | false    |                                                                                                         |                                                   |      |
| status            | text                     | 'stored'::text | false    |                                                                                                         |                                                   |      |
| error             | jsonb                    | '{}'::jsonb    | false    |                                                                                                         |                                                   |      |
| created_at        | timestamp with time zone | now()          | false    |                                                                                                         |                                                   |      |
| updated_at        | timestamp with time zone | now()          | false    |                                                                                                         |                                                   |      |

## 约束一览

| 名称                                  | 类型          | 定义                                                                             |
| ----------------------------------- | ----------- | ------------------------------------------------------------------------------ |
| document_blobs_upload_batch_id_fkey | FOREIGN KEY | FOREIGN KEY (upload_batch_id) REFERENCES upload_batches(id) ON DELETE SET NULL |
| document_blobs_parent_blob_id_fkey  | FOREIGN KEY | FOREIGN KEY (parent_blob_id) REFERENCES document_blobs(id) ON DELETE SET NULL  |
| document_blobs_pkey                 | PRIMARY KEY | PRIMARY KEY (id)                                                               |

## 索引一览

| 名称                        | 定义                                                                                           |
| ------------------------- | -------------------------------------------------------------------------------------------- |
| document_blobs_pkey       | CREATE UNIQUE INDEX document_blobs_pkey ON public.document_blobs USING btree (id)            |
| idx_document_blobs_sha256 | CREATE INDEX idx_document_blobs_sha256 ON public.document_blobs USING btree (sha256)         |
| idx_document_blobs_batch  | CREATE INDEX idx_document_blobs_batch ON public.document_blobs USING btree (upload_batch_id) |

## ER 图

```mermaid
erDiagram

"public.document_blobs" }o--o| "public.document_blobs" : "FOREIGN KEY (parent_blob_id) REFERENCES document_blobs(id) ON DELETE SET NULL"
"public.source_documents" }o--o| "public.document_blobs" : "FOREIGN KEY (blob_id) REFERENCES document_blobs(id) ON DELETE SET NULL"
"public.document_blobs" }o--o| "public.upload_batches" : "FOREIGN KEY (upload_batch_id) REFERENCES upload_batches(id) ON DELETE SET NULL"

"public.document_blobs" {
  uuid id ""
  uuid upload_batch_id FK ""
  uuid parent_blob_id FK ""
  text original_filename ""
  text safe_filename ""
  text content_type ""
  text file_ext ""
  bigint size_bytes ""
  text sha256 ""
  text storage_path ""
  text status ""
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
"public.upload_batches" {
  uuid id ""
  text source ""
  text status ""
  integer file_count ""
  integer expanded_file_count ""
  bigint total_size_bytes ""
  jsonb metadata ""
  jsonb error ""
  timestamp_with_time_zone created_at ""
  timestamp_with_time_zone updated_at ""
  timestamp_with_time_zone finished_at ""
}
```

---

> Generated by [tbls](https://github.com/k1LoW/tbls)
