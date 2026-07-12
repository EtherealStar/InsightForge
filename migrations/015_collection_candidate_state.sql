BEGIN;

ALTER TABLE fetch_candidates
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'discovered';

ALTER TABLE fetch_candidates
    DROP CONSTRAINT IF EXISTS fetch_candidates_status_check;

ALTER TABLE fetch_candidates
    ADD CONSTRAINT fetch_candidates_status_check CHECK (status IN (
        'discovered', 'fetching', 'fetched', 'normalized',
        'accepted', 'review_required', 'rejected', 'failed', 'unchanged'
    ));

COMMIT;
