BEGIN;

-- 权威事务复核只依赖 PostgreSQL 中可重放的指纹，不回读 Redis 或临时正文。
ALTER TABLE source_occurrences
    ADD COLUMN IF NOT EXISTS shingles TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS content_length INTEGER NOT NULL DEFAULT 0;

COMMIT;
