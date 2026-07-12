BEGIN;

-- Evidence Reference 直接切换到版本化证据语义，不保留旧的模糊来源评分字段。
ALTER TABLE evidence_refs
    ADD COLUMN IF NOT EXISTS document_version_id TEXT REFERENCES source_document_versions(id),
    ADD COLUMN IF NOT EXISTS source_occurrence_id TEXT REFERENCES source_occurrences(id),
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS stance TEXT NOT NULL DEFAULT 'supports',
    ADD COLUMN IF NOT EXISTS source_tier TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS source_kind TEXT NOT NULL DEFAULT 'other',
    ADD COLUMN IF NOT EXISTS role_overridden BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS override_reason TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS override_actor TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_evidence_refs_document_version ON evidence_refs(document_version_id);
CREATE INDEX IF NOT EXISTS idx_evidence_refs_occurrence ON evidence_refs(source_occurrence_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_fact_version_occurrence_quote
    ON evidence_refs(owner_type, owner_id, document_version_id, source_occurrence_id, quote_hash)
    WHERE owner_type = 'intel_fact' AND document_version_id IS NOT NULL;

COMMIT;
