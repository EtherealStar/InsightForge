# public.document_blobs

文件对象 metadata 表。文件字节由 FileBlobStore 保存，本表只保存可审计的文件清单、hash、状态和错误。

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PRIMARY KEY | 文件对象 ID |
| `upload_batch_id` | UUID NULL | 所属上传批次 |
| `parent_blob_id` | UUID NULL | 解包子文件指向原压缩包 blob |
| `original_filename` | TEXT | 用户上传或压缩包内的原始文件名 |
| `safe_filename` | TEXT | 清理后的安全文件名 |
| `content_type` | TEXT | MIME 类型或检测结果 |
| `file_ext` | TEXT | 文件扩展名 |
| `size_bytes` | BIGINT | 文件大小 |
| `sha256` | TEXT | 文件内容 hash |
| `storage_path` | TEXT | FileBlobStore 内的存储路径 |
| `status` | TEXT | `stored/extracted/rejected/parsed/failed/quarantined` |
| `error` | JSONB | 文件级错误 |
| `created_at` / `updated_at` | TIMESTAMPTZ | 时间字段 |

## 索引

- `idx_document_blobs_sha256`
- `idx_document_blobs_batch`

## 业务规则

- `sha256` 用于重复识别，不要求唯一。
- 原压缩包和解包子文件都写入本表；子文件通过 `parent_blob_id` 关联原压缩包。
- 解析成功后，`source_documents.blob_id` 指向对应 blob。
- 隔离文件进入 `quarantined`，不得删除 metadata 审计记录。
