"""根据来源变化与失败历史计算下一次采集时间。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from models.collection import SourceCursor


class SourceScheduleService:
    def __init__(self, cursor_store):
        self.store = cursor_store

    def is_due(self, profile, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        cursor = self.store.get_cursor(profile.id)
        if cursor is None:
            return True
        if cursor.circuit_open_until and now < cursor.circuit_open_until:
            return False
        return cursor.next_due_at is None or now >= cursor.next_due_at

    def record_success(
        self,
        profile,
        value: str,
        *,
        changed: bool,
        now: datetime | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> SourceCursor:
        now = now or datetime.now(UTC)
        previous = self.store.get_cursor(profile.id)
        unchanged = 0 if changed else (previous.consecutive_unchanged if previous else 0) + 1
        base = int(profile.collection_config.get("base_interval_seconds", 300))
        maximum = int(profile.collection_config.get("max_interval_seconds", 86400))
        interval = base if changed else min(maximum, base * (2 ** unchanged))
        cursor = SourceCursor(
            profile.id, value,
            etag=etag or (previous.etag if previous else None),
            last_modified=last_modified or (previous.last_modified if previous else None),
            next_due_at=now + timedelta(seconds=interval),
            consecutive_unchanged=unchanged,
            consecutive_failures=0,
            circuit_open_until=None,
            updated_at=now,
        )
        return self.store.save_cursor(cursor)

    def record_failure(self, profile, *, now: datetime | None = None) -> SourceCursor:
        now = now or datetime.now(UTC)
        previous = self.store.get_cursor(profile.id)
        failures = (previous.consecutive_failures if previous else 0) + 1
        base = int(profile.collection_config.get("base_interval_seconds", 300))
        maximum = int(profile.collection_config.get("max_interval_seconds", 86400))
        delay = min(maximum, base * (2 ** failures))
        threshold = int(profile.collection_config.get("failure_threshold", 3))
        circuit_until = now + timedelta(seconds=delay) if failures >= threshold else None
        cursor = SourceCursor(
            profile.id, previous.value if previous else "",
            etag=previous.etag if previous else None,
            last_modified=previous.last_modified if previous else None,
            next_due_at=now + timedelta(seconds=delay),
            consecutive_unchanged=previous.consecutive_unchanged if previous else 0,
            consecutive_failures=failures,
            circuit_open_until=circuit_until,
            updated_at=now,
        )
        return self.store.save_cursor(cursor)
