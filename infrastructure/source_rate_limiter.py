"""来源 token bucket；Redis 不可用时静态来源使用进程内保守配额。"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

from models.collection import SourceFetchPolicy


class ConservativeSourceRateLimiter:
    def __init__(self, redis_state_store=None):
        self.redis = redis_state_store
        self._lock = threading.Lock()
        self._tokens: dict[str, tuple[float, float]] = {}
        self._active = defaultdict(int)
        self._cooldowns: dict[str, float] = {}

    def acquire(self, source_profile_id: str, domain: str, policy: SourceFetchPolicy) -> bool:
        now = time.monotonic()
        if self._cooldowns.get(source_profile_id, 0) > now:
            return False
        redis_healthy = self.redis is not None and self.redis.healthcheck()
        if redis_healthy:
            if self.redis.get_json(f"logos:cooldown:source:{source_profile_id}") is not None:
                return False
            if not self.redis.consume_token(
                f"logos:rate:source:{source_profile_id}",
                policy.requests_per_minute,
                max(1, policy.requests_per_minute),
                120,
            ):
                return False
        elif self.redis is not None and (policy.render_required or policy.strict_rate_limit):
            return False
        with self._lock:
            if self._active[domain] >= policy.domain_concurrency:
                return False
            tokens, updated = self._tokens.get(source_profile_id, (1.0, now))
            refill = (now - updated) * policy.requests_per_minute / 60.0
            tokens = min(float(max(1, policy.requests_per_minute)), tokens + refill)
            if tokens < 1:
                self._tokens[source_profile_id] = (tokens, now)
                return False
            self._tokens[source_profile_id] = (tokens - 1, now)
            self._active[domain] += 1
            return True

    def release(self, source_profile_id: str, domain: str) -> None:
        with self._lock:
            self._active[domain] = max(0, self._active[domain] - 1)

    def cool_down(self, source_profile_id: str, seconds: int, reason: str) -> None:
        self._cooldowns[source_profile_id] = time.monotonic() + seconds
        if self.redis is not None and self.redis.healthcheck():
            self.redis.set_json(
                f"logos:cooldown:source:{source_profile_id}",
                {"reason": reason},
                ttl_seconds=seconds,
            )
