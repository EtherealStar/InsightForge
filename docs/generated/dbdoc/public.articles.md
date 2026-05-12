# public.articles

## 说明

文章元数据 + 全文存储。Pipeline 采集的新闻文章，经历 stored → pending_summary → summarized → embedded 生命周期。

## 列一览

| 名称           | 类型                          | 默认值                                  | Nullable | 子表                                                                                            | 备注                                                                |
| ------------ | --------------------------- | ------------------------------------ | -------- | --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| id           | integer                     | nextval('articles_id_seq'::regclass) | false    | [public.parent_chunks](public.parent_chunks.md) [public.child_chunks](public.child_chunks.md) | 自增主键                                                              |
| url_hash     | text                        |                                      | false    |                                                                                               | SHA256(url)，用于去重                                                  |
| title        | text                        |                                      | false    |                                                                                               | 文章标题                                                              |
| url          | text                        |                                      | false    |                                                                                               | 原始 URL                                                            |
| content      | text                        |                                      | true     |                                                                                               | Markdown 格式正文                                                     |
| html_content | text                        |                                      | true     |                                                                                               | 原始 HTML（抓取阶段使用，后续清空）                                              |
| summary      | text                        |                                      | true     |                                                                                               | AI 生成的摘要                                                          |
| source       | text                        |                                      | true     |                                                                                               | 新闻来源名称                                                            |
| author       | text                        | ''::text                             | true     |                                                                                               | 作者                                                                |
| language     | text                        |                                      | true     |                                                                                               | 语言 (en / zh / unknown)                                            |
| published_at | timestamp without time zone |                                      | true     |                                                                                               | 发布时间                                                              |
| created_at   | timestamp without time zone | CURRENT_TIMESTAMP                    | true     |                                                                                               | 入库时间                                                              |
| status       | text                        | 'stored'::text                       | true     |                                                                                               | 生命周期状态: stored → pending_summary → summarized → embedded          |
| tags         | jsonb                       | '[]'::jsonb                          | true     |                                                                                               | AI 生成的标签数组 (JSONB)                                                |

## 约束一览

| 名称                    | 类型          | 定义                |
| --------------------- | ----------- | ----------------- |
| articles_pkey         | PRIMARY KEY | PRIMARY KEY (id)  |
| articles_url_hash_key | UNIQUE      | UNIQUE (url_hash) |

## 索引一览

| 名称                    | 定义                                                                                  |
| --------------------- | ----------------------------------------------------------------------------------- |
| articles_pkey         | CREATE UNIQUE INDEX articles_pkey ON public.articles USING btree (id)               |
| articles_url_hash_key | CREATE UNIQUE INDEX articles_url_hash_key ON public.articles USING btree (url_hash) |
| idx_status            | CREATE INDEX idx_status ON public.articles USING btree (status)                     |
| idx_created_at        | CREATE INDEX idx_created_at ON public.articles USING btree (created_at)             |
| idx_source            | CREATE INDEX idx_source ON public.articles USING btree (source)                     |

## ER 图

```mermaid
erDiagram

"public.parent_chunks" }o--|| "public.articles" : "FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE"
"public.child_chunks" }o--|| "public.articles" : "FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE"

"public.articles" {
  integer id "自增主键"
  text url_hash "SHA256(url)，用于去重"
  text title "文章标题"
  text url "原始 URL"
  text content "Markdown 格式正文"
  text html_content "原始 HTML（抓取阶段使用，后续清空）"
  text summary "AI 生成的摘要"
  text source "新闻来源名称"
  text author "作者"
  text language "语言 (en / zh / unknown)"
  timestamp_without_time_zone published_at "发布时间"
  timestamp_without_time_zone created_at "入库时间"
  text status "生命周期状态: stored → pending_summary → summarized → embedded"
  jsonb tags "AI 生成的标签数组 (JSONB)"
}
"public.parent_chunks" {
  text parent_chunk_id "主键，格式: #quot;{article_id}_p{index}#quot;"
  integer article_id FK "所属文章 ID"
  text content "父 chunk 完整文本 (~1024 token)"
  integer token_count "tiktoken 计算的 token 数"
  jsonb child_chunk_ids "包含的子 chunk ID 数组 (JSONB)"
  text doc_name "文档名"
  text source "新闻来源"
  text url "文章 URL"
  tsvector search_vector "jieba 分词后的全文索引向量 (tsvector)"
  timestamp_without_time_zone created_at "创建时间"
}
"public.child_chunks" {
  text chunk_id "主键，格式: #quot;{article_id}_c{index}#quot;"
  integer article_id FK "所属文章 ID"
  text parent_chunk_id FK "所属父 chunk ID，格式: #quot;{article_id}_p{index}#quot;"
  text content "子 chunk 原文"
  integer token_count "tiktoken 计算的 token 数"
  text doc_name "文档名"
  jsonb heading_path "标题层级路径 (JSONB)"
  integer chunk_index "在文章内的序号"
  text source "新闻来源"
  text url "文章 URL"
  vector_1536_ embedding "子 chunk embedding 向量 (pgvector)"
  timestamp_without_time_zone created_at "创建时间"
}
```

---

> Generated by [tbls](https://github.com/k1LoW/tbls)
