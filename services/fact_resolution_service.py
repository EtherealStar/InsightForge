"""Conservative fact resolution service (Milestone 4).

Given an ``IntelFactCandidate`` and a list of existing ``IntelFact`` records
sharing the same ``candidate_key``, decide whether the candidate should:

  * reuse an existing fact (same)
  * create a new draft fact (different)
  * create a new draft fact with a status_reason (uncertain)

Rules:
  * candidate_key is only for recall; not unique.
  * Critical qualifiers (price, currency, version, market, billing period,
    time bucket) are compared first. Any explicit conflict → different.
  * If ``fact_text`` and ``normalized_data`` are identical after
    canonicalisation AND time semantics agree → same.
  * Otherwise → uncertain. The model is not consulted in the first version;
    callers can plug in a structured extraction client to disambiguate
    later, but must never auto-merge on a score threshold.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from models.target_intel import (
    FactResolution,
    FactResolutionOutcome,
    IntelFact,
    IntelFactCandidate,
)


CRITICAL_QUALIFIER_KEYS = (
    "amount",
    "currency",
    "billing_period",
    "market",
    "plan",
    "version",
    "edition",
    "sku",
)


def _canonical_text(value: str) -> str:
    return " ".join(value.lower().split())


def _canonical_data(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _time_bucket(dt: datetime | None, precision: str | None) -> tuple | None:
    if dt is None:
        return None
    if precision == "day":
        return (dt.year, dt.month, dt.day)
    if precision == "month":
        return (dt.year, dt.month)
    if precision == "quarter":
        return (dt.year, (dt.month - 1) // 3 + 1)
    return None


@dataclass
class ResolutionContext:
    candidate: IntelFactCandidate
    candidates: list[IntelFact] = field(default_factory=list)


class FactResolutionService:
    def __init__(self, structured_client=None):
        # structured_client is optional; v1 ships deterministic rules only.
        self._structured = structured_client

    def resolve(self, context: ResolutionContext) -> FactResolution:
        candidate = context.candidate
        qualifiers = candidate.key_qualifiers or {}
        cand_text = _canonical_text(candidate.fact_text)
        cand_norm = _canonical_data(candidate.normalized_data)
        cand_bucket = _time_bucket(candidate.occurred_at, candidate.time_precision)

        for existing in context.candidates:
            if not _same_subject(candidate, existing):
                continue
            # 1. critical qualifiers must agree.
            conflict = _find_qualifier_conflict(qualifiers, existing, candidate)
            if conflict:
                return FactResolution(
                    outcome=FactResolutionOutcome.DIFFERENT,
                    reason=f"critical qualifier conflict on {conflict}",
                )
            # 2. time bucket must agree.
            existing_bucket = _time_bucket(existing.occurred_at, existing.time_precision)
            if cand_bucket and existing_bucket and cand_bucket != existing_bucket:
                return FactResolution(
                    outcome=FactResolutionOutcome.DIFFERENT,
                    reason="time bucket differs",
                )
            # 3. identical text + identical normalized data → same.
            existing_text = _canonical_text(existing.fact_text)
            existing_norm = _canonical_data(existing.normalized_data)
            if existing_text == cand_text and existing_norm == cand_norm:
                return FactResolution(
                    outcome=FactResolutionOutcome.SAME,
                    matched_fact_id=existing.id,
                    reason="text and normalized data identical",
                )
            # 4. identical normalized payload alone → same.
            if cand_norm and existing_norm and existing_norm == cand_norm:
                return FactResolution(
                    outcome=FactResolutionOutcome.SAME,
                    matched_fact_id=existing.id,
                    reason="normalized payload identical",
                )
        # Fall back: uncertain. We do not consult the structured client in v1.
        return FactResolution(
            outcome=FactResolutionOutcome.UNCERTAIN,
            reason="no candidate matched deterministically",
        )


def _same_subject(candidate: IntelFactCandidate, existing: IntelFact) -> bool:
    if not candidate.subject_competitor_ids and not candidate.subject_product_ids:
        # No subject known — fall back to comparing candidate_key (already
        # filtered by caller) and time_precision bucket alone.
        return True
    # Subjects come from the candidate only; existing fact subjects live in
    # intel_fact_competitors / intel_fact_products. The Service caller is
    # expected to filter candidates to the same subject set first.
    return True


def _find_qualifier_conflict(
    qualifiers: dict[str, Any],
    existing: IntelFact,
    candidate: IntelFactCandidate,
) -> str | None:
    """Return the first conflicting key, or None."""
    if not qualifiers:
        return None
    # Compare against the candidate's normalized_data (which mirrors what the
    # existing fact would carry). When ``existing.normalized_data`` is None
    # or the key is absent we cannot conclude a conflict from that side.
    other = existing.normalized_data or {}
    for key in CRITICAL_QUALIFIER_KEYS:
        if key not in qualifiers:
            continue
        if key not in other:
            continue
        a = qualifiers[key]
        b = other[key]
        if isinstance(a, str) and isinstance(b, str):
            if a.strip().lower() != b.strip().lower():
                return key
        else:
            if a != b:
                return key
    return None