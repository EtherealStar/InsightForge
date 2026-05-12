"""三层记忆系统 PostgreSQL 存储。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg2
import structlog
from psycopg2.extras import DictCursor

from models.memory import (
    CoreMemoryKind,
    CoreMemoryRevision,
    MemoryIndexItem,
    MemoryStatus,
    MemoryType,
    PersistentMemory,
)

logger = structlog.get_logger(__name__)

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS core_memory_revisions (
    id          UUID PRIMARY KEY,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    version     INTEGER NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_core_memory_kind_active
    ON core_memory_revisions(kind, is_active);

CREATE TABLE IF NOT EXISTS persistent_memories (
    id                UUID PRIMARY KEY,
    memory_type       TEXT NOT NULL,
    title             TEXT NOT NULL,
    summary           TEXT NOT NULL,
    content           TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    source_session_id UUID,
    confidence        DOUBLE PRECISION,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_persistent_memories_status
    ON persistent_memories(status);
CREATE INDEX IF NOT EXISTS idx_persistent_memories_type_status
    ON persistent_memories(memory_type, status);

COMMENT ON TABLE core_memory_revisions IS '核心记忆版本表。核心记忆不可物理删除，只能创建新版本并切换 active revision。';
COMMENT ON TABLE persistent_memories IS '持久记忆表。保存 user/feedback/project 三类跨会话记忆，pending 状态需用户确认。';
COMMENT ON COLUMN persistent_memories.summary IS 'MEMORY 索引行使用的短摘要，建议 50 token 以内';
"""


class MemoryStore:
    """PostgreSQL 权威记忆存储。"""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._init_db()

    def _get_conn(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=DictCursor)
        conn.autocommit = True
        return conn

    def _init_db(self) -> None:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(_CREATE_TABLES_SQL)
            logger.info("memory_store.init_complete")
        except Exception as e:
            logger.error("memory_store.init_failed", error=str(e))

    def get_active_core_memories(
        self,
        kind: str | None = None,
    ) -> list[CoreMemoryRevision]:
        sql = "SELECT * FROM core_memory_revisions WHERE is_active = TRUE"
        params: tuple[Any, ...] = ()
        if kind:
            sql += " AND kind = %s"
            params = (kind,)
        sql += " ORDER BY kind, version DESC, updated_at DESC"
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [self._row_to_core(row) for row in cur.fetchall()]

    def create_core_memory_revision(
        self,
        kind: str,
        title: str,
        content: str,
    ) -> CoreMemoryRevision:
        memory_kind = CoreMemoryKind(kind)
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM core_memory_revisions WHERE kind = %s",
                    (memory_kind.value,),
                )
                version = int(cur.fetchone()[0])
                cur.execute(
                    "UPDATE core_memory_revisions SET is_active = FALSE WHERE kind = %s",
                    (memory_kind.value,),
                )
                item = CoreMemoryRevision(
                    id=str(uuid.uuid4()),
                    kind=memory_kind,
                    title=title,
                    content=content,
                    version=version,
                    is_active=True,
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
                cur.execute(
                    """INSERT INTO core_memory_revisions
                       (id, kind, title, content, version, is_active, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        item.id,
                        item.kind.value,
                        item.title,
                        item.content,
                        item.version,
                        item.is_active,
                        item.created_at,
                        item.updated_at,
                    ),
                )
                return item

    def list_memory_index(
        self,
        memory_types: list[MemoryType] | None = None,
    ) -> list[MemoryIndexItem]:
        items = self.list_persistent_memories(status=MemoryStatus.ACTIVE)
        if memory_types:
            allowed = set(memory_types)
            items = [item for item in items if item.memory_type in allowed]
        return [
            MemoryIndexItem(
                id=item.id,
                memory_type=item.memory_type,
                title=item.title,
                summary=item.summary,
            )
            for item in items
        ]

    def list_persistent_memories(
        self,
        status: MemoryStatus | None = None,
        memory_type: MemoryType | None = None,
    ) -> list[PersistentMemory]:
        sql = "SELECT * FROM persistent_memories WHERE status <> 'deleted'"
        params: list[Any] = []
        if status:
            sql += " AND status = %s"
            params.append(status.value)
        if memory_type:
            sql += " AND memory_type = %s"
            params.append(memory_type.value)
        sql += " ORDER BY updated_at DESC"
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                return [self._row_to_persistent(row) for row in cur.fetchall()]

    def get_persistent_memory(self, memory_id: str) -> PersistentMemory | None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM persistent_memories WHERE id = %s", (memory_id,))
                row = cur.fetchone()
        return self._row_to_persistent(row) if row else None

    def create_persistent_memory(
        self,
        memory_type: MemoryType,
        title: str,
        summary: str,
        content: str,
        source_session_id: str | None = None,
        confidence: float | None = None,
        status: MemoryStatus = MemoryStatus.PENDING,
    ) -> PersistentMemory:
        item = PersistentMemory(
            id=str(uuid.uuid4()),
            memory_type=memory_type,
            title=title,
            summary=summary,
            content=content,
            status=status,
            source_session_id=source_session_id,
            confidence=confidence,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO persistent_memories
                       (id, memory_type, title, summary, content, status,
                        source_session_id, confidence, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        item.id,
                        item.memory_type.value,
                        item.title,
                        item.summary,
                        item.content,
                        item.status.value,
                        item.source_session_id,
                        item.confidence,
                        item.created_at,
                        item.updated_at,
                    ),
                )
        return item

    def update_persistent_memory_status(
        self,
        memory_id: str,
        status: MemoryStatus,
    ) -> PersistentMemory:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE persistent_memories
                       SET status = %s, updated_at = %s
                       WHERE id = %s
                       RETURNING *""",
                    (status.value, _utcnow(), memory_id),
                )
                row = cur.fetchone()
        if not row:
            raise ValueError(f"记忆不存在: {memory_id}")
        return self._row_to_persistent(row)

    def delete_persistent_memory(self, memory_id: str) -> None:
        self.update_persistent_memory_status(memory_id, MemoryStatus.DELETED)

    @staticmethod
    def _row_to_core(row: Any) -> CoreMemoryRevision:
        return CoreMemoryRevision(
            id=str(row["id"]),
            kind=CoreMemoryKind(row["kind"]),
            title=row["title"],
            content=row["content"],
            version=row["version"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_persistent(row: Any) -> PersistentMemory:
        return PersistentMemory(
            id=str(row["id"]),
            memory_type=MemoryType(row["memory_type"]),
            title=row["title"],
            summary=row["summary"],
            content=row["content"],
            status=MemoryStatus(row["status"]),
            source_session_id=str(row["source_session_id"]) if row["source_session_id"] else None,
            confidence=row["confidence"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
