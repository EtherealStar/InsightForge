"""Application API key persistence."""
from __future__ import annotations

import psycopg2
import psycopg2.extras

from models.auth import ActorRole, ApiKeyRecord, ApiKeyStatus


class PostgresAuthStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _conn(self):
        return psycopg2.connect(self.dsn)

    def create_api_key(self, record: ApiKeyRecord) -> ApiKeyRecord:
        sql = """
            INSERT INTO api_keys
                (id, name, key_hash, role, status, created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()))
            RETURNING *
        """
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    sql,
                    (
                        record.id,
                        record.name,
                        record.key_hash,
                        _enum_value(record.role),
                        _enum_value(record.status),
                        record.created_by,
                        record.created_at,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return self._row_to_record(row)

    def get_api_key_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        sql = """
            SELECT *
            FROM api_keys
            WHERE key_hash = %s
            LIMIT 1
        """
        with self._conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (key_hash,))
                row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def update_last_used(self, key_id: str) -> None:
        sql = "UPDATE api_keys SET last_used_at = NOW() WHERE id = %s"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (key_id,))
            conn.commit()

    @staticmethod
    def _row_to_record(row: dict) -> ApiKeyRecord:
        role_val = row.get("role", ActorRole.VIEWER.value)
        status_val = row.get("status", ApiKeyStatus.ACTIVE.value)
        try:
            role = ActorRole(role_val)
        except ValueError:
            role = role_val
        try:
            status = ApiKeyStatus(status_val)
        except ValueError:
            status = status_val
        return ApiKeyRecord(
            id=row["id"],
            name=row["name"],
            key_hash=row["key_hash"],
            role=role,
            status=status,
            last_used_at=row.get("last_used_at"),
            created_by=row.get("created_by", "system") or "system",
            created_at=row.get("created_at"),
            revoked_at=row.get("revoked_at"),
        )


def _enum_value(value):
    return value.value if hasattr(value, "value") else value
