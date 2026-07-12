"""静态 HTTP 与显式浏览器渲染 Fetch Engine。"""
from __future__ import annotations

from typing import Any
import gzip
import zlib

import httpx
import structlog

from core.retry import with_retry
from models.collection import ArtifactStatus, FetchCandidate, FetchMethod, FetchResult, SourceFetchPolicy


logger = structlog.get_logger(__name__)


class HttpFetchEngine:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    @with_retry(max_retries=2, backoff_base=0.25, exceptions=(httpx.TransportError,))
    async def fetch(self, candidate: FetchCandidate, policy: SourceFetchPolicy) -> FetchResult:
        headers = {"user-agent": "InsightForge/1.0 (+collection)"}
        if policy.etag:
            headers["if-none-match"] = policy.etag
        if policy.last_modified:
            headers["if-modified-since"] = policy.last_modified

        async with httpx.AsyncClient(
            transport=self.transport,
            follow_redirects=True,
            timeout=policy.timeout_seconds,
        ) as client:
            async with client.stream("GET", candidate.normalized_url, headers=headers) as response:
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                if response.status_code == 304:
                    return FetchResult(candidate.normalized_url, str(response.url), FetchMethod.HTTP, ArtifactStatus.NOT_MODIFIED, 304, response_headers, None)
                if response.is_stream_consumed:
                    # MockTransport 可返回已缓冲响应；真实网络响应仍走下面的流式限制。
                    raw_body = response.content
                    raw_size = len(raw_body)
                else:
                    raw_parts = []
                    raw_size = 0
                    async for chunk in response.aiter_raw():
                        raw_size += len(chunk)
                        if raw_size > policy.max_response_bytes:
                            return FetchResult(candidate.normalized_url, str(response.url), FetchMethod.HTTP, ArtifactStatus.FAILED, response.status_code, response_headers, None, "response_too_large")
                        raw_parts.append(chunk)
                    raw_body = b"".join(raw_parts)
                if raw_size > policy.max_response_bytes:
                    return FetchResult(candidate.normalized_url, str(response.url), FetchMethod.HTTP, ArtifactStatus.FAILED, response.status_code, response_headers, None, "response_too_large")
                body = self._decode_content(raw_body, response_headers.get("content-encoding"))
                final_url = str(response.url)
                status_code = response.status_code

        if len(body) > policy.max_response_bytes:
            return FetchResult(candidate.normalized_url, final_url, FetchMethod.HTTP, ArtifactStatus.FAILED, status_code, response_headers, None, "response_too_large")
        if raw_size and len(body) / raw_size > policy.max_decompression_ratio:
            return FetchResult(candidate.normalized_url, final_url, FetchMethod.HTTP, ArtifactStatus.FAILED, status_code, response_headers, None, "decompression_ratio_exceeded")

        body_prefix = body[:4096].lower()
        challenge = any(marker in body_prefix for marker in (b"captcha", b"cloudflare", b"access denied"))
        if status_code in (403, 429) or challenge:
            reason = "challenge_page" if challenge else f"http_{status_code}"
            return FetchResult(candidate.normalized_url, final_url, FetchMethod.HTTP, ArtifactStatus.BLOCKED, status_code, response_headers, body, reason)

        if status_code >= 400:
            return FetchResult(candidate.normalized_url, final_url, FetchMethod.HTTP, ArtifactStatus.FAILED, status_code, response_headers, body, f"http_{status_code}")
        return FetchResult(candidate.normalized_url, final_url, FetchMethod.HTTP, ArtifactStatus.FETCHED, status_code, response_headers, body)

    @staticmethod
    def _decode_content(body: bytes, encoding: str | None) -> bytes:
        if not encoding:
            return body
        normalized = encoding.lower()
        if normalized == "gzip":
            return gzip.decompress(body)
        if normalized == "deflate":
            return zlib.decompress(body)
        # br/zstd 交给 httpx 可选依赖前必须显式拒绝，避免误把压缩字节送去清洗。
        raise ValueError(f"不支持的 Content-Encoding: {encoding}")


class BrowserFetchEngine:
    """Playwright 是可选运行时依赖，仅在 browser 队列中导入。"""

    async def fetch(self, candidate: FetchCandidate, policy: SourceFetchPolicy) -> FetchResult:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("browser fetch 需要安装 playwright 并执行 playwright install") from exc

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                response = await page.goto(candidate.normalized_url, wait_until="networkidle", timeout=int(policy.timeout_seconds * 1000))
                body = (await page.content()).encode("utf-8")
                status = response.status if response else None
                headers: dict[str, str] = await response.all_headers() if response else {}
                return FetchResult(candidate.normalized_url, page.url, FetchMethod.BROWSER, ArtifactStatus.FETCHED, status, headers, body)
            finally:
                await context.close()
                await browser.close()
