import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from infrastructure.collection_store import (
    PostgresCollectionRunStore,
    PostgresFetchArtifactStore,
    PostgresFetchCandidateStore,
    PostgresNormalizedDocumentStore,
)
from infrastructure.redis.state_store import RedisStateStore
from infrastructure.source_profile_store import PostgresSourceProfileStore
from models.collection import (
    ArtifactStatus,
    CollectionRun,
    CollectionRunStatus,
    ContentBlock,
    FetchCandidate,
    FetchMethod,
    NormalizationOutcome,
    NormalizedDocument,
    RawFetchArtifact,
    SourceFetchTask,
)
from models.source_governance import SourceProfile, SourceTier
from tests.test_migration_runner import _copy_migrations_to, _drop_database, _isolated_database, _run_runner


@pytest.mark.skipif(not os.getenv("TEST_PG_DSN"), reason="TEST_PG_DSN not set")
def test_postgres_collection_state_survives_redis_loss():
    dsn, database_name = _isolated_database()
    try:
        with tempfile.TemporaryDirectory() as directory:
            migration_dir = _copy_migrations_to(Path(directory))
            applied = _run_runner(migration_dir, dsn)
            assert applied.returncode == 0, applied.stdout + applied.stderr

        profile = PostgresSourceProfileStore(dsn).save_profile(
            SourceProfile(
                "fixture.invalid", tier=SourceTier.A,
                collection_config={"connector": "rss", "endpoint": "https://fixture.invalid/rss"},
            ),
            actor="integration-test",
            reason="collection recovery fixture",
        )
        runs = PostgresCollectionRunStore(dsn)
        run = runs.create_run(CollectionRun(status=CollectionRunStatus.RUNNING))
        task = runs.create_task(SourceFetchTask(run.id, profile.id))
        candidates = PostgresFetchCandidateStore(dsn)
        candidate = candidates.save_candidate(
            task.id,
            FetchCandidate(profile.id, "https://fixture.invalid/post", datetime.now(UTC), "cursor-1"),
        )
        artifacts = PostgresFetchArtifactStore(dsn)
        artifact = artifacts.save_artifact(
            RawFetchArtifact(
                candidate.id, task.id, candidate.normalized_url, candidate.normalized_url,
                FetchMethod.HTTP, ArtifactStatus.FETCHED, 200, "text/html", "body-hash",
                datetime.now(UTC), blob_path="aa/artifact.gz", expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        duplicate = artifacts.save_artifact(
            RawFetchArtifact(
                candidate.id, task.id, candidate.normalized_url, candidate.normalized_url,
                FetchMethod.HTTP, ArtifactStatus.FETCHED, 200, "text/html", "body-hash",
                datetime.now(UTC), blob_path="aa/artifact-restored.gz", expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        assert duplicate.id == artifact.id
        assert artifacts.get_artifact(artifact.id).blob_path == "aa/artifact-restored.gz"
        normalized_store = PostgresNormalizedDocumentStore(dsn)
        normalized_store.save_document(
            NormalizedDocument(
                artifact.id, "v1", NormalizationOutcome.ACCEPTED,
                [ContentBlock("block-1", "p", "Verbatim evidence body", 0, "block:0")], [],
            )
        )
        candidates.advance_candidate(candidate.id, "accepted")
        runs.advance_task(task.id, "succeeded")
        assert runs.reconcile(run.id).status is CollectionRunStatus.SUCCEEDED
        before = runs.collection_metrics()

        redis_url = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")
        redis_state = RedisStateStore(redis_url)
        assert redis_state.set_json("logos:recovery:test", {"run_id": run.id})
        redis_state._redis.flushdb()
        assert redis_state.get_json("logos:recovery:test") is None

        assert runs.collection_metrics() == before
        assert before["candidates_discovered"] == 1
        assert before["artifacts_fetched"] == 1
        assert before["documents_accepted"] == 1
    finally:
        _drop_database(database_name)
