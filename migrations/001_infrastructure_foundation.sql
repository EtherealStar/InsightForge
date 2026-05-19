-- 001: Phase 1 infrastructure foundation (PostgreSQL + Qdrant references)
-- PostgreSQL owns source documents, parent chunks, Qdrant point status,
-- upload metadata, and task history. It does not store child chunk embeddings.

BEGIN;

CREATE TABLE IF NOT EXISTS task_runs (
    id              UUID PRIMARY KEY,
    task_type       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    idempotency_key TEXT,
    input           JSONB NOT NULL DEFAULT '{}'::jsonb,
    result          JSONB NOT NULL DEFAULT '{}'::jsonb,
    error           JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempt         INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS task_stages (
    id          UUID PRIMARY KEY,
    task_run_id UUID NOT NULL REFERENCES task_runs(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    result      JSONB NOT NULL DEFAULT '{}'::jsonb,
    error       JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS task_events (
    id          UUID PRIMARY KEY,
    task_run_id UUID NOT NULL REFERENCES task_runs(id) ON DELETE CASCADE,
    stage_id    UUID REFERENCES task_stages(id) ON DELETE SET NULL,
    event_type  TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS upload_batches (
    id                  UUID PRIMARY KEY,
    source              TEXT NOT NULL DEFAULT 'api',
    status              TEXT NOT NULL DEFAULT 'received',
    file_count          INT NOT NULL DEFAULT 0,
    expanded_file_count INT NOT NULL DEFAULT 0,
    total_size_bytes    BIGINT NOT NULL DEFAULT 0,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    error               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS document_blobs (
    id                UUID PRIMARY KEY,
    upload_batch_id   UUID REFERENCES upload_batches(id) ON DELETE SET NULL,
    parent_blob_id    UUID REFERENCES document_blobs(id) ON DELETE SET NULL,
    original_filename TEXT NOT NULL,
    safe_filename     TEXT NOT NULL,
    content_type      TEXT NOT NULL DEFAULT '',
    file_ext          TEXT NOT NULL DEFAULT '',
    size_bytes        BIGINT NOT NULL DEFAULT 0,
    sha256            TEXT NOT NULL,
    storage_path      TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'stored',
    error             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS source_documents (
    id              UUID PRIMARY KEY,
    blob_id         UUID REFERENCES document_blobs(id) ON DELETE SET NULL,
    url             TEXT NOT NULL DEFAULT '',
    canonical_url   TEXT NOT NULL DEFAULT '',
    source_type     TEXT NOT NULL DEFAULT 'web',
    document_type   TEXT NOT NULL DEFAULT 'article',
    title           TEXT NOT NULL,
    content         TEXT NOT NULL DEFAULT '',
    content_hash    TEXT NOT NULL DEFAULT '',
    language        TEXT NOT NULL DEFAULT '',
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    competitor_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
    product_ids     JSONB NOT NULL DEFAULT '[]'::jsonb,
    parse_status    TEXT NOT NULL DEFAULT 'pending',
    parse_error     JSONB NOT NULL DEFAULT '{}'::jsonb,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_parent_chunks (
    parent_chunk_id TEXT PRIMARY KEY,
    document_id     UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    token_count     INT NOT NULL DEFAULT 0,
    child_point_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    heading_path    JSONB NOT NULL DEFAULT '[]'::jsonb,
    doc_name        TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT '',
    url             TEXT NOT NULL DEFAULT '',
    source_type     TEXT NOT NULL DEFAULT 'web',
    document_type   TEXT NOT NULL DEFAULT 'article',
    competitor_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
    product_ids     JSONB NOT NULL DEFAULT '[]'::jsonb,
    language        TEXT NOT NULL DEFAULT '',
    published_at    TIMESTAMPTZ,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    search_vector   TSVECTOR,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_vector_points (
    point_id        TEXT PRIMARY KEY,
    document_id     UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    parent_chunk_id TEXT NOT NULL REFERENCES document_parent_chunks(parent_chunk_id) ON DELETE CASCADE,
    chunk_index     INT NOT NULL DEFAULT 0,
    content_hash    TEXT NOT NULL DEFAULT '',
    token_count     INT NOT NULL DEFAULT 0,
    vector_status   TEXT NOT NULL DEFAULT 'pending',
    error           JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_runs_status_created ON task_runs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_stages_run ON task_stages(task_run_id);
CREATE INDEX IF NOT EXISTS idx_task_events_run_created ON task_events(task_run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_document_blobs_sha256 ON document_blobs(sha256);
CREATE INDEX IF NOT EXISTS idx_document_blobs_batch ON document_blobs(upload_batch_id);
CREATE INDEX IF NOT EXISTS idx_source_documents_source_created ON source_documents(source_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_documents_type_created ON source_documents(document_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_documents_hash ON source_documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_source_documents_parse_status ON source_documents(parse_status);
CREATE INDEX IF NOT EXISTS idx_source_documents_metadata ON source_documents USING GIN(metadata);
CREATE INDEX IF NOT EXISTS idx_document_parent_chunks_document ON document_parent_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_parent_chunks_fts ON document_parent_chunks USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_document_vector_points_document ON document_vector_points(document_id);
CREATE INDEX IF NOT EXISTS idx_document_vector_points_parent ON document_vector_points(parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_document_vector_points_status ON document_vector_points(vector_status);

COMMENT ON TABLE source_documents IS 'Unified source document metadata and normalized content.';
COMMENT ON TABLE document_parent_chunks IS 'Parent chunks stored in PostgreSQL for LLM context and FTS.';
COMMENT ON TABLE document_vector_points IS 'Qdrant child chunk point status; embeddings and child payloads live in Qdrant.';
COMMENT ON COLUMN document_parent_chunks.child_point_ids IS 'All child point IDs included in this parent chunk, including overlap.';
COMMENT ON COLUMN document_vector_points.point_id IS 'Qdrant point id. Stable UUID derived from document_id and chunk_index.';

COMMIT;
