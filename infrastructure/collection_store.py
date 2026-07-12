"""Collection Run、artifact 和 normalized document 的 PostgreSQL 权威存储。"""
from __future__ import annotations

import psycopg2
import psycopg2.extras

from models.collection import (
    ArtifactStatus,
    CollectionRun,
    CollectionRunStatus,
    ContentBlock,
    FetchMethod,
    FetchCandidate,
    CandidateStatus,
    NormalizationOutcome,
    NormalizedDocument,
    RawFetchArtifact,
    SourceFetchTask,
    SourceTaskStatus,
    SourceCursor,
)


class _PostgresStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        return psycopg2.connect(self.dsn)


class PostgresCollectionRunStore(_PostgresStore):
    def create_run(self, run: CollectionRun) -> CollectionRun:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO collection_runs(id,status,created_at,started_at,finished_at)
                   VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (run.id, run.status.value, run.created_at, run.started_at, run.finished_at),
            )
        return run

    def create_task(self, task: SourceFetchTask) -> SourceFetchTask:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO source_fetch_tasks(id,collection_run_id,source_profile_id,status,attempt,error,created_at,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (collection_run_id,source_profile_id) DO UPDATE SET updated_at=source_fetch_tasks.updated_at
                   RETURNING id""",
                (task.id, task.collection_run_id, task.source_profile_id, task.status.value, task.attempt,
                 psycopg2.extras.Json(task.error) if task.error else None, task.created_at, task.updated_at),
            )
            task.id = str(cur.fetchone()[0])
        return task

    def claim_task(self, task_id: str) -> SourceFetchTask:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """UPDATE source_fetch_tasks SET status='running', attempt=attempt+1, updated_at=NOW()
                   WHERE id=%s AND status IN ('pending','running') RETURNING *""",
                (task_id,),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError(f"source fetch task 不可领取: {task_id}")
        return self._task(row)

    def get_task(self, task_id: str) -> SourceFetchTask | None:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM source_fetch_tasks WHERE id=%s", (task_id,))
            row = cur.fetchone()
        return self._task(row) if row else None

    def advance_task(self, task_id: str, status: str, error: dict | None = None) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE source_fetch_tasks SET status=%s,error=%s,updated_at=NOW() WHERE id=%s",
                (status, psycopg2.extras.Json(error) if error else None, task_id),
            )

    def list_tasks(self, run_id: str) -> list[SourceFetchTask]:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM source_fetch_tasks WHERE collection_run_id=%s ORDER BY created_at", (run_id,))
            return [self._task(row) for row in cur.fetchall()]

    def finish_run(self, run_id: str, status: CollectionRunStatus) -> CollectionRun:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "UPDATE collection_runs SET status=%s,finished_at=CASE WHEN %s IN ('running','pending') THEN NULL ELSE NOW() END WHERE id=%s RETURNING *",
                (status.value, status.value, run_id),
            )
            row = cur.fetchone()
        return CollectionRun(CollectionRunStatus(row["status"]), str(row["id"]), row["created_at"], row["started_at"], row["finished_at"])

    def reconcile(self, run_id: str) -> CollectionRun:
        from services.collection_orchestrator import summarize_run
        return self.finish_run(run_id, summarize_run(self.list_tasks(run_id)))

    def list_active_run_ids(self) -> list[str]:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM collection_runs WHERE status IN ('pending','running') ORDER BY created_at")
            return [str(row[0]) for row in cur.fetchall()]

    def collection_metrics(self) -> dict[str, int]:
        queries = {
            "runs_running": "SELECT COUNT(*) FROM collection_runs WHERE status='running'",
            "candidates_discovered": "SELECT COUNT(*) FROM fetch_candidates",
            "artifacts_fetched": "SELECT COUNT(*) FROM raw_fetch_artifacts WHERE status='fetched'",
            "documents_normalized": "SELECT COUNT(*) FROM normalized_documents",
            "documents_accepted": "SELECT COUNT(*) FROM normalized_documents WHERE outcome='accepted'",
            "browser_artifacts": "SELECT COUNT(*) FROM raw_fetch_artifacts WHERE fetch_method='browser'",
            "blocked_artifacts": "SELECT COUNT(*) FROM raw_fetch_artifacts WHERE status='blocked'",
            "not_modified_artifacts": "SELECT COUNT(*) FROM raw_fetch_artifacts WHERE status='not_modified'",
        }
        with self._conn() as conn, conn.cursor() as cur:
            result = {}
            for name, query in queries.items():
                cur.execute(query)
                result[name] = int(cur.fetchone()[0])
            return result

    @staticmethod
    def _task(row) -> SourceFetchTask:
        return SourceFetchTask(str(row["collection_run_id"]), str(row["source_profile_id"]), SourceTaskStatus(row["status"]), row["attempt"], row["error"], str(row["id"]), row["created_at"], row["updated_at"])


class PostgresFetchArtifactStore(_PostgresStore):
    def save_artifact(self, artifact: RawFetchArtifact) -> RawFetchArtifact:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO raw_fetch_artifacts
                   (id,candidate_id,source_task_id,request_url,final_url,fetch_method,status,http_status,content_type,
                    body_hash,blob_path,headers,retained,retention_reason,expires_at,reason_code,observed_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (candidate_id, fetch_method, (COALESCE(body_hash, ''))) DO UPDATE
                   SET observed_at=EXCLUDED.observed_at, status=EXCLUDED.status,
                   http_status=EXCLUDED.http_status, content_type=EXCLUDED.content_type, blob_path=EXCLUDED.blob_path,
                   headers=EXCLUDED.headers, expires_at=EXCLUDED.expires_at, reason_code=EXCLUDED.reason_code
                   RETURNING id""",
                (artifact.id, artifact.candidate_id, artifact.source_task_id, artifact.request_url, artifact.final_url,
                 artifact.fetch_method.value, artifact.status.value, artifact.http_status, artifact.content_type,
                 artifact.body_hash, artifact.blob_path, psycopg2.extras.Json(artifact.headers), artifact.retained,
                 artifact.retention_reason, artifact.expires_at, artifact.reason_code, artifact.observed_at),
            )
            artifact.id = str(cur.fetchone()[0])
        return artifact

    def find_by_body_hash(self, body_hash: str) -> list[RawFetchArtifact]:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM raw_fetch_artifacts WHERE body_hash=%s ORDER BY observed_at DESC", (body_hash,))
            return [self._artifact(row) for row in cur.fetchall()]

    def get_artifact(self, artifact_id: str) -> RawFetchArtifact | None:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM raw_fetch_artifacts WHERE id=%s", (artifact_id,))
            row = cur.fetchone()
        return self._artifact(row) if row else None

    def latest_for_url(self, normalized_url: str) -> RawFetchArtifact | None:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT artifact.* FROM raw_fetch_artifacts artifact
                   JOIN fetch_candidates candidate ON candidate.id=artifact.candidate_id
                   WHERE candidate.normalized_url=%s
                   ORDER BY artifact.observed_at DESC LIMIT 1""",
                (normalized_url,),
            )
            row = cur.fetchone()
        return self._artifact(row) if row else None

    def promote(self, artifact_id: str, reason: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE raw_fetch_artifacts SET retained=TRUE,retention_reason=%s,expires_at=NULL WHERE id=%s", (reason, artifact_id))

    def expire_unretained(self, before) -> int:
        # 这里只清除 body 引用，最小审计元数据永久保留；实际文件由清理任务随后删除。
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE raw_fetch_artifacts SET blob_path=NULL
                   WHERE retained=FALSE AND expires_at<%s AND blob_path IS NOT NULL""",
                (before,),
            )
            return cur.rowcount

    def list_expired_blob_paths(self, before, limit: int = 1000) -> list[str]:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT blob_path FROM raw_fetch_artifacts
                   WHERE blob_path IS NOT NULL
                   GROUP BY blob_path
                   HAVING BOOL_AND(retained=FALSE AND expires_at<%s)
                   ORDER BY MIN(expires_at) LIMIT %s""",
                (before, limit),
            )
            return [row[0] for row in cur.fetchall()]

    @staticmethod
    def _artifact(row) -> RawFetchArtifact:
        return RawFetchArtifact(
            str(row["candidate_id"]), str(row["source_task_id"]), row["request_url"], row["final_url"],
            FetchMethod(row["fetch_method"]), ArtifactStatus(row["status"]), row["http_status"], row["content_type"],
            row["body_hash"], row["observed_at"], str(row["id"]), row["blob_path"], row["headers"], row["retained"],
            row["retention_reason"], row["expires_at"], row["reason_code"],
        )


class PostgresFetchCandidateStore(_PostgresStore):
    def save_candidate(self, source_task_id: str, candidate: FetchCandidate) -> FetchCandidate:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO fetch_candidates
                   (id,source_task_id,source_profile_id,normalized_url,discovery_cursor,expected_media_type,
                    canonical_url,idempotency_key,metadata,status,discovered_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (idempotency_key) DO UPDATE SET discovered_at=EXCLUDED.discovered_at RETURNING id""",
                (candidate.id, source_task_id, candidate.source_profile_id, candidate.normalized_url,
                 candidate.discovery_cursor, candidate.expected_media_type, candidate.canonical_url,
                 candidate.idempotency_key, psycopg2.extras.Json(candidate.metadata), candidate.status.value,
                 candidate.discovered_at),
            )
            candidate.id = str(cur.fetchone()[0])
        return candidate

    def get_candidate(self, candidate_id: str) -> FetchCandidate | None:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM fetch_candidates WHERE id=%s", (candidate_id,))
            row = cur.fetchone()
        return self._candidate(row) if row else None

    def find_by_idempotency_key(self, idempotency_key: str) -> FetchCandidate | None:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM fetch_candidates WHERE idempotency_key=%s", (idempotency_key,))
            row = cur.fetchone()
        return self._candidate(row) if row else None

    @staticmethod
    def _candidate(row) -> FetchCandidate:
        return FetchCandidate(
            str(row["source_profile_id"]), row["normalized_url"], row["discovered_at"], row["discovery_cursor"],
            row["expected_media_type"], row["canonical_url"], row["metadata"], CandidateStatus(row["status"]), str(row["id"]),
        )

    def advance_candidate(self, candidate_id: str, status: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE fetch_candidates SET status=%s WHERE id=%s", (status, candidate_id))

    def task_candidates_terminal(self, source_task_id: str) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FILTER (WHERE status NOT IN ('accepted','review_required','rejected','failed','unchanged')),
                          COUNT(*) FROM fetch_candidates WHERE source_task_id=%s""",
                (source_task_id,),
            )
            pending, total = cur.fetchone()
        return total > 0 and pending == 0


class PostgresSourceCursorStore(_PostgresStore):
    def get_cursor(self, source_profile_id: str) -> SourceCursor | None:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM source_cursors WHERE source_profile_id=%s", (source_profile_id,))
            row = cur.fetchone()
        if not row:
            return None
        return SourceCursor(
            str(row["source_profile_id"]), row["cursor_value"], row["etag"], row["last_modified"],
            row["next_due_at"], row["consecutive_unchanged"], row["consecutive_failures"],
            row["circuit_open_until"], row["updated_at"],
        )

    def save_cursor(self, cursor: SourceCursor) -> SourceCursor:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO source_cursors
                   (source_profile_id,cursor_value,etag,last_modified,next_due_at,consecutive_unchanged,
                    consecutive_failures,circuit_open_until,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (source_profile_id) DO UPDATE SET cursor_value=EXCLUDED.cursor_value,
                   etag=EXCLUDED.etag,last_modified=EXCLUDED.last_modified,next_due_at=EXCLUDED.next_due_at,
                   consecutive_unchanged=EXCLUDED.consecutive_unchanged,
                   consecutive_failures=EXCLUDED.consecutive_failures,
                   circuit_open_until=EXCLUDED.circuit_open_until,updated_at=EXCLUDED.updated_at""",
                (cursor.source_profile_id, cursor.value, cursor.etag, cursor.last_modified, cursor.next_due_at,
                 cursor.consecutive_unchanged, cursor.consecutive_failures, cursor.circuit_open_until, cursor.updated_at),
            )
        return cursor


