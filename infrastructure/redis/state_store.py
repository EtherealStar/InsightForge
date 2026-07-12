"""Redis execution-time state store."""
from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

_TOKEN_BUCKET_SCRIPT = """
local now = redis.call('TIME')
local now_ms = now[1] * 1000 + math.floor(now[2] / 1000)
local values = redis.call('HMGET', KEYS[1], 'tokens', 'updated_ms')
local tokens = tonumber(values[1]) or tonumber(ARGV[2])
local updated_ms = tonumber(values[2]) or now_ms
local refill = math.max(0, now_ms - updated_ms) * tonumber(ARGV[1]) / 60000
tokens = math.min(tonumber(ARGV[2]), tokens + refill)
local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated_ms', now_ms)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return allowed
"""


JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


class RedisStateStore:
    """Redis-backed locks, hot state, idempotency keys, and event streams.

    Redis is intentionally best-effort here. If unavailable, methods degrade to
    False/None so PostgreSQL task history can remain authoritative.
    """

    def __init__(self, redis_url: str | None, client: Any | None = None):
        self.redis_url = redis_url
        self._redis = client if client is not None else self._create_client(redis_url)

    @staticmethod
    def _create_client(redis_url: str | None):
        if not redis_url:
            return None
        try:
            import redis

            client = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            client.ping()
            return client
        except Exception as e:
            logger.warning("redis_state_store.unavailable", error=str(e))
            return None

    def healthcheck(self) -> bool:
        if not self._redis:
            return False
        try:
            return bool(self._redis.ping())
        except Exception as e:
            self._degrade("healthcheck_failed", e)
            return False

    def acquire_lock(self, key: str, owner: str, ttl_seconds: int) -> bool:
        if not self._redis:
            return False
        try:
            return bool(self._redis.set(key, owner, nx=True, ex=ttl_seconds))
        except Exception as e:
            self._degrade("acquire_lock_failed", e, key=key)
            return False

    def release_lock(self, key: str, owner: str) -> bool:
        if not self._redis:
            return False
        try:
            return int(self._redis.eval(_RELEASE_LOCK_SCRIPT, 1, key, owner)) == 1
        except Exception as e:
            self._degrade("release_lock_failed", e, key=key)
            return False

    def set_json(
        self,
        key: str,
        value: JsonValue,
        ttl_seconds: int | None = None,
    ) -> bool:
        if not self._redis:
            return False
        try:
            payload = json.dumps(value, ensure_ascii=False)
            if ttl_seconds is None:
                return bool(self._redis.set(key, payload))
            return bool(self._redis.set(key, payload, ex=ttl_seconds))
        except Exception as e:
            self._degrade("set_json_failed", e, key=key)
            return False

    def get_json(self, key: str) -> JsonValue:
        if not self._redis:
            return None
        try:
            raw = self._redis.get(key)
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except Exception as e:
            self._degrade("get_json_failed", e, key=key)
            return None

    def delete(self, key: str) -> bool:
        if not self._redis:
            return False
        try:
            return int(self._redis.delete(key)) > 0
        except Exception as e:
            self._degrade("delete_failed", e, key=key)
            return False

    def set_task_status(
        self,
        run_id: str,
        status: str,
        payload: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
    ) -> bool:
        value = {
            "run_id": run_id,
            "status": status,
            "payload": payload or {},
        }
        return self.set_json(self._task_key(run_id), value, ttl_seconds=ttl_seconds)

    def get_task_status(self, run_id: str) -> dict[str, Any] | None:
        value = self.get_json(self._task_key(run_id))
        return value if isinstance(value, dict) else None

    def append_task_event(self, run_id: str, event: dict[str, Any]) -> bool:
        if not self._redis:
            return False
        try:
            payload = json.dumps(event or {}, ensure_ascii=False)
            self._redis.xadd(self._task_events_key(run_id), {"event": payload})
            return True
        except Exception as e:
            self._degrade("append_task_event_failed", e, run_id=run_id)
            return False

    def set_idempotency_key(
        self, key: str, value: str, ttl_seconds: int
    ) -> bool:
        if not self._redis:
            return False
        try:
            return bool(self._redis.set(key, value, nx=True, ex=ttl_seconds))
        except Exception as e:
            self._degrade("set_idempotency_key_failed", e, key=key)
            return False

    def get_idempotency_key(self, key: str) -> str | None:
        if not self._redis:
            return None
        try:
            value = self._redis.get(key)
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return value
        except Exception as e:
            self._degrade("get_idempotency_key_failed", e, key=key)
            return None

    def consume_token(
        self,
        key: str,
        rate_per_minute: int,
        capacity: int,
        ttl_seconds: int,
    ) -> bool:
        if not self._redis:
            return False
        try:
            return int(
                self._redis.eval(
                    _TOKEN_BUCKET_SCRIPT,
                    1,
                    key,
                    max(1, rate_per_minute),
                    max(1, capacity),
                    max(1, ttl_seconds),
                )
            ) == 1
        except Exception as e:
            self._degrade("consume_token_failed", e, key=key)
            return False

    @staticmethod
    def _task_key(run_id: str) -> str:
        return f"logos:task:{run_id}"

    @staticmethod
    def _task_events_key(run_id: str) -> str:
        return f"logos:task_events:{run_id}"

    def _degrade(self, event: str, error: Exception, **fields: Any) -> None:
        logger.warning(
            f"redis_state_store.{event}",
            error=str(error),
            **fields,
        )
        self._redis = None
