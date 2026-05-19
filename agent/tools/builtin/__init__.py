"""Builtin Agent tool registration."""
from __future__ import annotations

import structlog
from typing import TYPE_CHECKING

from agent.tools.builtin.definitions import create_builtin_tool_definition_registry
from agent.tools.builtin.factory import BuiltinToolFactory

if TYPE_CHECKING:
    from core.config_manager import ConfigManager

logger = structlog.get_logger(__name__)


def register_builtin_tools(
    config_manager: "ConfigManager",
    *,
    refresh: bool = True,
) -> int:
    """Register active builtin tools using ToolSpec definitions and services."""
    from agent.tools.registry import get_tool_registry

    runtime_registry = get_tool_registry()
    definition_registry = getattr(
        config_manager,
        "builtin_tool_definition_registry",
        None,
    ) or create_builtin_tool_definition_registry()
    factory = getattr(config_manager, "builtin_tool_factory", None) or BuiltinToolFactory(
        config_manager.service_registry
    )

    if refresh:
        for tool_name in definition_registry.active_tool_names():
            if runtime_registry.has(tool_name):
                try:
                    runtime_registry.unregister(tool_name)
                except Exception as exc:
                    logger.warning(
                        "builtin_tool.unregister_failed",
                        tool=tool_name,
                        error=str(exc),
                    )

    registered = 0
    for spec in definition_registry.list_specs():
        tool = factory.create(spec)
        if tool is None:
            continue
        try:
            if runtime_registry.has(tool.name):
                continue
            runtime_registry.register(tool)
            registered += 1
        except Exception as exc:
            logger.error("builtin_tool.register_failed", tool=spec.name, error=str(exc))

    logger.info("builtin_tools.registered", count=registered, refresh=refresh)
    return registered


__all__ = ["register_builtin_tools"]
