"""三层记忆系统数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class MemoryType(StrEnum):
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"


class MemoryStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class CoreMemoryKind(StrEnum):
    SYSTEM_PROMPT = "system_prompt"
    TOOL_GUIDE = "tool_guide"
    SESSION_TEMPLATE = "session_template"
    FULL_COMPACT_TEMPLATE = "full_compact_template"


@dataclass
class CoreMemoryRevision:
    id: str
    kind: CoreMemoryKind
    title: str
    content: str
    version: int
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "title": self.title,
            "content": self.content,
            "version": self.version,
            "is_active": self.is_active,
            "created_at": _dt_to_iso(self.created_at),
            "updated_at": _dt_to_iso(self.updated_at),
        }


@dataclass
class PersistentMemory:
    id: str
    memory_type: MemoryType
    title: str
    summary: str
    content: str
    status: MemoryStatus = MemoryStatus.PENDING
    source_session_id: str | None = None
    confidence: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def index_line(self) -> str:
        return f"- [{self.memory_type.value}-{self.title}] - {self.summary}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "memory_type": self.memory_type.value,
            "title": self.title,
            "summary": self.summary,
            "content": self.content,
            "status": self.status.value,
            "source_session_id": self.source_session_id,
            "confidence": self.confidence,
            "index_line": self.index_line,
            "created_at": _dt_to_iso(self.created_at),
            "updated_at": _dt_to_iso(self.updated_at),
        }


@dataclass
class MemoryIndexItem:
    id: str
    memory_type: MemoryType
    title: str
    summary: str

    @property
    def line(self) -> str:
        return f"- [{self.memory_type.value}-{self.title}] - {self.summary}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "memory_type": self.memory_type.value,
            "title": self.title,
            "summary": self.summary,
            "line": self.line,
        }


def _dt_to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
