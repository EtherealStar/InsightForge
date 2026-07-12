from datetime import UTC, datetime

from models.collection import NormalizationOutcome, NormalizedDocument
from models.source_governance import SourceProfile, SourceTier
from services.collection_execution_service import CollectionExecutionService


def document(outcome=NormalizationOutcome.ACCEPTED):
    return NormalizedDocument("artifact", "v1", outcome, [], [])


def test_only_accepted_governed_source_can_enter_ingest():
    assert CollectionExecutionService.should_ingest(document(), SourceProfile("official.example", tier=SourceTier.A))
    assert not CollectionExecutionService.should_ingest(document(), SourceProfile("unknown.example"))
    assert not CollectionExecutionService.should_ingest(document(), SourceProfile("bad.example", tier=SourceTier.D))
    assert not CollectionExecutionService.should_ingest(
        document(NormalizationOutcome.REVIEW_REQUIRED), SourceProfile("official.example", tier=SourceTier.A)
    )
    assert not CollectionExecutionService.should_ingest(document(), None)
