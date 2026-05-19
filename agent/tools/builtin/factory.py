"""Factory for builtin Agent tools."""
from __future__ import annotations

import structlog

from agent.tools.base import BaseTool
from agent.tools.builtin.specs import ToolSpec
from services.service_registry import ServiceRegistry

logger = structlog.get_logger(__name__)


class BuiltinToolFactory:
    """Create builtin tools from service-level dependencies only."""

    def __init__(self, service_registry: ServiceRegistry):
        self.service_registry = service_registry

    def create(self, spec: ToolSpec) -> BaseTool | None:
        if not spec.enabled_by_default:
            return None
        missing = [name for name in spec.dependencies if not self.service_registry.has(name)]
        if missing:
            logger.warning(
                "builtin_tool.skipped_missing_dependencies",
                tool=spec.name,
                dependencies=missing,
            )
            return None
        deps = [self.service_registry.require(name) for name in spec.dependencies]
        return spec.tool_cls(*deps)
