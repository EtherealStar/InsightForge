"""Configuration audit persistence."""
from __future__ import annotations

import json

import psycopg2
import psycopg2.extras

from models.config_audit import ConfigAuditLog


class PostgresConfigAuditStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        return psycopg2.connect(self.dsn)

    def append_config_audit(self, log: ConfigAuditLog) -> ConfigAuditLog:
        sql = """
            INSERT INTO config_audit_log
                (actor, action, target, changed_keys, before_masked,
                 after_masked, request_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()))
            RETURNING id, created_at
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        log.actor,
                        log.action,
                        log.target,
                        json.dumps(log.changed_keys, ensure_ascii=False),
                        json.dumps(log.before_masked, ensure_ascii=False),
                        json.dumps(log.after_masked, ensure_ascii=False),
                        log.request_id,
                        log.created_at,
                    ),
                )
                row = cur.fetchone()
                log.id = row[0]
                log.created_at = row[1]
            conn.commit()
        return log

    def list_config_audit(
        self,
        *,
        target: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConfigAuditLog]:
        conditions = []
        params: list = []
        if target:
            conditions.append("target = %s")
            params.append(target)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT *
            FROM config_audit_log
            {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [self._row_to_log(row) for row in rows]

    @staticmethod
    def _row_to_log(row: dict) -> ConfigAuditLog:
        return ConfigAuditLog(
            id=row["id"],
            actor=row["actor"],
            action=row["action"],
            target=row["target"],
            changed_keys=_json_loads(row.get("changed_keys", []), []),
            before_masked=_json_loads(row.get("before_masked", {}), {}),
            after_masked=_json_loads(row.get("after_masked", {}), {}),
            request_id=row.get("request_id", "") or "",
            created_at=row.get("created_at"),
        )


def _json_loads(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        return json.loads(value or json.dumps(default))
    return value
