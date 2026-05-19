# public.upload_batches

上传批次表。一次上传可能包含多个原始文件，也可能包含压缩包解出的多个子文件。

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PRIMARY KEY | 上传批次 ID |
| `source` | TEXT | 来源，常见值为 `frontend/api/system` |
| `status` | TEXT | `received/processing/succeeded/partial_failed/failed/cancelled` |
| `file_count` | INT | 原始文件数 |
| `expanded_file_count` | INT | 解包后文件数 |
| `total_size_bytes` | BIGINT | 原始上传总大小 |
| `metadata` | JSONB | 上传上下文，如目标竞品、产品线、文档类型 |
| `error` | JSONB | 批次级错误 |
| `created_at` / `updated_at` / `finished_at` | TIMESTAMPTZ | 时间字段 |

## 索引

- `idx_task_runs_status_created` 不适用于本表；当前批次查询主要通过主键和关联 `document_blobs.upload_batch_id` 完成。

## 业务规则

- 批次内单个文件失败时，批次可进入 `partial_failed`。
- 批次终态不代表所有文件都生成了 `SourceDocument`；unsupported 文件会记录在 `document_blobs.error`。
