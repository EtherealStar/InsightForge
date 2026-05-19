"""Formatting helpers for builtin tools."""
from __future__ import annotations

from enum import Enum
from typing import Any


def enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def obj_value(obj: Any, name: str, default: Any = "") -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def truncate(text: Any, limit: int = 500) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def format_fact_item(fact: dict[str, Any], index: int | None = None) -> str:
    prefix = f"{index}. " if index is not None else ""
    event_date = fact.get("event_date") or "unknown date"
    evidence_count = len(fact.get("evidence_refs") or [])
    competitors = fact.get("competitor_ids") or []
    products = fact.get("product_ids") or []
    return (
        f"{prefix}**{fact.get('fact_text', '')}**\n"
        f"   ID: {fact.get('id')} | type: {fact.get('fact_type')} | "
        f"dimension: {fact.get('dimension')} | status: {fact.get('status')}\n"
        f"   date: {event_date} | confidence: {fact.get('confidence_score', 0)} | "
        f"importance: {fact.get('importance_score', 0)}\n"
        f"   competitors: {competitors or '-'} | products: {products or '-'} | "
        f"evidence: {evidence_count}"
    )
