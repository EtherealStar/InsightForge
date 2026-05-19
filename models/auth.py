"""Authentication domain models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import uuid4


class ActorRole(str, Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMIN = "admin"


class ApiKeyStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass
class ApiKeyRecord:
    name: str
    key_hash: str
    role: ActorRole | str = ActorRole.VIEWER
    status: ApiKeyStatus | str = ApiKeyStatus.ACTIVE
    id: str = ""
    last_used_at: datetime | None = None
    created_by: str = "system"
    created_at: datetime | None = None
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid4())
