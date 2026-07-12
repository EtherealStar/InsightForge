BEGIN;

-- ============================================================
-- 013: 三层结构化情报切流 contract migration
-- ============================================================
-- 本 migration 把 v2 字段置为 NOT NULL 并删除旧字段。一次性、不可回滚：
--   * 删除旧 analysis_reports / report_claims / report_evidence_refs /
--     report_quality_reviews / analysis_audit_log（按用户决定）。
--   * 删除旧 intel_facts 行 (lifecycle_status IS NULL)。
--   * 删除旧 insight_claims 行 (maturity IS NULL)。
--   * 删除旧 owner/role/score/JSON 字段。
--   * 将 lifecycle_status / maturity / verification_status 字段设为 NOT NULL。
--   * 重命名 verification_status → verification_status_v1（保留旧 unverified
--     字段以兼容可能尚未迁移的代码，但不再写入）。
-- ============================================================

-- 1. 旧结构化情报行清空
DELETE FROM intel_facts WHERE lifecycle_status IS NULL;
DELETE FROM insight_claims WHERE maturity IS NULL;
DELETE FROM evidence_refs WHERE quoted_text IS NULL;
DELETE FROM intel_fact_competitors
 WHERE NOT EXISTS (SELECT 1 FROM intel_facts WHERE id = intel_fact_competitors.fact_id);
DELETE FROM intel_fact_products
 WHERE NOT EXISTS (SELECT 1 FROM intel_facts WHERE id = intel_fact_products.fact_id);
DELETE FROM claim_facts
 WHERE NOT EXISTS (SELECT 1 FROM insight_claims WHERE id = claim_facts.claim_id);

-- 2. 删除旧报告域（按用户决定：切流时不迁移旧报告）
DELETE FROM report_evidence_refs;
DELETE FROM report_claims;
DELETE FROM report_quality_reviews;
DELETE FROM analysis_audit_log;
DELETE FROM analysis_reports;

-- 3. 旧字段删除
ALTER TABLE intel_facts DROP COLUMN IF EXISTS fact_kind;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS dimension;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS subject;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS predicate;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS object;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS attributes;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS event_date;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS importance_score;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS confidence_score;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS extraction_method;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS extraction_version;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS assertion_key;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS status;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS source_document_id;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS competitor_ids;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS product_ids;

ALTER TABLE insight_claims DROP COLUMN IF EXISTS claim_type;
ALTER TABLE insight_claims DROP COLUMN IF EXISTS dimension;
ALTER TABLE insight_claims DROP COLUMN IF EXISTS competitor_ids;
ALTER TABLE insight_claims DROP COLUMN IF EXISTS product_ids;
ALTER TABLE insight_claims DROP COLUMN IF EXISTS fact_ids;
ALTER TABLE insight_claims DROP COLUMN IF EXISTS confidence_score;
ALTER TABLE insight_claims DROP COLUMN IF EXISTS limitations;
ALTER TABLE insight_claims DROP COLUMN IF EXISTS status;

ALTER TABLE evidence_refs DROP COLUMN IF EXISTS owner_type;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS owner_id;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS url;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS title;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS snippet;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS evidence_type;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS relevance_score;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS role;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS stance;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS source_tier;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS source_kind;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS role_overridden;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS override_reason;
ALTER TABLE evidence_refs DROP COLUMN IF EXISTS override_actor;

ALTER TABLE intel_fact_competitors DROP COLUMN IF EXISTS confidence_score;
ALTER TABLE intel_fact_products DROP COLUMN IF EXISTS confidence_score;

ALTER TABLE report_evidence_refs DROP COLUMN IF EXISTS url;
ALTER TABLE report_evidence_refs DROP COLUMN IF EXISTS title;
ALTER TABLE report_evidence_refs DROP COLUMN IF EXISTS snippet;

-- 4. 旧 CHECK constraints 清理
ALTER TABLE intel_facts DROP CONSTRAINT IF EXISTS chk_intel_facts_importance_score;
ALTER TABLE intel_facts DROP CONSTRAINT IF EXISTS chk_intel_facts_confidence_score;
ALTER TABLE intel_facts DROP CONSTRAINT IF EXISTS chk_intel_facts_source_reliability;
ALTER TABLE intel_fact_competitors DROP CONSTRAINT IF EXISTS chk_intel_fact_competitors_confidence_score;
ALTER TABLE intel_fact_products DROP CONSTRAINT IF EXISTS chk_intel_fact_products_confidence_score;
ALTER TABLE evidence_refs DROP CONSTRAINT IF EXISTS chk_evidence_refs_relevance_score;
ALTER TABLE insight_claims DROP CONSTRAINT IF EXISTS chk_insight_claims_confidence_score;
ALTER TABLE report_quality_reviews DROP CONSTRAINT IF EXISTS chk_report_quality_reviews_overall_score;

-- 5. 新字段 NOT NULL
ALTER TABLE intel_facts ALTER COLUMN fact_text SET NOT NULL;
ALTER TABLE intel_facts ALTER COLUMN lifecycle_status SET NOT NULL;
ALTER TABLE intel_facts ALTER COLUMN created_by SET NOT NULL;
ALTER TABLE intel_facts ALTER COLUMN created_at SET NOT NULL;
ALTER TABLE intel_facts ALTER COLUMN updated_at SET NOT NULL;

-- 重命名 target_verification_status → verification_status；旧的 verification_status
-- （unverified 语义）已被全部清空，可直接删除。
ALTER TABLE intel_facts DROP CONSTRAINT IF EXISTS chk_intel_facts_verification;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS verification_status;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS verification_reason;
ALTER TABLE intel_facts DROP COLUMN IF EXISTS observed_at;
ALTER TABLE intel_facts RENAME COLUMN target_verification_status TO verification_status;
ALTER TABLE intel_facts ALTER COLUMN verification_status SET NOT NULL;

ALTER TABLE insight_claims ALTER COLUMN claim_text SET NOT NULL;
ALTER TABLE insight_claims ALTER COLUMN maturity SET NOT NULL;
ALTER TABLE insight_claims ALTER COLUMN created_by SET NOT NULL;
ALTER TABLE insight_claims ALTER COLUMN created_at SET NOT NULL;
ALTER TABLE insight_claims ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE evidence_refs ALTER COLUMN quoted_text SET NOT NULL;
ALTER TABLE evidence_refs ALTER COLUMN quote_hash SET NOT NULL;
ALTER TABLE evidence_refs ALTER COLUMN document_version_id SET NOT NULL;
ALTER TABLE evidence_refs ALTER COLUMN source_occurrence_id SET NOT NULL;

COMMIT;