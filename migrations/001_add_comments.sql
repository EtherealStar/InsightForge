-- ============================================================
-- 001_add_comments.sql
-- 为所有表和列添加 COMMENT，供 tbls 自动生成文档
-- ============================================================

-- ========== articles 表 ==========
COMMENT ON TABLE articles IS '文章元数据 + 全文存储。Pipeline 采集的新闻文章，经历 stored → pending_summary → summarized → embedded 生命周期。';

COMMENT ON COLUMN articles.id IS '自增主键';
COMMENT ON COLUMN articles.url_hash IS 'SHA256(url)，用于去重';
COMMENT ON COLUMN articles.title IS '文章标题';
COMMENT ON COLUMN articles.url IS '原始 URL';
COMMENT ON COLUMN articles.content IS 'Markdown 格式正文';
COMMENT ON COLUMN articles.html_content IS '原始 HTML（抓取阶段使用，后续清空）';
COMMENT ON COLUMN articles.summary IS 'AI 生成的摘要';
COMMENT ON COLUMN articles.source IS '新闻来源名称';
COMMENT ON COLUMN articles.author IS '作者';
COMMENT ON COLUMN articles.language IS '语言 (en / zh / unknown)';
COMMENT ON COLUMN articles.published_at IS '发布时间';
COMMENT ON COLUMN articles.created_at IS '入库时间';
COMMENT ON COLUMN articles.status IS '生命周期状态: stored → pending_summary → summarized → embedded';
COMMENT ON COLUMN articles.tags IS 'AI 生成的标签数组 (JSONB)';

-- ========== parent_chunks 表 ==========
COMMENT ON TABLE parent_chunks IS '父分块。~1024 token 的大粒度文本块，用于 LLM 召回上下文 + jieba 全文索引。';

COMMENT ON COLUMN parent_chunks.parent_chunk_id IS '主键，格式: "{article_id}_p{index}"';
COMMENT ON COLUMN parent_chunks.article_id IS '所属文章 ID';
COMMENT ON COLUMN parent_chunks.content IS '父 chunk 完整文本 (~1024 token)';
COMMENT ON COLUMN parent_chunks.token_count IS 'tiktoken 计算的 token 数';
COMMENT ON COLUMN parent_chunks.child_chunk_ids IS '包含的子 chunk ID 数组 (JSONB)';
COMMENT ON COLUMN parent_chunks.doc_name IS '文档名';
COMMENT ON COLUMN parent_chunks.source IS '新闻来源';
COMMENT ON COLUMN parent_chunks.url IS '文章 URL';
COMMENT ON COLUMN parent_chunks.search_vector IS 'jieba 分词后的全文索引向量 (tsvector)';
COMMENT ON COLUMN parent_chunks.created_at IS '创建时间';

-- ========== child_chunks 表 ==========
COMMENT ON TABLE child_chunks IS '子分块 (pgvector)。≤512 token 的细粒度文本块 + embedding 向量，用于语义检索。';

COMMENT ON COLUMN child_chunks.chunk_id IS '主键，格式: "{article_id}_c{index}"';
COMMENT ON COLUMN child_chunks.article_id IS '所属文章 ID';
COMMENT ON COLUMN child_chunks.parent_chunk_id IS '所属父 chunk ID，格式: "{article_id}_p{index}"';
COMMENT ON COLUMN child_chunks.content IS '子 chunk 原文';
COMMENT ON COLUMN child_chunks.token_count IS 'tiktoken 计算的 token 数';
COMMENT ON COLUMN child_chunks.doc_name IS '文档名';
COMMENT ON COLUMN child_chunks.heading_path IS '标题层级路径 (JSONB)';
COMMENT ON COLUMN child_chunks.chunk_index IS '在文章内的序号';
COMMENT ON COLUMN child_chunks.source IS '新闻来源';
COMMENT ON COLUMN child_chunks.url IS '文章 URL';
COMMENT ON COLUMN child_chunks.embedding IS '子 chunk embedding 向量 (pgvector)';
COMMENT ON COLUMN child_chunks.created_at IS '创建时间';
