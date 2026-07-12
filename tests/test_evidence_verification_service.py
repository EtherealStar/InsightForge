from models.intel import IntelFact, VerificationStatus
from services.evidence_verification_service import EvidenceVerificationService


def test_independent_evidence_must_come_from_distinct_clusters():
    evidence = [
        {"document_cluster_id": "cluster-a", "role": "independent", "source_tier": "A"},
        {"document_cluster_id": "cluster-a", "role": "independent", "source_tier": "B"},
        {"document_cluster_id": "cluster-b", "role": "interested_claim", "source_tier": "A"},
    ]

    status, _ = EvidenceVerificationService().derive_status(
        IntelFact(fact_text="fact"), evidence
    )

    assert status != VerificationStatus.CORROBORATED


def test_assertion_key_is_independent_of_evidence_source():
    service = EvidenceVerificationService()
    common = {
        "subject": "Cursor",
        "fact_type": "pricing_change",
        "predicate": "monthly_price",
        "object": "$20",
        "event_date": "2026-07-01",
    }

    first = service.assertion_key({**common, "source_document_id": "cluster-a"})
    second = service.assertion_key({**common, "source_document_id": "cluster-b"})

    assert first == second


def test_contradicting_evidence_has_priority():
    status, reason = EvidenceVerificationService().derive_status(
        IntelFact(fact_text="fact"),
        [
            {"source_document_id": "a", "role": "independent", "source_tier": "A"},
            {"source_document_id": "b", "role": "independent", "source_tier": "B"},
            {"source_document_id": "c", "stance": "contradicts"},
        ],
    )

    assert status == VerificationStatus.DISPUTED
    assert reason == "存在明确反证"


def test_primary_evidence_is_self_reported():
    status, _ = EvidenceVerificationService().derive_status(
        IntelFact(fact_text="fact"),
        [{"source_document_id": "a", "role": "primary", "source_tier": "A"}],
    )

    assert status == VerificationStatus.SELF_REPORTED
