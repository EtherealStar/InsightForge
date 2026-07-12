"""Redis 去重热点索引；任何异常都降级为缓存未命中。"""
from __future__ import annotations

from typing import Any

import structlog

from models.document_governance import SimHashFingerprint, SourceOccurrence

logger = structlog.get_logger()


class RedisDedupCache:
    PREFIX = "dedup:v1:"

    def __init__(self, redis_url: str | None, client: Any | None = None):
        self._redis = client if client is not None else self._create_client(redis_url)

    @staticmethod
    def _create_client(redis_url: str | None):
        if not redis_url:
            return None
        try:
            import redis

            client = redis.Redis.from_url(redis_url, decode_responses=True)
            client.ping()
            return client
        except Exception as exc:
            logger.warning("dedup_cache.unavailable", error=str(exc))
            return None

    @staticmethod
    def _text(value: Any) -> str:
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    def find_url(self, normalized_url: str) -> str | None:
        value = self._call("get", f"{self.PREFIX}url:{normalized_url}")
        return self._text(value) if value is not None else None

    def find_exact(self, content_hash: str) -> list[str]:
        return self._members(f"{self.PREFIX}hash:{content_hash}")

    def find_by_bands(self, fingerprint: SimHashFingerprint) -> list[str]:
        keys = self._band_keys(fingerprint)
        values: set[str] = set()
        for key in keys:
            values.update(self._members(key))
        return sorted(values)

    def index_occurrence(self, occurrence: SourceOccurrence) -> bool:
        if not self._redis:
            return False
        try:
            self._redis.set(f"{self.PREFIX}url:{occurrence.normalized_url}", occurrence.document_id)
            self._redis.sadd(f"{self.PREFIX}hash:{occurrence.content_hash}", occurrence.document_id)
            for key in self._band_keys(occurrence.simhash):
                self._redis.sadd(key, occurrence.document_id)
            return True
        except Exception as exc:
            logger.warning("dedup_cache.write_failed", error=str(exc))
            return False

    def clear(self) -> int:
        if not self._redis:
            return 0
        try:
            keys = list(self._redis.scan_iter(match=f"{self.PREFIX}*"))
            return int(self._redis.delete(*keys)) if keys else 0
        except Exception as exc:
            logger.warning("dedup_cache.clear_failed", error=str(exc))
            return 0

    def _members(self, key: str) -> list[str]:
        values = self._call("smembers", key) or []
        return sorted(self._text(value) for value in values)

    def _call(self, method: str, *args):
        if not self._redis:
            return None
        try:
            return getattr(self._redis, method)(*args)
        except Exception as exc:
            logger.warning("dedup_cache.read_failed", operation=method, error=str(exc))
            return None

    def _band_keys(self, fingerprint: SimHashFingerprint) -> list[str]:
        version = fingerprint.algorithm_version
        high = [f"{self.PREFIX}band:{version}:h:{index}:{value}" for index, value in enumerate(fingerprint.high_bands)]
        gray = [f"{self.PREFIX}band:{version}:g:{index}:{value}" for index, value in enumerate(fingerprint.gray_bands)]
        return high + gray
