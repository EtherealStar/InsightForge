BEGIN;

-- 011: 三层结构化情报完整目标 schema
-- 数据库为全新创建，无遗留数据。旧字段保留在表上以兼容已有代码。

-- 1. Intel Fact 目标字段
ALTER TABLE intel_facts
    ADD COLUMN IF NOT EXISTS normalized_data JSONB,
    ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS time_precision TEXT,
    ADD COLUMN IF NOT EXISTS candidate_key TEXT,
    ADD COLUMN IF NOT EXISTS lifecycle_status TEXT,
    ADD COLUMN IF NOT EXISTS target_verification_status TEXT,
    ADD COLUMN IF NOT EXISTS status_reason TEXT,
    ADD COLUMN IF NOT EXISTS supersedes_fact_id TEXT,
    ADD COLUMN IF NOT EXISTS extraction_version_target TEXT;

CREATE INDEX IF NOT EXISTS idx_intel_facts_lifecycle_status ON intel_facts(lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_intel_facts_candidate_key ON intel_facts(candidate_key);
CREATE INDEX IF NOT EXISTS idx_intel_facts_occurred_at ON intel_facts(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_intel_facts_valid_from ON intel_facts(valid_from DESC);
CREATE INDEX IF NOT EXISTS idx_intel_facts_supersedes ON intel_facts(supersedes_fact_id);

-- 旧 NOT NULL 字段放宽：v2 fact 不再使用 fact_kind / dimension / subject /
-- predicate / object / attributes / event_date / observed_at / extraction_method /
-- extraction_version / assertion_key / status / source_document_id / importance_score /
-- confidence_score / verification_status / verification_reason / fact_type / fact_text /
-- created_at / updated_at 等旧字段。fact_text 和 created_at / updated_at 仍由 v2 写入，
-- 所以保留 NOT NULL；其它全部放宽。
DO $$
BEGIN
    ALTER TABLE intel_facts ALTER COLUMN fact_kind DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN dimension DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN subject DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN predicate DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN object DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN attributes DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN importance_score DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN confidence_score DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN extraction_method DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN extraction_version DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN assertion_key DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN status DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN verification_status DROP NOT NULL;
    ALTER TABLE intel_facts ALTER COLUMN verification_reason DROP NOT NULL;
EXCEPTION WHEN others THEN NULL;
END $$;
DO $$
BEGIN
    ALTER TABLE intel_facts ALTER COLUMN source_document_id DROP NOT NULL;
EXCEPTION WHEN undefined_column THEN NULL;
END $$;

ALTER TABLE intel_facts DROP CONSTRAINT IF EXISTS chk_intel_facts_lifecycle_status_target;
ALTER TABLE intel_facts ADD CONSTRAINT chk_intel_facts_lifecycle_status_target
    CHECK (lifecycle_status IS NULL OR lifecycle_status IN ('draft','active','superseded','retracted','rejected'));

ALTER TABLE intel_facts DROP CONSTRAINT IF EXISTS chk_intel_facts_verification_target;
ALTER TABLE intel_facts ADD CONSTRAINT chk_intel_facts_verification_target
    CHECK (target_verification_status IS NULL OR target_verification_status IN ('single_source','self_reported','corroborated','disputed'));

ALTER TABLE intel_facts DROP CONSTRAINT IF EXISTS chk_intel_facts_time_precision_target;
ALTER TABLE intel_facts ADD CONSTRAINT chk_intel_facts_time_precision_target
    CHECK (time_precision IS NULL OR time_precision IN ('day','month','quarter','unknown'));

ALTER TABLE intel_facts DROP CONSTRAINT IF EXISTS chk_intel_facts_valid_range_target;
ALTER TABLE intel_facts ADD CONSTRAINT chk_intel_facts_valid_range_target
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from);

ALTER TABLE intel_facts DROP CONSTRAINT IF EXISTS chk_intel_facts_no_self_supersede_target;
ALTER TABLE intel_facts ADD CONSTRAINT chk_intel_facts_no_self_supersede_target
    CHECK (supersedes_fact_id IS NULL OR supersedes_fact_id <> id);
ALTER TABLE intel_facts DROP CONSTRAINT IF EXISTS chk_intel_facts_target_fact_type;
ALTER TABLE intel_facts ADD CONSTRAINT chk_intel_facts_target_fact_type
    CHECK (lifecycle_status IS NULL OR fact_type IN ('product','commercial','corporate','ecosystem','customer_market','risk','general'));

-- 2. Evidence Reference 目标 anchor 字段
ALTER TABLE evidence_refs
    ADD COLUMN IF NOT EXISTS quoted_text TEXT,
    ADD COLUMN IF NOT EXISTS quote_hash TEXT,
    ADD COLUMN IF NOT EXISTS locator JSONB;

-- 旧 NOT NULL 字段放宽：v2 Evidence Reference 不再使用 owner_type / owner_id /
-- url / title / snippet / evidence_type / relevance_score / role / stance /
-- source_tier / source_kind / role_overridden / override_reason / override_actor。
DO $$
BEGIN
    ALTER TABLE evidence_refs ALTER COLUMN owner_type DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN owner_id DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN url DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN title DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN snippet DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN evidence_type DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN role DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN stance DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN source_tier DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN source_kind DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN role_overridden DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN override_reason DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN override_actor DROP NOT NULL;
    ALTER TABLE evidence_refs ALTER COLUMN relevance_score DROP NOT NULL;
EXCEPTION WHEN others THEN NULL;
END $$;

DROP INDEX IF EXISTS uq_evidence_fact_version_occurrence_quote;

CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_target_anchor
    ON evidence_refs(document_version_id, source_occurrence_id, quote_hash)
    WHERE quoted_text IS NOT NULL AND document_version_id IS NOT NULL
      AND source_occurrence_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_evidence_refs_quote_hash ON evidence_refs(quote_hash);

ALTER TABLE evidence_refs DROP CONSTRAINT IF EXISTS chk_evidence_refs_locator;
ALTER TABLE evidence_refs ADD CONSTRAINT chk_evidence_refs_locator
    CHECK (
        locator IS NULL
        OR (
            locator ? 'kind'
            AND locator ->> 'kind' = 'char_range'
            AND (locator ->> 'start') IS NOT NULL
            AND (locator ->> 'end') IS NOT NULL
            AND (locator ->> 'start') ~ '^[0-9]+$'
            AND (locator ->> 'end') ~ '^[0-9]+$'
            AND (locator ->> 'end')::bigint > (locator ->> 'start')::bigint
        )
    );

-- 3. Fact-Competitor / Fact-Product 关系目标字段
ALTER TABLE intel_fact_competitors
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'subject',
    ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'confirmed';

ALTER TABLE intel_fact_products
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'subject',
    ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'confirmed';

ALTER TABLE intel_fact_competitors DROP CONSTRAINT IF EXISTS chk_intel_fact_competitors_role_target;
ALTER TABLE intel_fact_competitors ADD CONSTRAINT chk_intel_fact_competitors_role_target
    CHECK (role IN ('subject','counterpart','mentioned'));

ALTER TABLE intel_fact_competitors DROP CONSTRAINT IF EXISTS chk_intel_fact_competitors_review_target;
ALTER TABLE intel_fact_competitors ADD CONSTRAINT chk_intel_fact_competitors_review_target
    CHECK (review_status IN ('confirmed','needs_review'));

ALTER TABLE intel_fact_products DROP CONSTRAINT IF EXISTS chk_intel_fact_products_role_target;
ALTER TABLE intel_fact_products ADD CONSTRAINT chk_intel_fact_products_role_target
    CHECK (role IN ('subject','counterpart','mentioned'));

ALTER TABLE intel_fact_products DROP CONSTRAINT IF EXISTS chk_intel_fact_products_review_target;
ALTER TABLE intel_fact_products ADD CONSTRAINT chk_intel_fact_products_review_target
    CHECK (review_status IN ('confirmed','needs_review'));
-- 4. source_profile_competitors（事实主体控制来源）
CREATE TABLE IF NOT EXISTS source_profile_competitors (
    profile_id    TEXT NOT NULL REFERENCES source_profiles(id) ON DELETE CASCADE,
    competitor_id INTEGER NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    created_by    TEXT NOT NULL DEFAULT 'system',
    reason        TEXT NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (profile_id, competitor_id)
);

CREATE INDEX IF NOT EXISTS idx_source_profile_competitors_competitor
    ON source_profile_competitors(competitor_id);

COMMENT ON TABLE source_profile_competitors IS
    'Source Profile 与事实主体 competitor 的受控关系，用于 self_reported 判定。';

-- 5. Fact ↔ Evidence 关系
CREATE TABLE IF NOT EXISTS fact_evidence (
    fact_id         TEXT NOT NULL REFERENCES intel_facts(id) ON DELETE CASCADE,
    evidence_ref_id TEXT NOT NULL REFERENCES evidence_refs(id) ON DELETE CASCADE,
    stance          TEXT NOT NULL DEFAULT 'supports',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (fact_id, evidence_ref_id)
);

ALTER TABLE fact_evidence DROP CONSTRAINT IF EXISTS chk_fact_evidence_stance;
ALTER TABLE fact_evidence ADD CONSTRAINT chk_fact_evidence_stance
    CHECK (stance IN ('supports','contradicts','contextual'));

CREATE INDEX IF NOT EXISTS idx_fact_evidence_fact ON fact_evidence(fact_id);
CREATE INDEX IF NOT EXISTS idx_fact_evidence_evidence ON fact_evidence(evidence_ref_id);

-- 6. Insight Claim 目标字段
ALTER TABLE insight_claims
    ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS maturity TEXT,
    ADD COLUMN IF NOT EXISTS status_reason TEXT,
    ADD COLUMN IF NOT EXISTS approved_by TEXT,
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS supersedes_claim_id TEXT,
    ADD COLUMN IF NOT EXISTS scope JSONB;

-- 旧 NOT NULL 字段放宽：v2 claim 不再使用 claim_type / dimension /
-- confidence_score / competitor_ids / product_ids / fact_ids / status 等旧字段。
DO $$
BEGIN
    ALTER TABLE insight_claims ALTER COLUMN claim_type DROP NOT NULL;
    ALTER TABLE insight_claims ALTER COLUMN dimension DROP NOT NULL;
    ALTER TABLE insight_claims ALTER COLUMN confidence_score DROP NOT NULL;
    ALTER TABLE insight_claims ALTER COLUMN limitations DROP NOT NULL;
    ALTER TABLE insight_claims ALTER COLUMN status DROP NOT NULL;
EXCEPTION WHEN others THEN NULL;
END $$;

ALTER TABLE insight_claims DROP CONSTRAINT IF EXISTS chk_insight_claims_maturity_target;
ALTER TABLE insight_claims ADD CONSTRAINT chk_insight_claims_maturity_target
    CHECK (maturity IS NULL OR maturity IN ('draft','hypothesis','supported','needs_review','disputed','superseded'));

ALTER TABLE insight_claims DROP CONSTRAINT IF EXISTS chk_insight_claims_supported_approver;
ALTER TABLE insight_claims ADD CONSTRAINT chk_insight_claims_supported_approver
    CHECK (maturity IS DISTINCT FROM 'supported' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL));

