from dataclasses import fields, is_dataclass

from models.evidence import EvidenceOwnerType, EvidenceRef, EvidenceType
from models.insight import ClaimStatus, ClaimType, InsightClaim
from models.intel import (
    FactKind,
    FactStatus,
    FactType,
    IntelDimension,
    IntelFact,
)
from models.report import SourceRef


def test_intel_fact_models_are_pure_dataclasses():
    fact = IntelFact(
        fact_kind=FactKind.EVENT,
        fact_type=FactType.FEATURE_RELEASE,
        dimension=IntelDimension.PRODUCT,
        subject="Cursor",
        predicate="released",
        object="feature",
        fact_text="Cursor released a feature.",
        status=FactStatus.DRAFT,
    )

    assert is_dataclass(fact)
    assert fact.id
    assert fact.attributes == {}
    assert fact.competitor_ids == []
    assert FactType.PRICING_CHANGE.value == "pricing_change"
    assert IntelDimension.GO_TO_MARKET.value == "go_to_market"
    assert "source_document_id" not in {field.name for field in fields(IntelFact)}


def test_evidence_and_claim_models_defaults():
    evidence = EvidenceRef(
        owner_type=EvidenceOwnerType.INTEL_FACT,
        owner_id="fact-1",
        evidence_type=EvidenceType.SOURCE_CHUNK,
    )
    claim = InsightClaim(
        claim_text="Cursor is expanding pricing options.",
        claim_type=ClaimType.TREND,
        status=ClaimStatus.DRAFT,
        fact_ids=["fact-1"],
    )

    assert evidence.id
    assert claim.id
    assert claim.fact_ids == ["fact-1"]
    assert claim.competitor_ids == []


def test_source_ref_no_longer_references_article_intel_id():
    field_names = {field.name for field in fields(SourceRef)}

    assert "intel_id" not in field_names
