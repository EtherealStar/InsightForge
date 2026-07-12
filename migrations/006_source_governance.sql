BEGIN;

CREATE TABLE IF NOT EXISTS source_profiles (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL UNIQUE,
    tier TEXT NOT NULL DEFAULT 'unknown',
    source_kind TEXT NOT NULL DEFAULT 'other',
    inherit_to_subdomains BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS source_profile_revisions (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES source_profiles(id) ON DELETE CASCADE,
    tier TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS document_clusters (
    id TEXT PRIMARY KEY,
    active_version_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS source_occurrences (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES document_clusters(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    simhash BIGINT NOT NULL,
    high_bands INTEGER[] NOT NULL,
    gray_bands SMALLINT[] NOT NULL,
    algorithm_version TEXT NOT NULL,
    source_profile_revision_id TEXT REFERENCES source_profile_revisions(id),
    source_tier TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_source_occurrences_content_hash ON source_occurrences(content_hash);
CREATE INDEX IF NOT EXISTS idx_source_occurrences_high_bands ON source_occurrences USING GIN(high_bands);
CREATE INDEX IF NOT EXISTS idx_source_occurrences_gray_bands ON source_occurrences USING GIN(gray_bands);
CREATE TABLE IF NOT EXISTS source_document_versions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES document_clusters(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'building',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_document_version ON source_document_versions(document_id) WHERE status = 'active';
DO $$ BEGIN
    ALTER TABLE document_clusters
        ADD CONSTRAINT fk_document_clusters_active_version
        FOREIGN KEY (active_version_id) REFERENCES source_document_versions(id)
        DEFERRABLE INITIALLY DEFERRED;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
CREATE TABLE IF NOT EXISTS duplicate_candidates (
    id TEXT PRIMARY KEY,
    left_occurrence_id TEXT NOT NULL REFERENCES source_occurrences(id) ON DELETE CASCADE,
    right_occurrence_id TEXT NOT NULL REFERENCES source_occurrences(id) ON DELETE CASCADE,
    hamming_distance INTEGER NOT NULL,
    shingle_jaccard DOUBLE PRECISION NOT NULL,
    shingle_containment DOUBLE PRECISION NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(left_occurrence_id, right_occurrence_id)
);
COMMIT;
