from infrastructure.redis.dedup_cache import RedisDedupCache
from models.document_governance import SimHashFingerprint, SourceOccurrence


class FakeRedis:
    def __init__(self):
        self.strings = {}
        self.sets = {}

    def get(self, key):
        return self.strings.get(key)

    def set(self, key, value):
        self.strings[key] = value
        return True

    def sadd(self, key, *values):
        self.sets.setdefault(key, set()).update(values)
        return len(values)

    def smembers(self, key):
        return self.sets.get(key, set())

    def scan_iter(self, match):
        prefix = match.removesuffix("*")
        return iter([key for key in (*self.strings, *self.sets) if key.startswith(prefix)])

    def delete(self, *keys):
        for key in keys:
            self.strings.pop(key, None)
            self.sets.pop(key, None)
        return len(keys)


def _occurrence() -> SourceOccurrence:
    return SourceOccurrence(
        document_id="cluster-1",
        url="https://example.com/article",
        normalized_url="https://example.com/article",
        title="Article",
        content_hash="abc123",
        simhash=SimHashFingerprint(42, (1, 2, 3, 4), (1, 2, 3, 4, 5, 6, 7, 8)),
    )


def test_cache_indexes_exact_url_and_bands_and_can_be_cleared():
    cache = RedisDedupCache(redis_url=None, client=FakeRedis())
    occurrence = _occurrence()

    cache.index_occurrence(occurrence)

    assert cache.find_exact("abc123") == ["cluster-1"]
    assert cache.find_url("https://example.com/article") == "cluster-1"
    assert cache.find_by_bands(occurrence.simhash) == ["cluster-1"]
    assert cache.clear() > 0
    assert cache.find_exact("abc123") == []


class FailingRedis:
    def __getattr__(self, name):
        raise RuntimeError("redis unavailable")


def test_cache_failure_is_a_miss_not_a_deduplication_decision():
    cache = RedisDedupCache(redis_url=None, client=FailingRedis())
    occurrence = _occurrence()

    assert cache.find_exact(occurrence.content_hash) == []
    assert cache.find_by_bands(occurrence.simhash) == []
    assert cache.index_occurrence(occurrence) is False
