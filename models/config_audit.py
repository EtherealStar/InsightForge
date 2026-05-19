"""Configuration audit domain model."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ConfigAuditLog:
    actor: str
    action: str
    target: str
    changed_keys: list[str] = field(default_factory=list)
    before_masked: dict = field(default_factory=dict)
    after_masked: dict = field(default_factory=dict)
    request_id: str = ""
    id: int | None = None
    created_at: datetime | None = None
