BEGIN;

ALTER TABLE source_profiles ADD COLUMN IF NOT EXISTS collection_config JSONB NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS collection_runs (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('pending','running','succeeded','partial_failed','failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS source_fetch_tasks (
    id UUID PRIMARY KEY,
    collection_run_id UUID NOT NULL REFERENCES collection_runs(id) ON DELETE CASCADE,
    source_profile_id TEXT NOT NULL REFERENCES source_profiles(id),
    status TEXT NOT NULL CHECK (status IN ('pending','running','succeeded','failed','paused')),
    attempt INTEGER NOT NULL DEFAULT 0,
    error JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (collection_run_id, source_profile_id)
);

CREATE TABLE IF NOT EXISTS source_cursors (
    source_profile_id TEXT PRIMARY KEY REFERENCES source_profiles(id) ON DELETE CASCADE,
    cursor_value TEXT NOT NULL,
    etag TEXT,
    last_modified TEXT,
    next_due_at TIMESTAMPTZ,
    consecutive_unchanged INTEGER NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    circuit_open_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fetch_candidates (
    id UUID PRIMARY KEY,
    source_task_id UUID NOT NULL REFERENCES source_fetch_tasks(id) ON DELETE CASCADE,
    source_profile_id TEXT NOT NULL REFERENCES source_profiles(id),
    normalized_url TEXT NOT NULL,
    discovery_cursor TEXT NOT NULL,
    expected_media_type TEXT,
    canonical_url TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    metadata JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'discovered' CHECK (status IN (
        'discovered','fetching','fetched','normalized','accepted','review_required','rejected','failed','unchanged'
    )),
    discovered_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_fetch_artifacts (
    id UUID PRIMARY KEY,
    candidate_id UUID NOT NULL REFERENCES fetch_candidates(id),
    source_task_id UUID NOT NULL REFERENCES source_fetch_tasks(id),
    request_url TEXT NOT NULL,
    final_url TEXT NOT NULL,
    fetch_method TEXT NOT NULL CHECK (fetch_method IN ('http','browser')),
    status TEXT NOT NULL CHECK (status IN ('fetched','not_modified','blocked','failed')),
    http_status INTEGER,
    content_type TEXT,
    body_hash TEXT,
    blob_path TEXT,
    headers JSONB NOT NULL DEFAULT '{}',
    retained BOOLEAN NOT NULL DEFAULT FALSE,
    retention_reason TEXT,
    expires_at TIMESTAMPTZ,
    reason_code TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (candidate_id, fetch_method, body_hash)
);
CREATE INDEX IF NOT EXISTS idx_fetch_artifacts_body_hash ON raw_fetch_artifacts(body_hash);
CREATE INDEX IF NOT EXISTS idx_fetch_artifacts_expiry ON raw_fetch_artifacts(expires_at) WHERE retained = FALSE;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fetch_artifact_observation
    ON raw_fetch_artifacts(candidate_id, fetch_method, COALESCE(body_hash, ''));

CREATE TABLE IF NOT EXISTS normalized_documents (
    id UUID PRIMARY KEY,
    artifact_id UUID NOT NULL REFERENCES raw_fetch_artifacts(id),
    normalizer_version TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('accepted','retry_render','review_required','rejected')),
    reason_codes TEXT[] NOT NULL DEFAULT '{}',
    title TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (artifact_id, normalizer_version)
);

CREATE TABLE IF NOT EXISTS content_blocks (
    id TEXT PRIMARY KEY,
    normalized_document_id UUID NOT NULL REFERENCES normalized_documents(id) ON DELETE CASCADE,
    block_type TEXT NOT NULL,
    block_text TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    source_locator TEXT NOT NULL,
    UNIQUE (normalized_document_id, ordinal)
);

COMMIT;
