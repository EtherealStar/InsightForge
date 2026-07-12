BEGIN;

-- 旧 facts 可由来源文档重新抽取；清空后直接切换身份，不保留文档级键。
TRUNCATE TABLE intel_facts CASCADE;
ALTER TABLE intel_facts DROP COLUMN dedupe_key;
ALTER TABLE intel_facts ADD COLUMN assertion_key TEXT NOT NULL;
ALTER TABLE intel_facts ADD COLUMN IF NOT EXISTS verification_status TEXT NOT NULL DEFAULT 'unverified';
ALTER TABLE intel_facts ADD COLUMN IF NOT EXISTS verification_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE intel_facts DROP COLUMN IF EXISTS source_reliability;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS source_document_id;
CREATE INDEX IF NOT EXISTS idx_intel_facts_assertion_key ON intel_facts(assertion_key);
COMMIT;
