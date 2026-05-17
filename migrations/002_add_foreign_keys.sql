-- ============================================================
-- 002_add_foreign_keys.sql
-- 添加外键约束，建立表间引用完整性
-- ON DELETE CASCADE: 删除文章时自动级联删除关联的 chunks
-- ============================================================

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_parent_chunks_article'
  ) THEN
    ALTER TABLE parent_chunks
      ADD CONSTRAINT fk_parent_chunks_article
      FOREIGN KEY (article_id) REFERENCES articles(id)
      ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_child_chunks_article'
  ) THEN
    ALTER TABLE child_chunks
      ADD CONSTRAINT fk_child_chunks_article
      FOREIGN KEY (article_id) REFERENCES articles(id)
      ON DELETE CASCADE;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_child_chunks_parent'
  ) THEN
    ALTER TABLE child_chunks
      ADD CONSTRAINT fk_child_chunks_parent
      FOREIGN KEY (parent_chunk_id) REFERENCES parent_chunks(parent_chunk_id)
      ON DELETE CASCADE;
  END IF;
END $$;
