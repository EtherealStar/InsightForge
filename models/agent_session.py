"""Agent 会话数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class SessionStatus(StrEnum):
    """Agent 会话状态。"""

    ACTIVE = "active"
    PLANNED = "planned"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ResearchTodo:
    """深度研究执行 todo。"""

    id: str
    title: str
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchTodo":
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or data.get("content") or ""),
            status=str(data.get("status") or "pending"),
        )


@dataclass
class AgentSession:
    """Agent 会话记录。"""

    id: str
    topic: str
    status: SessionStatus = SessionStatus.PLANNED
    session_type: str = "research_plan_execute"
    messages: list[dict[str, Any]] = field(default_factory=list)
    plan: dict[str, Any] | str | None = None
    todos: list[ResearchTodo] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    summary: str | None = None
    summary_template: str | None = None
    token_count: int = 0
    last_compacted_tokens: int = 0
    compact_failures: int = 0
    final_answer: str | None = None
    report_filename: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    approved_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.id,
            "session_type": self.session_type,
            "topic": self.topic,
            "status": self.status.value,
            "messages": self.messages,
            "plan": self.plan,
            "todos": [todo.to_dict() for todo in self.todos],
            "events": self.events,
            "summary": self.summary,
            "summary_template": self.summary_template,
            "token_count": self.token_count,
            "last_compacted_tokens": self.last_compacted_tokens,
            "compact_failures": self.compact_failures,
            "final_answer": self.final_answer,
            "report_filename": self.report_filename,
            "error": self.error,
            "created_at": _dt_to_iso(self.created_at),
            "updated_at": _dt_to_iso(self.updated_at),
            "approved_at": _dt_to_iso(self.approved_at),
            "started_at": _dt_to_iso(self.started_at),
            "completed_at": _dt_to_iso(self.completed_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentSession":
        return cls(
            id=str(data.get("id") or data.get("session_id") or ""),
            session_type=str(data.get("session_type") or "research_plan_execute"),
            topic=str(data.get("topic") or ""),
            status=SessionStatus(str(data.get("status") or SessionStatus.PLANNED)),
            messages=list(data.get("messages") or []),
            plan=data.get("plan"),
            todos=[
                ResearchTodo.from_dict(todo)
                for todo in data.get("todos") or []
                if isinstance(todo, dict)
            ],
            events=list(data.get("events") or []),
            summary=data.get("summary"),
            summary_template=data.get("summary_template"),
            token_count=int(data.get("token_count") or 0),
            last_compacted_tokens=int(data.get("last_compacted_tokens") or 0),
            compact_failures=int(data.get("compact_failures") or 0),
            final_answer=data.get("final_answer"),
            report_filename=data.get("report_filename"),
            error=data.get("error"),
            created_at=_parse_dt(data.get("created_at")),
            updated_at=_parse_dt(data.get("updated_at")),
            approved_at=_parse_dt(data.get("approved_at")),
            started_at=_parse_dt(data.get("started_at")),
            completed_at=_parse_dt(data.get("completed_at")),
        )


def _dt_to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_dt(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None
