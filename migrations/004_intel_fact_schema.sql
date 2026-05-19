-- 004: Phase 2 structured intel fact schema

BEGIN;

-- ============================================================
-- 1. New structured fact tables
-- ============================================================
CREATE TABLE IF NOT EXISTS intel_facts (
    id                  TEXT PRIMARY KEY,
    source_document_id  UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    fact_kind           TEXT NOT NULL,
    fact_type           TEXT NOT NULL,
    dimension           TEXT NOT NULL,
    subject             TEXT NOT NULL,
    predicate           TEXT NOT NULL,
    object              TEXT NOT NULL DEFAULT '',
    fact_text           TEXT NOT NULL,
    attributes          JSONB NOT NULL DEFAULT '{}'::jsonb,
    event_date          DATE,
    observed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    importance_score    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    confidence_score    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    source_reliability  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    extraction_method   TEXT NOT NULL DEFAULT 'llm',
    extraction_version  TEXT NOT NULL DEFAULT '',
    dedupe_key          TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'draft',
    created_by          TEXT NOT NULL DEFAULT 'system',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_intel_facts_importance_score CHECK (importance_score >= 0.0 AND importance_score <= 1.0),
    CONSTRAINT chk_intel_facts_confidence_score CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    CONSTRAINT chk_intel_facts_source_reliability CHECK (source_reliability >= 0.0 AND source_reliability <= 1.0)
);

CREATE TABLE IF NOT EXISTS intel_fact_competitors (
    fact_id             TEXT NOT NULL REFERENCES intel_facts(id) ON DELETE CASCADE,
    competitor_id       INT NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    relation_type       TEXT NOT NULL DEFAULT 'subject',
    confidence_score    DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (fact_id, competitor_id, relation_type),
    CONSTRAINT chk_intel_fact_competitors_confidence_score CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0)
);

CREATE TABLE IF NOT EXISTS intel_fact_products (
    fact_id             TEXT NOT NULL REFERENCES intel_facts(id) ON DELETE CASCADE,
    product_id          INT NOT NULL REFERENCES competitor_products(id) ON DELETE CASCADE,
    relation_type       TEXT NOT NULL DEFAULT 'subject',
    confidence_score    DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (fact_id, product_id, relation_type),
    CONSTRAINT chk_intel_fact_products_confidence_score CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0)
);

CREATE TABLE IF NOT EXISTS evidence_refs (
    id                  TEXT PRIMARY KEY,
    owner_type          TEXT NOT NULL,
    owner_id            TEXT NOT NULL,
    source_document_id  UUID REFERENCES source_documents(id) ON DELETE CASCADE,
    parent_chunk_id     TEXT REFERENCES document_parent_chunks(parent_chunk_id) ON DELETE SET NULL,
    url                 TEXT NOT NULL DEFAULT '',
    title               TEXT NOT NULL DEFAULT '',
    snippet             TEXT NOT NULL DEFAULT '',
    quote_hash          TEXT NOT NULL DEFAULT '',
    evidence_type       TEXT NOT NULL DEFAULT 'source_chunk',
    relevance_score     DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_evidence_refs_relevance_score CHECK (relevance_score >= 0.0 AND relevance_score <= 1.0)
);

CREATE TABLE IF NOT EXISTS insight_claims (
    id                  TEXT PRIMARY KEY,
    claim_text          TEXT NOT NULL,
    claim_type          TEXT NOT NULL,
    dimension           TEXT NOT NULL,
    competitor_ids      JSONB NOT NULL DEFAULT '[]'::jsonb,
    product_ids         JSONB NOT NULL DEFAULT '[]'::jsonb,
    fact_ids            JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence_score    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    limitations         TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'draft',
    created_by          TEXT NOT NULL DEFAULT 'system',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_insight_claims_confidence_score CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0)
);

-- ============================================================
-- 2. Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_intel_facts_source_document ON intel_facts(source_document_id);
CREATE INDEX IF NOT EXISTS idx_intel_facts_type_event_date ON intel_facts(fact_type, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_intel_facts_dimension_event_date ON intel_facts(dimension, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_intel_facts_status_event_date ON intel_facts(status, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_intel_facts_dedupe_key ON intel_facts(dedupe_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_intel_facts_source_dedupe_key
    ON intel_facts(source_document_id, dedupe_key)
    WHERE dedupe_key <> '';
CREATE INDEX IF NOT EXISTS idx_intel_facts_attributes ON intel_facts USING GIN (attributes);

CREATE INDEX IF NOT EXISTS idx_intel_fact_competitors_competitor ON intel_fact_competitors(competitor_id);
CREATE INDEX IF NOT EXISTS idx_intel_fact_competitors_relation ON intel_fact_competitors(relation_type);
CREATE INDEX IF NOT EXISTS idx_intel_fact_products_product ON intel_fact_products(product_id);
CREATE INDEX IF NOT EXISTS idx_intel_fact_products_relation ON intel_fact_products(relation_type);

CREATE INDEX IF NOT EXISTS idx_evidence_refs_owner ON evidence_refs(owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_evidence_refs_source_document ON evidence_refs(source_document_id);
CREATE INDEX IF NOT EXISTS idx_evidence_refs_parent_chunk ON evidence_refs(parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_evidence_refs_url ON evidence_refs(url);

CREATE INDEX IF NOT EXISTS idx_insight_claims_type_created ON insight_claims(claim_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_insight_claims_dimension_created ON insight_claims(dimension, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_insight_claims_status_created ON insight_claims(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_insight_claims_competitor_ids ON insight_claims USING GIN (competitor_ids);
CREATE INDEX IF NOT EXISTS idx_insight_claims_fact_ids ON insight_claims USING GIN (fact_ids);

-- ============================================================
-- 3. Cleanup legacy phase-1/phase-1.5 intel fields
-- ============================================================
DROP TABLE IF EXISTS intel_products;
DROP TABLE IF EXISTS intel_competitors;

ALTER TABLE source_documents
    DROP COLUMN IF EXISTS intel_type,
    DROP COLUMN IF EXISTS analysis_notes,
    DROP COLUMN IF EXISTS source_reliability;

COMMENT ON TABLE intel_facts IS 'Structured competitor intelligence facts and events.';
COMMENT ON TABLE evidence_refs IS 'Evidence references for facts and claims.';
COMMENT ON TABLE insight_claims IS 'Analytical claims built from facts and evidence.';

COMMIT;