class PostgresNormalizedDocumentStore(_PostgresStore):
    def save_document(self, document: NormalizedDocument) -> NormalizedDocument:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO normalized_documents(id,artifact_id,normalizer_version,outcome,reason_codes,title,metadata,created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (artifact_id,normalizer_version) DO UPDATE SET artifact_id=EXCLUDED.artifact_id RETURNING id""",
                (document.id, document.artifact_id, document.normalizer_version, document.outcome.value,
                 document.reason_codes, document.title, psycopg2.extras.Json(document.metadata), document.created_at),
            )
            document.id = str(cur.fetchone()[0])
            for block in document.blocks:
                cur.execute(
                    """INSERT INTO content_blocks(id,normalized_document_id,block_type,block_text,ordinal,source_locator)
                       VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                    (block.id, document.id, block.block_type, block.text, block.ordinal, block.source_locator),
                )
        return document

    def find_version(self, artifact_id: str, normalizer_version: str) -> NormalizedDocument | None:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM normalized_documents WHERE artifact_id=%s AND normalizer_version=%s", (artifact_id, normalizer_version))
            row = cur.fetchone()
            if not row:
                return None
            cur.execute("SELECT * FROM content_blocks WHERE normalized_document_id=%s ORDER BY ordinal", (row["id"],))
            blocks = [ContentBlock(item["id"], item["block_type"], item["block_text"], item["ordinal"], item["source_locator"]) for item in cur.fetchall()]
        return NormalizedDocument(str(row["artifact_id"]), row["normalizer_version"], NormalizationOutcome(row["outcome"]), blocks, list(row["reason_codes"]), row["title"], row["metadata"], str(row["id"]), row["created_at"])

    def get_document(self, document_id: str) -> NormalizedDocument | None:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT artifact_id,normalizer_version FROM normalized_documents WHERE id=%s", (document_id,))
            row = cur.fetchone()
        return self.find_version(str(row["artifact_id"]), row["normalizer_version"]) if row else None
