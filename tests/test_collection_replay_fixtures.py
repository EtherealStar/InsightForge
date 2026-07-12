from datetime import UTC, datetime
from pathlib import Path

import pytest

from models.collection import ArtifactStatus, FetchMethod, NormalizationOutcome, NormalizerRules, RawFetchArtifact
from services.normalization_service import DeterministicNormalizationService


FIXTURES = Path(__file__).parent / "fixtures" / "collection"


@pytest.mark.parametrize(
    ("filename", "content_type", "method", "expected"),
    [
        ("accepted.html", "text/html", FetchMethod.HTTP, NormalizationOutcome.ACCEPTED),
        ("retry_render.html", "text/html", FetchMethod.HTTP, NormalizationOutcome.RETRY_RENDER),
        ("review_required.html", "text/html", FetchMethod.BROWSER, NormalizationOutcome.REVIEW_REQUIRED),
        ("rejected.bin", "application/octet-stream", FetchMethod.HTTP, NormalizationOutcome.REJECTED),
    ],
)
def test_replay_fixture_has_stable_expected_outcome(filename, content_type, method, expected):
    artifact = RawFetchArtifact(
        filename, "task", f"https://fixture.invalid/{filename}", f"https://fixture.invalid/{filename}",
        method, ArtifactStatus.FETCHED, 200, content_type, filename, datetime.now(UTC), id=filename,
    )
    body = (FIXTURES / filename).read_bytes()
    service = DeterministicNormalizationService()

    first = service.normalize(artifact, body, NormalizerRules("fixture-v1"))
    second = service.normalize(artifact, body, NormalizerRules("fixture-v1"))

    assert first.outcome is expected
    assert [(item.id, item.text, item.source_locator) for item in first.blocks] == [
        (item.id, item.text, item.source_locator) for item in second.blocks
    ]

