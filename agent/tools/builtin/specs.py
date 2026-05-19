"""Builtin tool definition metadata."""
from __future__ import annotations

from dataclasses import dataclass

from agent.tools.base import BaseTool


@dataclass(frozen=True)
class ToolSpec:
    name: str
    tool_cls: type[BaseTool]
    dependencies: tuple[str, ...]
    enabled_by_default: bool = True
    tags: tuple[str, ...] = ()


class ToolDefinitionRegistry:
    """Registry of builtin tool definitions, separate from runtime tools."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"duplicate builtin tool spec: {spec.name}")
        self._specs[spec.name] = spec

    def list_specs(self, include_removed: bool = False) -> list[ToolSpec]:
        return [spec for spec in self._specs.values() if spec.enabled_by_default]

    def active_tool_names(self) -> list[str]:
        return [spec.name for spec in self.list_specs()]

    def removed_tool_names(self) -> list[str]:
        return []

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)
