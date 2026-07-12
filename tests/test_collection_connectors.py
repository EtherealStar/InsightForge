from datetime import UTC, datetime

from infrastructure.connectors import ApiConnector, RssConnector, SitemapConnector, normalize_url
from models.collection import SourceCursor
from models.source_governance import SourceProfile


NOW = datetime(2026, 7, 13, tzinfo=UTC)


def test_normalize_url_removes_tracking_fragment_and_default_port():
    assert normalize_url("HTTPS://Example.com:443/a/?utm_source=x&b=2#part") == "https://example.com/a?b=2"


def test_rss_discovery_is_stable_for_same_cursor_and_url():
    profile = SourceProfile(domain="example.com")
    payload = b"""<rss><channel><item><link>https://example.com/post?utm_campaign=x</link>
        <guid>post-1</guid><pubDate>Mon, 13 Jul 2026 08:00:00 GMT</pubDate></item></channel></rss>"""
    cursor = SourceCursor(source_profile_id=profile.id, value="page-1")

    first = RssConnector(payload, observed_at=NOW).discover(profile, cursor)
    second = RssConnector(payload, observed_at=NOW).discover(profile, cursor)

    assert first.candidates[0].normalized_url == "https://example.com/post"
    assert first.candidates[0].idempotency_key == second.candidates[0].idempotency_key


def test_sitemap_uses_lastmod_as_discovery_cursor():
    profile = SourceProfile(domain="example.com")
    payload = b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/a</loc><lastmod>2026-07-12</lastmod></url>
    </urlset>"""

    result = SitemapConnector(payload, observed_at=NOW).discover(profile, None)

    assert result.candidates[0].discovery_cursor == "2026-07-12"
    assert result.next_cursor.value == "2026-07-12"


def test_api_connector_reads_configured_fields_without_fetching_body():
    profile = SourceProfile(domain="api.example.com")
    payload = {"items": [{"url": "https://api.example.com/p/1", "id": 17}], "next": "18"}

    result = ApiConnector(payload, items_field="items", url_field="url", cursor_field="next").discover(profile, None)

    assert [item.discovery_cursor for item in result.candidates] == ["17"]
    assert result.next_cursor.value == "18"

