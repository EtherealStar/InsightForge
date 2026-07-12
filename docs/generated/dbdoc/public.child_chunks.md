# public.child_chunks

## 说明

子分块 (pgvector)。≤512 token 的细粒度文本块 + embedding 向量，用于语义检索。

## 列一览

| 名称              | 类型                          | 默认值               | Nullable | 父表                                              | 备注                                             |
| --------------- | --------------------------- | ----------------- | -------- | ----------------------------------------------- | ---------------------------------------------- |
| chunk_id        | text                        |                   | false    |                                                 | 主键，格式: "{article_id}_c{index}"                 |
| article_id      | integer                     |                   | false    | [public.articles](public.articles.md)           | 所属文章 ID                                        |
| parent_chunk_id | text                        |                   | false    | [public.parent_chunks](public.parent_chunks.md) | 所属父 chunk ID，格式: "{article_id}_p{index}"       |
| content         | text                        |                   | false    |                                                 | 子 chunk 原文                                     |
| token_count     | integer                     | 0                 | false    |                                                 | tiktoken 计算的 token 数                           |
| doc_name        | text                        | ''::text          | false    |                                                 | 文档名                                            |
| heading_path    | jsonb                       | '[]'::jsonb       | false    |                                                 | 标题层级路径 (JSONB)                                 |
| chunk_index     | integer                     | 0                 | false    |                                                 | 在文章内的序号                                        |
| source          | text                        | ''::text          | true     |                                                 | 新闻来源                                           |
| url             | text                        | ''::text          | true     |                                                 | 文章 URL                                         |
| embedding       | vector(1536)                |                   | false    |                                                 | 子 chunk embedding 向量 (pgvector)                |
| created_at      | timestamp without time zone | CURRENT_TIMESTAMP | true     |                                                 | 创建时间                                           |

## 约束一览

| 名称                      | 类型          | 定义                                                                                        |
| ----------------------- | ----------- | ----------------------------------------------------------------------------------------- |
| fk_child_chunks_article | FOREIGN KEY | FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE                        |
| fk_child_chunks_parent  | FOREIGN KEY | FOREIGN KEY (parent_chunk_id) REFERENCES parent_chunks(parent_chunk_id) ON DELETE CASCADE |
| child_chunks_pkey       | PRIMARY KEY | PRIMARY KEY (chunk_id)                                                                    |

## 索引一览

| 名称                               | 定义                                                                                                 |
| -------------------------------- | -------------------------------------------------------------------------------------------------- |
| child_chunks_pkey                | CREATE UNIQUE INDEX child_chunks_pkey ON public.child_chunks USING btree (chunk_id)                |
| idx_child_chunks_article_id      | CREATE INDEX idx_child_chunks_article_id ON public.child_chunks USING btree (article_id)           |
| idx_child_chunks_parent_chunk_id | CREATE INDEX idx_child_chunks_parent_chunk_id ON public.child_chunks USING btree (parent_chunk_id) |

## ER 图

```mermaid
erDiagram

"public.child_chunks" }o--|| "public.articles" : "FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE"
"public.child_chunks" }o--|| "public.parent_chunks" : "FOREIGN KEY (parent_chunk_id) REFERENCES parent_chunks(parent_chunk_id) ON DELETE CASCADE"

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
```

---

> Generated by [tbls](https://github.com/k1LoW/tbls)
