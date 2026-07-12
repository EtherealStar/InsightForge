BEGIN;

ALTER TABLE document_clusters
    ADD COLUMN IF NOT EXISTS canonical_occurrence_id TEXT REFERENCES source_occurrences(id);

CREATE TABLE IF NOT EXISTS governance_audit_log (
    id BIGSERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    before_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_governance_audit_entity
    ON governance_audit_log(entity_type, entity_id, created_at DESC);

COMMIT;
