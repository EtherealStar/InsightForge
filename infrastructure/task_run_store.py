"""PostgreSQL task run history store."""
from __future__ import annotations

import json
from typing import Any

import psycopg2
import structlog
from psycopg2.extras import DictCursor, Json

from core.exceptions import StoreError
from models.task_run import TaskEvent, TaskRun, TaskStage, TaskStatus, new_task_id

logger = structlog.get_logger(__name__)


class PostgresTaskRunStore:
    """Durable task run, stage, and event store.

    Schema is owned by migrations. This class only checks connectivity and
    performs CRUD against task_runs, task_stages, and task_events.
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.healthcheck()

    def _get_conn(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=DictCursor)
        conn.autocommit = True
        return conn

    def healthcheck(self) -> bool:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return True
        except Exception as e:
            raise StoreError(f"PostgreSQL task run store unavailable: {e}") from e

    def create_run(
        self,
        task_type: str,
        input: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> TaskRun:
        run_id = new_task_id()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO task_runs (
                            id, task_type, status, idempotency_key, input
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            run_id,
                            task_type,
                            TaskStatus.PENDING.value,
                            idempotency_key,
                            Json(input or {}),
                        ),
                    )
                    row = cur.fetchone()
            logger.info("task_run.created", run_id=run_id, task_type=task_type)
            return self._row_to_run(row)
        except Exception as e:
            logger.error("task_run.create_failed", task_type=task_type, error=str(e))
            raise StoreError(f"Failed to create task run: {e}") from e

    def start_run(self, run_id: str) -> TaskRun:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE task_runs
                        SET status = %s,
                            started_at = COALESCE(started_at, NOW()),
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (TaskStatus.RUNNING.value, run_id),
                    )
                    row = cur.fetchone()
            if not row:
                raise StoreError(f"Task run not found: {run_id}")
            return self._row_to_run(row)
        except StoreError:
            raise
        except Exception as e:
            logger.error("task_run.start_failed", run_id=run_id, error=str(e))
            raise StoreError(f"Failed to start task run {run_id}: {e}") from e

    def finish_run(
        self,
        run_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> TaskRun:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE task_runs
                        SET status = %s,
                            result = %s,
                            error = %s,
                            finished_at = NOW(),
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (status, Json(result or {}), Json(error or {}), run_id),
                    )
                    row = cur.fetchone()
            if not row:
                raise StoreError(f"Task run not found: {run_id}")
            return self._row_to_run(row)
        except StoreError:
            raise
        except Exception as e:
            logger.error("task_run.finish_failed", run_id=run_id, error=str(e))
            raise StoreError(f"Failed to finish task run {run_id}: {e}") from e

    def create_stage(self, run_id: str, name: str) -> TaskStage:
        stage_id = new_task_id()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO task_stages (
                            id, task_run_id, name, status, started_at
                        )
                        VALUES (%s, %s, %s, %s, NOW())
                        RETURNING *
                        """,
                        (stage_id, run_id, name, TaskStatus.RUNNING.value),
                    )
                    row = cur.fetchone()
                    cur.execute(
                        "UPDATE task_runs SET updated_at = NOW() WHERE id = %s",
                        (run_id,),
                    )
            logger.info("task_stage.created", run_id=run_id, stage_id=stage_id, name=name)
            return self._row_to_stage(row)
        except Exception as e:
            logger.error(
                "task_stage.create_failed",
                run_id=run_id,
                name=name,
                error=str(e),
            )
            raise StoreError(f"Failed to create task stage: {e}") from e

    def finish_stage(
        self,
        stage_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> TaskStage:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE task_stages
                        SET status = %s,
                            result = %s,
                            error = %s,
                            finished_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (status, Json(result or {}), Json(error or {}), stage_id),
                    )
                    row = cur.fetchone()
                    if row:
                        cur.execute(
                            "UPDATE task_runs SET updated_at = NOW() WHERE id = %s",
                            (row["task_run_id"],),
                        )
            if not row:
                raise StoreError(f"Task stage not found: {stage_id}")
            return self._row_to_stage(row)
        except StoreError:
            raise
        except Exception as e:
            logger.error("task_stage.finish_failed", stage_id=stage_id, error=str(e))
            raise StoreError(f"Failed to finish task stage {stage_id}: {e}") from e

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        stage_id: str | None = None,
    ) -> TaskEvent:
        event_id = new_task_id()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO task_events (
                            id, task_run_id, stage_id, event_type, payload
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (event_id, run_id, stage_id, event_type, Json(payload or {})),
                    )
                    row = cur.fetchone()
                    cur.execute(
                        "UPDATE task_runs SET updated_at = NOW() WHERE id = %s",
                        (run_id,),
                    )
            return self._row_to_event(row)
        except Exception as e:
            logger.error(
                "task_event.append_failed",
                run_id=run_id,
                event_type=event_type,
                error=str(e),
            )
            raise StoreError(f"Failed to append task event: {e}") from e

    def get_run(self, run_id: str) -> TaskRun | None:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM task_runs WHERE id = %s", (run_id,))
                    row = cur.fetchone()
            return self._row_to_run(row) if row else None
        except Exception as e:
            logger.error("task_run.get_failed", run_id=run_id, error=str(e))
            raise StoreError(f"Failed to get task run {run_id}: {e}") from e

    def list_runs(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TaskRun], int]:
        filters = filters or {}
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        where: list[str] = []
        params: list[Any] = []

        if filters.get("task_type"):
            where.append("task_type = %s")
            params.append(filters["task_type"])
        if filters.get("status"):
            where.append("status = %s")
            params.append(filters["status"])
        if filters.get("date_from"):
            where.append("created_at >= %s")
            params.append(filters["date_from"])
        if filters.get("date_to"):
            where.append("created_at <= %s")
            params.append(filters["date_to"])
        if filters.get("actor"):
            where.append(
                "(input->>'actor' = %s OR input->>'triggered_by' = %s OR input->>'created_by' = %s)"
            )
            params.extend([filters["actor"], filters["actor"], filters["actor"]])

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) FROM task_runs {where_sql}", params)
                    total = int(cur.fetchone()[0])
                    cur.execute(
                        f"""
                        SELECT *
                        FROM task_runs
                        {where_sql}
                        ORDER BY created_at DESC, id DESC
                        LIMIT %s OFFSET %s
                        """,
                        [*params, limit, offset],
                    )
                    rows = cur.fetchall()
            return [self._row_to_run(row) for row in rows], total
        except Exception as e:
            logger.error("task_run.list_failed", filters=filters, error=str(e))
            raise StoreError(f"Failed to list task runs: {e}") from e

    def list_stages(self, run_id: str) -> list[TaskStage]:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT *
                        FROM task_stages
                        WHERE task_run_id = %s
                        ORDER BY created_at ASC, id ASC
                        """,
                        (run_id,),
                    )
                    rows = cur.fetchall()
            return [self._row_to_stage(row) for row in rows]
        except Exception as e:
            logger.error("task_stage.list_failed", run_id=run_id, error=str(e))
            raise StoreError(f"Failed to list task stages for {run_id}: {e}") from e

    def list_events(self, run_id: str, limit: int = 200) -> list[TaskEvent]:
        limit = max(1, min(int(limit), 1000))
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT *
                        FROM task_events
                        WHERE task_run_id = %s
                        ORDER BY created_at ASC, id ASC
                        LIMIT %s
                        """,
                        (run_id, limit),
                    )
                    rows = cur.fetchall()
            return [self._row_to_event(row) for row in rows]
        except Exception as e:
            logger.error("task_event.list_failed", run_id=run_id, error=str(e))
            raise StoreError(f"Failed to list task events for {run_id}: {e}") from e

    @staticmethod
    def _json_value(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return json.loads(value) if value else {}
        return dict(value)

    @classmethod
    def _row_to_run(cls, row) -> TaskRun:
        return TaskRun(
            id=str(row["id"]),
            task_type=row["task_type"],
            status=row["status"],
            idempotency_key=row["idempotency_key"],
            input=cls._json_value(row["input"]),
            result=cls._json_value(row["result"]),
            error=cls._json_value(row["error"]),
            attempt=row["attempt"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    @classmethod
    def _row_to_stage(cls, row) -> TaskStage:
        return TaskStage(
            id=str(row["id"]),
            task_run_id=str(row["task_run_id"]),
            name=row["name"],
            status=row["status"],
            result=cls._json_value(row["result"]),
            error=cls._json_value(row["error"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            created_at=row["created_at"],
        )

    @classmethod
    def _row_to_event(cls, row) -> TaskEvent:
        return TaskEvent(
            id=str(row["id"]),
            task_run_id=str(row["task_run_id"]),
            stage_id=str(row["stage_id"]) if row["stage_id"] else None,
            event_type=row["event_type"],
            payload=cls._json_value(row["payload"]),
            created_at=row["created_at"],
        )
