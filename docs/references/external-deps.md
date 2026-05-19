# 外部依赖配置

本文件记录基础设施和解析链路依赖的外部服务或第三方库。当前上传文档摄入底座未新增运行时服务。

---

## 上传文档解析

| 能力 | 依赖 | 说明 |
|---|---|---|
| TXT/MD/CSV/TSV 解析 | Python 标准库 | 读取文本、CSV/TSV 转 Markdown 表格 |
| HTML -> Markdown | 既有 `NewsMarkdownConverter` 依赖 | 复用 `beautifulsoup4`、`markdownify`、`trafilatura` 等现有项目依赖 |
| zip 解包 | Python 标准库 `zipfile` | 带路径穿越和大小限制校验 |
| PDF/DOCX | 暂无 | 当前仅识别为 unsupported，后续接入解析库或专门解析服务 |

---

## 基础设施服务

| 服务 | 用途 |
|---|---|
| PostgreSQL | `upload_batches`、`document_blobs`、`source_documents`、父块、任务历史 |
| Qdrant | 子块向量和 payload 检索 |
| Redis | 上传/解析/向量化锁、任务热状态、事件 stream 和短期幂等 |

上传文件字节当前保存在本地 `storage/`，后续如替换为 MinIO/S3，需要实现 `FileBlobStoreProtocol`，不影响上层服务。
