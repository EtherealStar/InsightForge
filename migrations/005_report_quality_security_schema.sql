-- 005: Phase 3 report quality, security, and audit schema

BEGIN;

-- ============================================================
-- 1. Extend analysis reports for governed report workflow
-- ============================================================
ALTER TABLE analysis_reports
    ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'not_reviewed',
    ADD COLUMN IF NOT EXISTS quality_score DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS quality_summary TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS generation_context_hash TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS approved_by TEXT,
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_analysis_reports_review_status
    ON analysis_reports(review_status);
CREATE INDEX IF NOT EXISTS idx_analysis_reports_quality_score
    ON analysis_reports(quality_score);

-- ============================================================
-- 2. Report to claim/evidence relationship tables
-- ============================================================
CREATE TABLE IF NOT EXISTS report_claims (
    report_id       INT NOT NULL REFERENCES analysis_reports(id) ON DELETE CASCADE,
    claim_id        TEXT NOT NULL REFERENCES insight_claims(id) ON DELETE CASCADE,
    section_key     TEXT NOT NULL DEFAULT '',
    position        INT NOT NULL DEFAULT 0,
    usage_type      TEXT NOT NULL DEFAULT 'supporting',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (report_id, claim_id, section_key, usage_type)
);

CREATE TABLE IF NOT EXISTS report_evidence_refs (
    id              TEXT PRIMARY KEY,
    report_id       INT NOT NULL REFERENCES analysis_reports(id) ON DELETE CASCADE,
    evidence_ref_id TEXT REFERENCES evidence_refs(id) ON DELETE SET NULL,
    claim_id        TEXT REFERENCES insight_claims(id) ON DELETE SET NULL,
    fact_id         TEXT REFERENCES intel_facts(id) ON DELETE SET NULL,
    section_key     TEXT NOT NULL DEFAULT '',
    citation_label  TEXT NOT NULL DEFAULT '',
    url             TEXT NOT NULL DEFAULT '',
    title           TEXT NOT NULL DEFAULT '',
    snippet         TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_report_claims_report
    ON report_claims(report_id);
CREATE INDEX IF NOT EXISTS idx_report_claims_claim
    ON report_claims(claim_id);
CREATE INDEX IF NOT EXISTS idx_report_evidence_refs_report
    ON report_evidence_refs(report_id);
CREATE INDEX IF NOT EXISTS idx_report_evidence_refs_evidence
    ON report_evidence_refs(evidence_ref_id);
CREATE INDEX IF NOT EXISTS idx_report_evidence_refs_claim
    ON report_evidence_refs(claim_id);
CREATE INDEX IF NOT EXISTS idx_report_evidence_refs_fact
    ON report_evidence_refs(fact_id);
CREATE INDEX IF NOT EXISTS idx_report_evidence_refs_citation
    ON report_evidence_refs(report_id, citation_label);

-- ============================================================
-- 3. Report quality reviews
-- ============================================================
CREATE TABLE IF NOT EXISTS report_quality_reviews (
    id                      TEXT PRIMARY KEY,
    report_id               INT NOT NULL REFERENCES analysis_reports(id) ON DELETE CASCADE,
    review_type             TEXT NOT NULL,
    status                  TEXT NOT NULL,
    overall_score           DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    dimension_scores        JSONB NOT NULL DEFAULT '{}'::jsonb,
    issues                  JSONB NOT NULL DEFAULT '[]'::jsonb,
    revision_suggestions    JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_provider          TEXT NOT NULL DEFAULT '',
    model_name              TEXT NOT NULL DEFAULT '',
    prompt_version          TEXT NOT NULL DEFAULT '',
    reviewed_by             TEXT NOT NULL DEFAULT 'system',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_report_quality_reviews_overall_score
        CHECK (overall_score >= 0.0 AND overall_score <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_report_quality_reviews_report
    ON report_quality_reviews(report_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_report_quality_reviews_status
    ON report_quality_reviews(status, created_at DESC);

-- ============================================================
-- 4. Config audit and API key storage
-- ============================================================
CREATE TABLE IF NOT EXISTS config_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    actor           TEXT NOT NULL,
    action          TEXT NOT NULL,
    target          TEXT NOT NULL,
    changed_keys    JSONB NOT NULL DEFAULT '[]'::jsonb,
    before_masked   JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_masked    JSONB NOT NULL DEFAULT '{}'::jsonb,
    request_id      TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_keys (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    key_hash        TEXT NOT NULL UNIQUE,
    role            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    last_used_at    TIMESTAMPTZ,
    created_by      TEXT NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_config_audit_log_target
    ON config_audit_log(target, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_config_audit_log_actor
    ON config_audit_log(actor, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_keys_status_role
    ON api_keys(status, role);

COMMENT ON TABLE report_claims IS 'Claims referenced by governed analysis reports.';
COMMENT ON TABLE report_evidence_refs IS 'Evidence snapshots and citation labels referenced by governed analysis reports.';
COMMENT ON TABLE report_quality_reviews IS 'Rule, LLM, and manual quality review results for reports.';
COMMENT ON TABLE config_audit_log IS 'Audit log for configuration changes and reloads.';
COMMENT ON TABLE api_keys IS 'Application API keys stored as hashes; plaintext keys are never stored.';

COMMIT;
