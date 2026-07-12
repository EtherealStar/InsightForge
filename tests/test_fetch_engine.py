import httpx
import pytest

from infrastructure.fetch_engines import HttpFetchEngine
from models.collection import ArtifactStatus, FetchCandidate, SourceFetchPolicy


def candidate() -> FetchCandidate:
    from datetime import UTC, datetime
    return FetchCandidate("source-1", "https://example.com/a", datetime.now(UTC), "cursor-1")


@pytest.mark.asyncio
async def test_http_fetch_sends_conditionals_and_handles_304():
    def handler(request: httpx.Request):
        assert request.headers["if-none-match"] == '"v1"'
        return httpx.Response(304, request=request)

    engine = HttpFetchEngine(transport=httpx.MockTransport(handler))
    result = await engine.fetch(candidate(), SourceFetchPolicy(etag='"v1"'))

    assert result.status is ArtifactStatus.NOT_MODIFIED
    assert result.body is None


@pytest.mark.asyncio
async def test_http_fetch_rejects_oversized_response():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 11, request=request))
    result = await HttpFetchEngine(transport=transport).fetch(candidate(), SourceFetchPolicy(max_response_bytes=10))

    assert result.status is ArtifactStatus.FAILED
    assert result.reason_code == "response_too_large"


@pytest.mark.asyncio
async def test_http_fetch_marks_challenge_page_blocked():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(403, text="Please complete the CAPTCHA", headers={"content-type": "text/html"}, request=request)
    )
    result = await HttpFetchEngine(transport=transport).fetch(candidate(), SourceFetchPolicy())

    assert result.status is ArtifactStatus.BLOCKED
    assert result.reason_code == "challenge_page"
