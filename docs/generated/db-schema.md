# 数据库 Schema 文档

> **来源**：从 [ARCHITECTURE.md](../../ARCHITECTURE.md) §12 迁出的完整数据库 Schema。
> **生成方式**：手动维护，与代码实现同步更新。

---

## PostgreSQL articles 表

```sql
CREATE TABLE IF NOT EXISTS articles (
    id           SERIAL PRIMARY KEY,
    url_hash     TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    content      TEXT,
    html_content TEXT,
    summary      TEXT,
    source       TEXT,
    author       TEXT DEFAULT '',
    language     TEXT,
    published_at TIMESTAMP,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status       TEXT DEFAULT 'stored',
    tags         JSONB DEFAULT '[]'::jsonb
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_status ON articles(status);
CREATE INDEX IF NOT EXISTS idx_created_at ON articles(created_at);
CREATE INDEX IF NOT EXISTS idx_source ON articles(source);
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | SERIAL | 自增主键 |
| `url_hash` | TEXT UNIQUE | SHA256(url)，用于去重 |
| `title` | TEXT | 文章标题 |
| `url` | TEXT | 原始 URL |
| `content` | TEXT | Markdown 格式正文 |
| `html_content` | TEXT | 原始 HTML（抓取阶段使用，后续清空） |
| `summary` | TEXT | AI 生成的摘要 |
| `source` | TEXT | 新闻来源名称 |
| `author` | TEXT | 作者 |
| `language` | TEXT | 语言 (`en` / `zh` / `unknown`) |
| `published_at` | TIMESTAMP | 发布时间 |
| `created_at` | TIMESTAMP | 入库时间 |
| `status` | TEXT | 生命周期状态 |
| `tags` | JSONB | AI 生成的标签数组 |

### ArticleStatus 生命周期

```
stored → pending_summary → summarized → embedded
```

- `stored`：新入库，等待摘要（无摘要服务时直接跳到 `summarized`）
- `pending_summary`：已标记待摘要
- `summarized`：摘要完成，等待向量化
- `embedded`：向量化完成，可被检索

---

## PostgreSQL parent_chunks 表

```sql
CREATE TABLE IF NOT EXISTS parent_chunks (
    parent_chunk_id TEXT PRIMARY KEY,
    article_id      INTEGER NOT NULL,
    content         TEXT NOT NULL,
    token_count     INTEGER NOT NULL DEFAULT 0,
    child_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    doc_name        TEXT NOT NULL DEFAULT '',
    source          TEXT DEFAULT '',
    url             TEXT DEFAULT '',
    search_vector   tsvector,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_parent_chunks_article_id ON parent_chunks(article_id);
CREATE INDEX IF NOT EXISTS idx_parent_chunks_fts ON parent_chunks USING GIN(search_vector);
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `parent_chunk_id` | TEXT PK | 格式: `"{article_id}_p{index}"` |
| `article_id` | INTEGER | 所属文章 ID |
| `content` | TEXT | 父 chunk 完整文本 (~1024 token) |
| `token_count` | INTEGER | tiktoken 计算的 token 数 |
| `child_chunk_ids` | JSONB | 包含的子 chunk ID 数组 |
| `doc_name` | TEXT | 文档名 |
| `source` | TEXT | 新闻来源 |
| `url` | TEXT | 文章 URL |
| `search_vector` | tsvector | jieba 分词后的全文索引向量 |
| `created_at` | TIMESTAMP | 创建时间 |

---

## PostgreSQL child_chunks 表 (pgvector)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS child_chunks (
    chunk_id        TEXT PRIMARY KEY,
    article_id      INTEGER NOT NULL,
    parent_chunk_id TEXT NOT NULL,
    content         TEXT NOT NULL,
    token_count     INTEGER NOT NULL DEFAULT 0,
    doc_name        TEXT NOT NULL DEFAULT '',
    heading_path    JSONB NOT NULL DEFAULT '[]'::jsonb,
    chunk_index     INTEGER NOT NULL DEFAULT 0,
    source          TEXT DEFAULT '',
    url             TEXT DEFAULT '',
    embedding       vector(1536) NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_child_chunks_article_id
    ON child_chunks(article_id);
CREATE INDEX IF NOT EXISTS idx_child_chunks_parent_chunk_id
    ON child_chunks(parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_child_chunks_embedding_hnsw
    ON child_chunks USING hnsw (embedding vector_cosine_ops);
```

> `embedding` 维度由 `EMBEDDING_VECTOR_SIZE` 配置控制，默认 `1536`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `chunk_id` | TEXT PK | 子 chunk 唯一 ID，格式: `"{article_id}_c{index}"` |
| `article_id` | INTEGER | 所属文章 ID |
| `parent_chunk_id` | TEXT | 所属父 chunk ID，格式: `"{article_id}_p{index}"` |
| `content` | TEXT | 子 chunk 原文 |
| `token_count` | INTEGER | tiktoken 计算的 token 数 |
| `doc_name` | TEXT | 文档名 |
| `heading_path` | JSONB | 标题层级路径 |
| `chunk_index` | INTEGER | 在文章内的序号 |
| `source` | TEXT | 新闻来源 |
| `url` | TEXT | 文章 URL |
| `embedding` | vector(n) | 子 chunk embedding 向量 |
| `created_at` | TIMESTAMP | 创建时间 |

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