ALTER TABLE insight_claims DROP CONSTRAINT IF EXISTS chk_insight_claims_no_self_supersede;
ALTER TABLE insight_claims ADD CONSTRAINT chk_insight_claims_no_self_supersede
    CHECK (supersedes_claim_id IS NULL OR supersedes_claim_id <> id);

CREATE INDEX IF NOT EXISTS idx_insight_claims_maturity ON insight_claims(maturity);
CREATE INDEX IF NOT EXISTS idx_insight_claims_supersedes ON insight_claims(supersedes_claim_id);
CREATE INDEX IF NOT EXISTS idx_insight_claims_tags ON insight_claims USING GIN (tags);

-- 7. Claim ↔ Fact 关系
CREATE TABLE IF NOT EXISTS claim_facts (
    claim_id   TEXT NOT NULL REFERENCES insight_claims(id) ON DELETE CASCADE,
    fact_id    TEXT NOT NULL REFERENCES intel_facts(id) ON DELETE CASCADE,
    stance     TEXT NOT NULL DEFAULT 'supports',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (claim_id, fact_id)
);

ALTER TABLE claim_facts DROP CONSTRAINT IF EXISTS chk_claim_facts_stance;
ALTER TABLE claim_facts ADD CONSTRAINT chk_claim_facts_stance
    CHECK (stance IN ('supports','contradicts','contextual'));

