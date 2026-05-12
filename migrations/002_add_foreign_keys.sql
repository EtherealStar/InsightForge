-- ============================================================
-- 002_add_foreign_keys.sql
-- 添加外键约束，建立表间引用完整性
-- ON DELETE CASCADE: 删除文章时自动级联删除关联的 chunks
-- ============================================================

-- parent_chunks.article_id → articles.id
ALTER TABLE parent_chunks
  ADD CONSTRAINT fk_parent_chunks_article
  FOREIGN KEY (article_id) REFERENCES articles(id)
  ON DELETE CASCADE;

-- child_chunks.article_id → articles.id
ALTER TABLE child_chunks
  ADD CONSTRAINT fk_child_chunks_article
  FOREIGN KEY (article_id) REFERENCES articles(id)
  ON DELETE CASCADE;

-- child_chunks.parent_chunk_id → parent_chunks.parent_chunk_id
ALTER TABLE child_chunks
  ADD CONSTRAINT fk_child_chunks_parent
  FOREIGN KEY (parent_chunk_id) REFERENCES parent_chunks(parent_chunk_id)
  ON DELETE CASCADE;
