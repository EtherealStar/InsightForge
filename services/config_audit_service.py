"""Configuration audit helpers."""
from __future__ import annotations

from models.config_audit import ConfigAuditLog

SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "DSN", "BACKEND", "BROKER")


class ConfigAuditService:
    def __init__(self, store):
        self.store = store

    def diff_keys(self, before: dict[str, str], after: dict[str, str]) -> list[str]:
        keys = set(before) | set(after)
        return sorted(key for key in keys if str(before.get(key, "")) != str(after.get(key, "")))

    def mask_env(self, env: dict[str, str], keys: list[str] | None = None) -> dict[str, str]:
        selected = keys or sorted(env)
        return {key: self.mask_value(key, env.get(key, "")) for key in selected}

    def append(
        self,
        *,
        actor: str,
        action: str,
        target: str,
        before: dict[str, str],
        after: dict[str, str],
        request_id: str = "",
    ) -> ConfigAuditLog:
        changed_keys = self.diff_keys(before, after)
        log = ConfigAuditLog(
            actor=actor,
            action=action,
            target=target,
            changed_keys=changed_keys,
            before_masked=self.mask_env(before, changed_keys),
            after_masked=self.mask_env(after, changed_keys),
            request_id=request_id,
        )
        return self.store.append_config_audit(log)

    @staticmethod
    def mask_value(key: str, value: str) -> str:
        value = "" if value is None else str(value)
        if not value:
            return ""
        if any(marker in key.upper() for marker in SECRET_MARKERS):
            if len(value) <= 8:
                return "*" * len(value)
            return value[:4] + "*" * (len(value) - 8) + value[-4:]
        return value