CREATE INDEX IF NOT EXISTS idx_claim_facts_claim ON claim_facts(claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_facts_fact ON claim_facts(fact_id);

-- 8. 报告 citation 快照增量字段
ALTER TABLE report_evidence_refs
    ADD COLUMN IF NOT EXISTS quoted_text_snapshot TEXT,
    ADD COLUMN IF NOT EXISTS locator_snapshot JSONB,
    ADD COLUMN IF NOT EXISTS document_version_id TEXT REFERENCES source_document_versions(id),
    ADD COLUMN IF NOT EXISTS source_occurrence_id TEXT REFERENCES source_occurrences(id);

CREATE INDEX IF NOT EXISTS idx_report_evidence_refs_version
    ON report_evidence_refs(document_version_id);
CREATE INDEX IF NOT EXISTS idx_report_evidence_refs_occurrence
    ON report_evidence_refs(source_occurrence_id);

ALTER TABLE report_evidence_refs DROP CONSTRAINT IF EXISTS chk_report_evidence_refs_snapshot_locator;
ALTER TABLE report_evidence_refs ADD CONSTRAINT chk_report_evidence_refs_snapshot_locator
    CHECK (
        locator_snapshot IS NULL
        OR (
            locator_snapshot ? 'kind'
            AND locator_snapshot ->> 'kind' = 'char_range'
            AND (locator_snapshot ->> 'start') IS NOT NULL
            AND (locator_snapshot ->> 'end') IS NOT NULL
            AND (locator_snapshot ->> 'start') ~ '^[0-9]+$'
            AND (locator_snapshot ->> 'end') ~ '^[0-9]+$'
            AND (locator_snapshot ->> 'end')::bigint > (locator_snapshot ->> 'start')::bigint
        )
    );

COMMIT;
