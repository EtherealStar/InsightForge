"""Versioned registry of normalized fact schemas (Milestone 3).

First version ships ``commercial.pricing.v1``. Unknown schemas, mismatched
``fact_type``, or invalid payloads cause the fact to remain in draft with a
``status_reason`` describing the failure; they do not raise to the caller.

Each schema declares:
  * ``fact_types``: which top-level fact_type values may carry the payload
  * ``required`` / ``optional`` field lists
  * ``enums``: dict of field → allowed values
  * ``validator(payload) -> tuple[bool, str]``: optional cross-field checks

Payloads are dicts that may carry extra fields; validators should ignore
unknown keys. The registry is the only place where pricing / market /
billing period shape lives — plain feature facts do not go through it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class NormalizedSchema:
    name: str
    fact_types: tuple[str, ...]
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()
    enums: dict[str, tuple[str, ...]] = field(default_factory=dict)
    validator: Callable[[dict[str, Any]], tuple[bool, str]] | None = None


def _validate_pricing(payload: dict[str, Any]) -> tuple[bool, str]:
    """Cross-field pricing validation.

    Returns ``(True, "")`` on success, ``(False, reason)`` on failure.
    """
    billing = payload.get("billing_period")
    if billing and billing not in {"month", "year", "one_time", "week"}:
        return False, f"unknown billing_period: {billing}"
    market = payload.get("market")
    if market is not None and (not isinstance(market, str) or not market.strip()):
        return False, "market must be a non-empty string"
    currency = payload.get("currency")
    if currency and not isinstance(currency, str) or (currency and len(currency) != 3):
        return False, "currency must be ISO-4217 3-letter code"
    amount = payload.get("amount")
    if not isinstance(amount, (int, float)) or amount < 0:
        return False, "amount must be a non-negative number"
    return True, ""


PRICING_V1 = NormalizedSchema(
    name="commercial.pricing.v1",
    fact_types=("commercial",),
    required=("amount", "currency", "billing_period"),
    optional=("market", "plan"),
    validator=_validate_pricing,
)


_REGISTRY: dict[str, NormalizedSchema] = {
    schema.name: schema for schema in (PRICING_V1,)
}


def register_schema(schema: NormalizedSchema) -> None:
    """Add or replace a schema (used by tests and downstream extensions)."""
    _REGISTRY[schema.name] = schema


def get_schema(name: str) -> NormalizedSchema | None:
    return _REGISTRY.get(name)


def list_schemas() -> list[NormalizedSchema]:
    return list(_REGISTRY.values())


def validate_payload(
    schema_name: str | None,
    fact_type: str,
    payload: dict[str, Any] | None,
) -> tuple[bool, str]:
    """Return (ok, reason). Empty payload with no schema is always OK."""
    if not schema_name:
        return True, ""
    if payload is None:
        return False, f"schema {schema_name} requires a payload"
    schema = _REGISTRY.get(schema_name)
    if schema is None:
        return False, f"unknown schema {schema_name}"
    if fact_type not in schema.fact_types:
        return False, (
            f"schema {schema_name} only applies to fact_type {schema.fact_types}; "
            f"got {fact_type}"
        )
    for required in schema.required:
        if required not in payload:
            return False, f"schema {schema_name} missing required field {required}"
    for field_name, allowed in schema.enums.items():
        if field_name in payload and payload[field_name] not in allowed:
            return False, (
                f"schema {schema_name} field {field_name} must be one of {allowed}"
            )
    if schema.validator is not None:
        ok, reason = schema.validator(payload)
        if not ok:
            return False, f"schema {schema_name}: {reason}"
    return True, ""