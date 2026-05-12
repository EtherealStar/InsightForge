"""Agent 会话存储，实现 PostgreSQL 持久化 + Redis 热缓存。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg2
import structlog
from psycopg2.extras import DictCursor

from models.agent_session import AgentSession, ResearchTodo, SessionStatus

logger = structlog.get_logger(__name__)

_SESSION_CACHE_PREFIX = "logos:agent_session:"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS agent_sessions (
    id              UUID PRIMARY KEY,
    session_type    TEXT NOT NULL DEFAULT 'research_plan_execute',
    topic           TEXT NOT NULL,
    status          TEXT NOT NULL,
    messages        JSONB NOT NULL DEFAULT '[]'::jsonb,
    plan            JSONB,
    todos           JSONB NOT NULL DEFAULT '[]'::jsonb,
    events          JSONB NOT NULL DEFAULT '[]'::jsonb,
    summary         TEXT,
    summary_template TEXT,
    token_count     INTEGER NOT NULL DEFAULT 0,
    last_compacted_tokens INTEGER NOT NULL DEFAULT 0,
    compact_failures INTEGER NOT NULL DEFAULT 0,
    final_answer    TEXT,
    report_filename TEXT,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at     TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_status
    ON agent_sessions(status);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_created_at
    ON agent_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_session_type
    ON agent_sessions(session_type);

COMMENT ON TABLE agent_sessions IS 'Agent 会话记录。保存 Plan Execute 深度研究的消息、计划、todo、执行事件与最终报告索引。';
COMMENT ON COLUMN agent_sessions.id IS '会话 UUID，同时作为前端会话标识和 Agent run_id';
COMMENT ON COLUMN agent_sessions.session_type IS '会话类型，当前固定为 research_plan_execute';
COMMENT ON COLUMN agent_sessions.topic IS '用户提交的研究主题';
COMMENT ON COLUMN agent_sessions.status IS '会话状态: planned/approved/running/completed/failed/cancelled';
COMMENT ON COLUMN agent_sessions.messages IS '会话消息历史，OpenAI message 格式数组';
COMMENT ON COLUMN agent_sessions.plan IS 'AI 生成并经用户审阅的研究计划 JSON；非结构化计划保存在 raw 字段';
COMMENT ON COLUMN agent_sessions.todos IS '用户确认后的执行 todo 列表，JSONB 数组';
COMMENT ON COLUMN agent_sessions.events IS '执行过程事件，AgentEvent 序列化后的 JSONB 数组';
COMMENT ON COLUMN agent_sessions.summary IS '当前会话摘要，用于普通问答和深度研究的短期记忆注入';
COMMENT ON COLUMN agent_sessions.token_count IS '当前会话估算 token 数';
COMMENT ON COLUMN agent_sessions.last_compacted_tokens IS '上次成功摘要压缩时的估算 token 数';
COMMENT ON COLUMN agent_sessions.compact_failures IS '连续会话摘要更新失败次数';
COMMENT ON COLUMN agent_sessions.final_answer IS '最终研究报告正文副本';
COMMENT ON COLUMN agent_sessions.report_filename IS 'output/research 下生成的 Markdown 报告文件名';
COMMENT ON COLUMN agent_sessions.error IS '失败原因，仅 failed 状态使用';
COMMENT ON COLUMN agent_sessions.created_at IS '会话创建时间';
COMMENT ON COLUMN agent_sessions.updated_at IS '会话最后更新时间';
COMMENT ON COLUMN agent_sessions.approved_at IS '用户确认计划和 todo 的时间';
COMMENT ON COLUMN agent_sessions.started_at IS '执行开始时间';
COMMENT ON COLUMN agent_sessions.completed_at IS '执行结束时间';
"""

_ALTER_TABLE_SQL = """
ALTER TABLE agent_sessions
    ADD COLUMN IF NOT EXISTS summary TEXT,
    ADD COLUMN IF NOT EXISTS summary_template TEXT,
    ADD COLUMN IF NOT EXISTS token_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_compacted_tokens INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS compact_failures INTEGER NOT NULL DEFAULT 0;
"""


