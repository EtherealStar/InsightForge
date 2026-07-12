from io import BytesIO
from datetime import UTC, datetime

from pypdf import PdfWriter

from models.collection import ArtifactStatus, FetchMethod, NormalizationOutcome, NormalizerRules, RawFetchArtifact
from services.pdf_normalization_service import PdfTextNormalizationService


def test_pdf_without_text_layer_requires_review():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    stream = BytesIO()
    writer.write(stream)
    artifact = RawFetchArtifact(
        "candidate", "task", "https://example.com/a.pdf", "https://example.com/a.pdf",
        FetchMethod.HTTP, ArtifactStatus.FETCHED, 200, "application/pdf", "hash", datetime.now(UTC), id="artifact",
    )

    result = PdfTextNormalizationService().normalize(
        artifact, stream.getvalue(), NormalizerRules("pdf-text-v1", minimum_text_length=10)
    )

    assert result.outcome is NormalizationOutcome.REVIEW_REQUIRED
    assert result.reason_codes == ["pdf_text_layer_missing"]
    assert result.blocks == []
