# 数据库业务规则补充说明

> **表结构文档**由 [tbls](https://github.com/k1LoW/tbls) 自动生成 → [dbdoc/](dbdoc/)
> 本文件仅保留 tbls 无法覆盖的业务规则说明。

---

## ArticleStatus 生命周期

```
stored → pending_summary → summarized → embedded
```

- `stored`：新入库，等待摘要（无摘要服务时直接跳到 `summarized`）
- `pending_summary`：已标记待摘要
- `summarized`：摘要完成，等待向量化
- `embedded`：向量化完成，可被检索

---

## 核心实体关系

```
Article (1) ──→ (N) ParentChunk (父分块, PostgreSQL)
Article (1) ──→ (N) Chunk (子分块, PostgreSQL/pgvector)
Chunk (N)   ──→ (1) ParentChunk (通过 parent_chunk_id)
```

外键约束已配置 `ON DELETE CASCADE`：删除文章时自动级联删除关联的父子 chunks。

---

## 分块策略

| 参数 | 默认值 | 说明 |
|---|---|---|
| `chunk_max_child_tokens` | 512 | 子 chunk 最大 token 数 |
| `chunk_target_parent_tokens` | 1024 | 父 chunk 目标 token 数 |
| `chunk_overlap_tokens` | 100 | 父 chunk 间重叠 token 数 |
| `embedding_vector_size` | 1536 | pgvector 向量维度 |

**关键规则**：
- 子 chunk 按 Markdown 标题结构切分，≤512 token，存入 PostgreSQL `child_chunks` 用于 pgvector 检索
- 父 chunk ~1024 token，完整包含若干子 chunk，存入 PostgreSQL 用于 LLM 召回
- 父 chunk 之间通过共享尾部子 chunk 实现 ~100 token overlap
- 子 chunk 明确归属一个父 chunk（通过 `parent_chunk_id`）
- 短文档 (≤1024 token) 同时视为子 chunk 和父 chunk
- 全文索引：父 chunk 写入时自动使用 `jieba` 分词生成 `search_vector`
- `backfill_search_vectors()` 支持为已有数据回填全文索引

### 存储示意

```
文章 → ChunkingService
         ├── 子 chunks (≤512 tok) ──→ Embedding ──→ PostgreSQL child_chunks
         │                                          embedding + parent_chunk_id
         └── 父 chunks (~1024 tok) ──→ PostgreSQL (parent_chunks)
                                       含 search_vector (jieba tsvector)
```
