from datetime import UTC, datetime

from models.collection import (
    ArtifactStatus,
    FetchMethod,
    NormalizationOutcome,
    NormalizerRules,
    RawFetchArtifact,
)
from services.normalization_service import DeterministicNormalizationService


def artifact(content_type: str = "text/html") -> RawFetchArtifact:
    return RawFetchArtifact(
        candidate_id="candidate-1",
        source_task_id="task-1",
        request_url="https://example.com/post",
        final_url="https://example.com/post",
        fetch_method=FetchMethod.HTTP,
        status=ArtifactStatus.FETCHED,
        http_status=200,
        content_type=content_type,
        body_hash="hash",
        observed_at=datetime(2026, 7, 13, tzinfo=UTC),
        id="artifact-1",
    )


def test_normalization_produces_stable_verbatim_blocks():
    body = b"<html><body><article><h1>Release</h1><p>Exact product text remains unchanged.</p></article></body></html>"
    service = DeterministicNormalizationService()

    first = service.normalize(artifact(), body, NormalizerRules(version="v1", minimum_text_length=10))
    second = service.normalize(artifact(), body, NormalizerRules(version="v1", minimum_text_length=10))

    assert first.outcome is NormalizationOutcome.ACCEPTED
    assert [(b.id, b.text) for b in first.blocks] == [(b.id, b.text) for b in second.blocks]
    assert "Exact product text remains unchanged." in [b.text for b in first.blocks]


def test_short_static_page_requests_one_browser_retry():
    result = DeterministicNormalizationService().normalize(
        artifact(), b"<html><body>Enable JavaScript</body></html>", NormalizerRules(version="v1")
    )
    assert result.outcome is NormalizationOutcome.RETRY_RENDER
    assert "body_too_short" in result.reason_codes


def test_short_browser_page_requires_review_instead_of_retry_loop():
    item = artifact()
    item.fetch_method = FetchMethod.BROWSER
    result = DeterministicNormalizationService().normalize(item, b"<html><body>blocked</body></html>", NormalizerRules(version="v1"))
    assert result.outcome is NormalizationOutcome.REVIEW_REQUIRED


def test_unsupported_binary_is_rejected():
    result = DeterministicNormalizationService().normalize(
        artifact("application/octet-stream"), b"\x00\x01\x02", NormalizerRules(version="v1")
    )
    assert result.outcome is NormalizationOutcome.REJECTED
    assert "unsupported_media_type" in result.reason_codes


def test_pdf_is_routed_to_ocr_review_instead_of_decoded_as_text():
    result = DeterministicNormalizationService().normalize(
        artifact("application/pdf"), b"%PDF-1.7\n" + b"binary syntax " * 20, NormalizerRules(version="v1")
    )
    assert result.outcome is NormalizationOutcome.REVIEW_REQUIRED
    assert result.blocks == []
    assert result.reason_codes == ["pdf_requires_ocr"]
