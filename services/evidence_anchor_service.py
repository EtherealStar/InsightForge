"""Evidence anchor service (Milestone 3).

Provides the only legitimate path to creating a formal Evidence Reference.
The service:

  * Validates the locator is a well-formed char_range pointing inside the
    bound Document Version's content.
  * Confirms ``content[start:end] == quoted_text`` byte-for-byte (Python
    Unicode code points; end exclusive).
  * Verifies the Source Occurrence belongs to the same Document Cluster.
  * Computes the canonical ``quote_hash`` (server-side) and rejects any
    client-supplied hash that disagrees.

Search snippets, bare URLs and un-attached manual inputs are NOT accepted
here — they belong to the Evidence Candidate pipeline, not formal anchors.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.exceptions import IntelligenceInvariantError
from infrastructure.intel_store_v2 import (
    PostgresIntelStoreV2,
    compute_quote_hash,
)
from models.target_evidence import CharRangeLocator, EvidenceReference


@dataclass
class AnchorRequest:
    document_version_id: str
    source_occurrence_id: str
    quoted_text: str
    locator: dict
    parent_chunk_id: str | None = None
    client_quote_hash: str | None = None


class EvidenceAnchorService:
    def __init__(self, store: PostgresIntelStoreV2):
        self._store = store

    def create_evidence_reference(self, request: AnchorRequest) -> EvidenceReference:
        if not request.quoted_text:
            raise IntelligenceInvariantError("quoted_text must not be empty")
        if not request.document_version_id or not request.source_occurrence_id:
            raise IntelligenceInvariantError(
                "document_version_id and source_occurrence_id are required"
            )

        try:
            locator = CharRangeLocator.from_dict(request.locator)
        except (ValueError, KeyError, TypeError) as exc:
            raise IntelligenceInvariantError(f"invalid locator: {exc}") from exc

        # Resolve the version / occurrence context. Raises StoreError if
        # the version / occurrence don't share a cluster.
        context = self._store.resolve_evidence_context(
            document_version_id=request.document_version_id,
            source_occurrence_id=request.source_occurrence_id,
        )
        content = context.get("content")
        if content is None:
            raise IntelligenceInvariantError(
                f"document version {request.document_version_id} has no content"
            )

        if locator.end > len(content):
            raise IntelligenceInvariantError(
                f"locator end {locator.end} exceeds content length {len(content)}"
            )
        if locator.start < 0:
            raise IntelligenceInvariantError(
                f"locator start {locator.start} is negative"
            )
        actual = content[locator.start:locator.end]
        if actual != request.quoted_text:
            raise IntelligenceInvariantError(
                "quoted_text does not match content slice "
                f"[{locator.start}:{locator.end}]"
            )

        server_hash = compute_quote_hash(request.quoted_text)
        if (
            request.client_quote_hash is not None
            and request.client_quote_hash != server_hash
        ):
            raise IntelligenceInvariantError(
                "client_quote_hash disagrees with server-computed hash"
            )

        evidence = EvidenceReference(
            document_version_id=request.document_version_id,
            source_occurrence_id=request.source_occurrence_id,
            quoted_text=request.quoted_text,
            quote_hash=server_hash,
            locator=locator.to_dict(),
            parent_chunk_id=request.parent_chunk_id,
        )
        return self._store.save_evidence_reference(evidence)