class AgentSessionStore:
    """PostgreSQL 会话持久化，Redis 可用时作为执行期缓存。"""

    def __init__(self, dsn: str, redis_url: str | None = None):
        self.dsn = dsn
        self.redis_url = redis_url
        self._redis = self._create_redis(redis_url)
        self._init_db()

    def _get_conn(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=DictCursor)
        conn.autocommit = True
        return conn

    def _init_db(self) -> None:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(_CREATE_TABLE_SQL)
                    cur.execute(_ALTER_TABLE_SQL)
            logger.info("agent_session_store.init_complete")
        except Exception as e:
            logger.error("agent_session_store.init_failed", error=str(e))

    @staticmethod
    def _create_redis(redis_url: str | None):
        if not redis_url:
            return None
        try:
            import redis

            client = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            client.ping()
            return client
        except Exception as e:
            logger.warning(
                "agent_session_store.redis_unavailable",
                error=str(e),
            )
            return None

    def create_session(
        self,
        topic: str,
        plan: dict[str, Any] | str | None,
        todos: list[ResearchTodo],
        messages: list[dict[str, Any]] | None = None,
    ) -> AgentSession:
        now = _utcnow()
        session = AgentSession(
            id=str(uuid.uuid4()),
            topic=topic,
            status=SessionStatus.PLANNED,
            messages=messages or [],
            plan=plan,
            todos=todos,
            created_at=now,
            updated_at=now,
        )
        self._cache_session(session)
        self._upsert_session(session)
        return session

    def create_general_session(
        self,
        topic: str,
        messages: list[dict[str, Any]] | None = None,
    ) -> AgentSession:
        now = _utcnow()
        session = AgentSession(
            id=str(uuid.uuid4()),
            session_type="general_query",
            topic=topic,
            status=SessionStatus.ACTIVE,
            messages=messages or [],
            created_at=now,
            updated_at=now,
        )
        self._cache_session(session)
        self._upsert_session(session)
        return session

    def get_session(self, session_id: str) -> AgentSession | None:
        cached = self._get_cached_session(session_id)
        if cached:
            return cached

        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM agent_sessions WHERE id = %s",
                        (session_id,),
                    )
                    row = cur.fetchone()
            if not row:
                return None
            session = self._row_to_session(row)
            self._cache_session(session)
            return session
        except Exception as e:
            logger.error(
                "agent_session_store.get_failed",
                session_id=session_id,
                error=str(e),
            )
            return None

    def save_plan(
        self,
        session_id: str,
        plan: dict[str, Any] | str,
        todos: list[ResearchTodo],
    ) -> AgentSession:
        session = self._require_session(session_id)
        session.plan = plan
        session.todos = todos
        session.status = SessionStatus.PLANNED
        session.updated_at = _utcnow()
        self._cache_session(session)
        self._upsert_session(session)
        return session

    def update_status(
        self,
        session_id: str,
        status: SessionStatus,
        error: str | None = None,
    ) -> AgentSession:
        session = self._require_session(session_id)
        now = _utcnow()
        session.status = status
        session.error = error
        session.updated_at = now
        if status == SessionStatus.APPROVED:
            session.approved_at = now
        elif status == SessionStatus.RUNNING:
            session.started_at = now
        elif status in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.CANCELLED):
            session.completed_at = now

        self._cache_session(session)
        if status in (SessionStatus.PLANNED, SessionStatus.APPROVED, SessionStatus.RUNNING):
            self._upsert_session(session)
        else:
            self._upsert_session(session)
            self.flush_session(session_id)
        return session

    def append_event(self, session_id: str, event: dict[str, Any]) -> None:
        session = self._require_session(session_id)
        session.events.append(event)
        session.updated_at = _utcnow()
        if self._redis:
            self._cache_session(session)
        else:
            self._upsert_session(session)

    def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        session = self._require_session(session_id)
        session.messages.append(message)
        session.updated_at = _utcnow()
        if self._redis:
            self._cache_session(session)
        else:
            self._upsert_session(session)

    def update_summary(
        self,
        session_id: str,
        summary: str,
        token_count: int,
        last_compacted_tokens: int,
        compact_failures: int = 0,
    ) -> AgentSession:
        session = self._require_session(session_id)
        session.summary = summary
        session.token_count = token_count
        session.last_compacted_tokens = last_compacted_tokens
        session.compact_failures = compact_failures
        session.updated_at = _utcnow()
        self._cache_session(session)
        self._upsert_session(session)
        return session

    def update_todos(
        self,
        session_id: str,
        todos: list[ResearchTodo],
    ) -> AgentSession:
        session = self._require_session(session_id)
        session.todos = todos
        session.updated_at = _utcnow()
        if self._redis:
            self._cache_session(session)
        else:
            self._upsert_session(session)
        return session

    def complete_session(
        self,
        session_id: str,
        final_answer: str,
        report_filename: str | None,
    ) -> AgentSession:
        session = self._require_session(session_id)
        now = _utcnow()
        session.status = SessionStatus.COMPLETED
        session.final_answer = final_answer
        session.report_filename = report_filename
        session.error = None
        session.completed_at = now
        session.updated_at = now
        self._cache_session(session)
        self.flush_session(session_id)
        return session

    def fail_session(self, session_id: str, error: str) -> AgentSession:
        session = self._require_session(session_id)
        now = _utcnow()
        session.status = SessionStatus.FAILED
        session.error = error
        session.completed_at = now
        session.updated_at = now
        self._cache_session(session)
        self.flush_session(session_id)
        return session

    def flush_session(self, session_id: str) -> None:
        session = self._get_cached_session(session_id) or self.get_session(session_id)
        if session:
            self._upsert_session(session)

    def _require_session(self, session_id: str) -> AgentSession:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"会话不存在: {session_id}")
        return session

    def _cache_key(self, session_id: str) -> str:
        return f"{_SESSION_CACHE_PREFIX}{session_id}"

    def _cache_session(self, session: AgentSession) -> None:
        if not self._redis:
            return
        try:
            self._redis.set(
                self._cache_key(session.id),
                json.dumps(session.to_dict(), ensure_ascii=False),
            )
        except Exception as e:
            logger.warning(
                "agent_session_store.cache_write_failed",
                session_id=session.id,
                error=str(e),
            )
            self._redis = None

    def _get_cached_session(self, session_id: str) -> AgentSession | None:
        if not self._redis:
            return None
        try:
            raw = self._redis.get(self._cache_key(session_id))
            if not raw:
                return None
            data = json.loads(raw)
            return AgentSession.from_dict(data)
        except Exception as e:
            logger.warning(
                "agent_session_store.cache_read_failed",
                session_id=session_id,
                error=str(e),
            )
            self._redis = None
            return None

    def _upsert_session(self, session: AgentSession) -> None:
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO agent_sessions
                           (id, session_type, topic, status, messages, plan, todos,
                            events, summary, summary_template, token_count,
                            last_compacted_tokens, compact_failures, final_answer,
                            report_filename, error, created_at, updated_at,
                            approved_at, started_at, completed_at)
                           VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,
                                   %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                   %s, %s, %s, %s)
                           ON CONFLICT (id) DO UPDATE SET
                               session_type = EXCLUDED.session_type,
                               topic = EXCLUDED.topic,
                               status = EXCLUDED.status,
                               messages = EXCLUDED.messages,
                               plan = EXCLUDED.plan,
                               todos = EXCLUDED.todos,
                               events = EXCLUDED.events,
                               summary = EXCLUDED.summary,
                               summary_template = EXCLUDED.summary_template,
                               token_count = EXCLUDED.token_count,
                               last_compacted_tokens = EXCLUDED.last_compacted_tokens,
                               compact_failures = EXCLUDED.compact_failures,
                               final_answer = EXCLUDED.final_answer,
                               report_filename = EXCLUDED.report_filename,
                               error = EXCLUDED.error,
                               updated_at = EXCLUDED.updated_at,
                               approved_at = EXCLUDED.approved_at,
                               started_at = EXCLUDED.started_at,
                               completed_at = EXCLUDED.completed_at""",
                        (
                            session.id,
                            session.session_type,
                            session.topic,
                            session.status.value,
                            _json(session.messages),
                            _json(_plan_to_json(session.plan)),
                            _json([todo.to_dict() for todo in session.todos]),
                            _json(session.events),
                            session.summary,
                            session.summary_template,
                            session.token_count,
                            session.last_compacted_tokens,
                            session.compact_failures,
                            session.final_answer,
                            session.report_filename,
                            session.error,
                            session.created_at or _utcnow(),
                            session.updated_at or _utcnow(),
                            session.approved_at,
                            session.started_at,
                            session.completed_at,
                        ),
                    )
        except Exception as e:
            logger.error(
                "agent_session_store.upsert_failed",
                session_id=session.id,
                error=str(e),
            )
            raise

    @staticmethod
    def _row_to_session(row: Any) -> AgentSession:
        todos = row["todos"] or []
        if isinstance(todos, str):
            todos = json.loads(todos)
        messages = row["messages"] or []
        if isinstance(messages, str):
            messages = json.loads(messages)
        events = row["events"] or []
        if isinstance(events, str):
            events = json.loads(events)
        plan = row["plan"]
        if isinstance(plan, str):
            try:
                plan = json.loads(plan)
            except json.JSONDecodeError:
                plan = {"raw": plan}

        return AgentSession(
            id=str(row["id"]),
            session_type=row["session_type"],
            topic=row["topic"],
            status=SessionStatus(row["status"]),
            messages=messages,
            plan=plan,
            todos=[ResearchTodo.from_dict(todo) for todo in todos],
            events=events,
            summary=_row_get(row, "summary"),
            summary_template=_row_get(row, "summary_template"),
            token_count=int(_row_get(row, "token_count") or 0),
            last_compacted_tokens=int(_row_get(row, "last_compacted_tokens") or 0),
            compact_failures=int(_row_get(row, "compact_failures") or 0),
            final_answer=row["final_answer"],
            report_filename=row["report_filename"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approved_at=row["approved_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _plan_to_json(plan: dict[str, Any] | str | None) -> dict[str, Any] | None:
    if plan is None or isinstance(plan, dict):
        return plan
    return {"raw": plan}


def _row_get(row: Any, key: str) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError):
        return None
