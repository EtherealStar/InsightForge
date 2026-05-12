"""AgentSessionStore PostgreSQL 测试。"""

import os

import psycopg2
import pytest

from infrastructure.agent_session_store import AgentSessionStore
from models.agent_session import ResearchTodo


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_PG_DSN"),
    reason="Requires PostgreSQL instance",
)


def test_agent_session_store_persists_without_redis(test_dsn):
    store = AgentSessionStore(test_dsn, redis_url=None)

    session = store.create_session(
        topic="AI",
        plan={"goal": "研究AI"},
        todos=[ResearchTodo(id="todo-1", title="检索资料")],
    )
    store.append_event(session.id, {"event_type": "thought", "content": "t"})
    loaded = store.get_session(session.id)

    assert loaded is not None
    assert loaded.plan["goal"] == "研究AI"
    assert loaded.todos[0].title == "检索资料"
    assert loaded.events[0]["event_type"] == "thought"


def test_agent_session_table_has_tbls_comments(test_dsn):
    AgentSessionStore(test_dsn, redis_url=None)

    with psycopg2.connect(test_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT obj_description('agent_sessions'::regclass, 'pg_class')"""
            )
            table_comment = cur.fetchone()[0]
            cur.execute(
                """SELECT col_description('agent_sessions'::regclass, attnum)
                   FROM pg_attribute
                   WHERE attrelid = 'agent_sessions'::regclass
                     AND attname = 'plan'"""
            )
            plan_comment = cur.fetchone()[0]

    assert "Agent 会话记录" in table_comment
    assert "研究计划" in plan_comment
