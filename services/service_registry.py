"""Service whitelist used by Agent tool factories."""
from __future__ import annotations

from typing import Any


class ServiceRegistry:
    """Small whitelist registry for service-level dependencies."""

    ALLOWED = {
        "intel_service",
        "insight_service",
        "competitor_service",
        "report_service",
        "evidence_search_service",
        "web_search_service",
    }

    def __init__(self, services: dict[str, Any]):
        invalid = set(services) - self.ALLOWED
        if invalid:
            names = ", ".join(sorted(invalid))
            raise ValueError(f"ServiceRegistry rejects non-whitelisted services: {names}")
        self._services = dict(services)

    def get(self, name: str) -> Any | None:
        if name not in self.ALLOWED:
            return None
        return self._services.get(name)

    def require(self, name: str) -> Any:
        service = self.get(name)
        if service is None:
            raise KeyError(f"Service not available or not whitelisted: {name}")
        return service

    def has(self, name: str) -> bool:
        return self.get(name) is not None
