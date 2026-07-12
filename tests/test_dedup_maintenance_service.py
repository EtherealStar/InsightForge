import pytest

from services.dedup_maintenance_service import DedupMaintenanceService


class Store:
    def __init__(self, occurrences):
        self.occurrences = occurrences

    def list_occurrences(self, *, limit=1000, offset=0):
        return self.occurrences[offset : offset + limit]


class Cache:
    def __init__(self):
        self.items = []

    def clear(self):
        self.items.clear()
        return 4

    def index_occurrence(self, occurrence):
        self.items.append(occurrence)
        return occurrence != "bad"


def test_rebuild_cache_is_batched_and_reports_failures():
    cache = Cache()
    result = DedupMaintenanceService(Store(["a", "bad", "c"]), cache).rebuild_cache(batch_size=2)

    assert cache.items == ["a", "bad", "c"]
    assert result == {"deleted_keys": 4, "indexed": 2, "failed": 1}


def test_rebuild_cache_rejects_invalid_batch_size():
    with pytest.raises(ValueError, match="batch_size must be positive"):
        DedupMaintenanceService(Store([]), Cache()).rebuild_cache(batch_size=0)
