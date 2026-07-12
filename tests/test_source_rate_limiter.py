from models.collection import SourceFetchPolicy
from infrastructure.source_rate_limiter import ConservativeSourceRateLimiter


class RedisState:
    def __init__(self, healthy=True, allowed=True):
        self.healthy = healthy
        self.allowed = allowed
        self.calls = []
        self.values = {}

    def healthcheck(self): return self.healthy

    def consume_token(self, key, rate_per_minute, capacity, ttl_seconds):
        self.calls.append((key, rate_per_minute, capacity, ttl_seconds))
        return self.allowed

    def get_json(self, key): return self.values.get(key)
    def set_json(self, key, value, ttl_seconds=None): self.values[key] = value; return True


def test_healthy_redis_uses_distributed_source_bucket():
    redis = RedisState()
    limiter = ConservativeSourceRateLimiter(redis)
    policy = SourceFetchPolicy(requests_per_minute=12)

    assert limiter.acquire("source-1", "example.com", policy)
    limiter.release("source-1", "example.com")
    assert redis.calls[0][0] == "logos:rate:source:source-1"


def test_redis_bucket_denial_stops_fetch():
    limiter = ConservativeSourceRateLimiter(RedisState(allowed=False))
    assert not limiter.acquire("source-1", "example.com", SourceFetchPolicy())


def test_redis_loss_allows_conservative_static_but_pauses_browser_and_strict_source():
    limiter = ConservativeSourceRateLimiter(RedisState(healthy=False))
    assert limiter.acquire("source-1", "example.com", SourceFetchPolicy())
    limiter.release("source-1", "example.com")
    assert not limiter.acquire("source-2", "example.org", SourceFetchPolicy(render_required=True))
    assert not limiter.acquire("source-3", "example.net", SourceFetchPolicy(strict_rate_limit=True))


def test_cooldown_is_shared_through_redis():
    redis = RedisState()
    first = ConservativeSourceRateLimiter(redis)
    first.cool_down("source-1", 60, "http_429")

    second = ConservativeSourceRateLimiter(redis)
    assert not second.acquire("source-1", "example.com", SourceFetchPolicy())
