"""只负责发现候选的来源 Connector，不下载候选正文。"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser

from models.collection import DiscoveryResult, FetchCandidate, SourceCursor
from models.source_governance import SourceProfile


TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    port = parts.port
    netloc = hostname if port in (None, 80 if scheme == "http" else 443) else f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    ]
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))


class _BaseConnector:
    expected_media_type: str | None = "text/html"

    def __init__(self, *, observed_at: datetime | None = None):
        self.observed_at = observed_at or datetime.now(UTC)

    def _candidate(self, profile: SourceProfile, url: str, cursor: Any, **metadata: Any) -> FetchCandidate:
        return FetchCandidate(
            source_profile_id=profile.id,
            normalized_url=normalize_url(url),
            discovered_at=self.observed_at,
            discovery_cursor=str(cursor or ""),
            expected_media_type=self.expected_media_type,
            metadata=metadata,
        )


class RssConnector(_BaseConnector):
    def __init__(self, payload: bytes | str, *, observed_at: datetime | None = None):
        super().__init__(observed_at=observed_at)
        self.payload = payload

    def discover(self, profile: SourceProfile, cursor: SourceCursor | None) -> DiscoveryResult:
        feed = feedparser.parse(self.payload)
        candidates = []
        for entry in feed.entries:
            value = entry.get("id") or entry.get("published") or (cursor.value if cursor else "")
            if entry.get("link"):
                candidates.append(self._candidate(profile, entry.link, value, title=entry.get("title")))
        next_value = str(candidates[-1].discovery_cursor) if candidates else (cursor.value if cursor else "")
        return DiscoveryResult(candidates, SourceCursor(profile.id, next_value))


class SitemapConnector(_BaseConnector):
    def __init__(self, payload: bytes | str, *, observed_at: datetime | None = None):
        super().__init__(observed_at=observed_at)
        self.payload = payload

    def discover(self, profile: SourceProfile, cursor: SourceCursor | None) -> DiscoveryResult:
        root = ET.fromstring(self.payload)
        candidates = []
        for item in root.findall("{*}url"):
            loc = item.findtext("{*}loc")
            lastmod = item.findtext("{*}lastmod") or (cursor.value if cursor else "")
            if loc:
                candidates.append(self._candidate(profile, loc, lastmod))
        next_value = max((item.discovery_cursor for item in candidates), default=cursor.value if cursor else "")
        return DiscoveryResult(candidates, SourceCursor(profile.id, next_value))


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


class ListingConnector(_BaseConnector):
    def __init__(self, payload: str, *, observed_at: datetime | None = None):
        super().__init__(observed_at=observed_at)
        self.payload = payload

    def discover(self, profile: SourceProfile, cursor: SourceCursor | None) -> DiscoveryResult:
        parser = _LinkParser()
        parser.feed(self.payload)
        value = cursor.value if cursor else self.observed_at.isoformat()
        return DiscoveryResult([self._candidate(profile, url, value) for url in parser.links], SourceCursor(profile.id, value))


class ApiConnector(_BaseConnector):
    def __init__(self, payload: dict[str, Any] | str, *, items_field: str, url_field: str, cursor_field: str, observed_at: datetime | None = None):
        super().__init__(observed_at=observed_at)
        self.payload = json.loads(payload) if isinstance(payload, str) else payload
        self.items_field = items_field
        self.url_field = url_field
        self.cursor_field = cursor_field

    def discover(self, profile: SourceProfile, cursor: SourceCursor | None) -> DiscoveryResult:
        candidates = []
        for item in self.payload.get(self.items_field, []):
            item_cursor = item.get("cursor", item.get("id", cursor.value if cursor else ""))
            candidates.append(self._candidate(profile, item[self.url_field], item_cursor, api_item=item))
        next_value = str(self.payload.get(self.cursor_field, cursor.value if cursor else ""))
        return DiscoveryResult(candidates, SourceCursor(profile.id, next_value))


class SearchConnector(_BaseConnector):
    def __init__(self, results: Iterable[dict[str, Any]], *, observed_at: datetime | None = None):
        super().__init__(observed_at=observed_at)
        self.results = list(results)

    def discover(self, profile: SourceProfile, cursor: SourceCursor | None) -> DiscoveryResult:
        value = cursor.value if cursor else self.observed_at.isoformat()
        candidates = [self._candidate(profile, item["url"], item.get("id", value), search_result=item) for item in self.results]
        return DiscoveryResult(candidates, SourceCursor(profile.id, value))
