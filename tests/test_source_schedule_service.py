from datetime import UTC, datetime, timedelta

from models.collection import SourceCursor
from models.source_governance import SourceProfile
from services.source_schedule_service import SourceScheduleService


class CursorStore:
    def __init__(self): self.values = {}
    def get_cursor(self, profile_id): return self.values.get(profile_id)
    def save_cursor(self, cursor): self.values[cursor.source_profile_id] = cursor; return cursor


NOW = datetime(2026, 7, 13, tzinfo=UTC)


def profile():
    return SourceProfile(
        "example.com", id="source-1",
        collection_config={"base_interval_seconds": 300, "max_interval_seconds": 3600, "failure_threshold": 3},
    )


def test_unchanged_source_backs_off_and_changed_source_returns_to_baseline():
    store = CursorStore()
    service = SourceScheduleService(store)

    first = service.record_success(profile(), "cursor-1", changed=False, now=NOW)
    second = service.record_success(profile(), "cursor-1", changed=False, now=NOW)
    changed = service.record_success(profile(), "cursor-2", changed=True, now=NOW)

    assert first.next_due_at == NOW + timedelta(seconds=600)
    assert second.next_due_at == NOW + timedelta(seconds=1200)
    assert changed.next_due_at == NOW + timedelta(seconds=300)
    assert changed.consecutive_unchanged == 0


def test_failures_back_off_and_open_circuit_at_threshold():
    store = CursorStore()
    service = SourceScheduleService(store)

    service.record_failure(profile(), now=NOW)
    service.record_failure(profile(), now=NOW)
    third = service.record_failure(profile(), now=NOW)

    assert third.consecutive_failures == 3
    assert third.circuit_open_until is not None
    assert not service.is_due(profile(), NOW + timedelta(minutes=1))
    assert service.is_due(profile(), third.circuit_open_until)
