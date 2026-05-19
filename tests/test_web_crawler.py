"""WebCrawler 行为测试"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from infrastructure.web_crawler import (
    WebCrawler,
    _build_storage_name,
    _canonicalize_url,
    _merge_rules,
    _url_matches_rules,
)


class _FakeRouter:
    def default_handler(self, handler):
        self.handler = handler
        return handler


class _FakeBeautifulSoupCrawler:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.router = _FakeRouter()
        self.run = AsyncMock()
        self.instances.append(self)


def test_build_storage_name_is_unique_per_crawl_task():
    """同一站点的不同爬取任务也应使用不同存储名称。"""
    first = _build_storage_name("BBC News", "https://www.bbc.com/news")
    second = _build_storage_name("BBC News", "https://www.bbc.com/news")

    assert first != second
    assert first.startswith("web-crawler-bbc-news-")
    assert second.startswith("web-crawler-bbc-news-")


def test_crawl_uses_independent_request_queue_name():
    """每次爬取显式打开独立 RequestQueue，避免落到 Crawlee default。"""
    _FakeBeautifulSoupCrawler.instances = []
    request_queue = MagicMock()

    with (
        patch(
            "infrastructure.web_crawler.RequestQueue.open",
            new=AsyncMock(return_value=request_queue),
        ) as open_queue,
        patch(
            "infrastructure.web_crawler.BeautifulSoupCrawler",
            new=_FakeBeautifulSoupCrawler,
        ),
    ):
        articles = asyncio.run(
            WebCrawler(max_pages=3)._crawl("Example", "https://example.com")
        )

    assert articles == []
    storage_name = open_queue.await_args.kwargs["name"]
    assert storage_name.startswith("web-crawler-example-")

    crawler = _FakeBeautifulSoupCrawler.instances[0]
    assert crawler.kwargs["request_manager"] is request_queue
    crawler.run.assert_awaited_once_with(["https://example.com"])


def test_crawl_all_restores_max_pages_after_site_failure():
    crawler = WebCrawler(max_pages=20)

    with patch.object(crawler, "crawl_site", side_effect=RuntimeError("boom")):
        articles, errors = crawler.crawl_all(
            [{"name": "bad", "url": "https://example.com", "max_pages": 2}]
        )

    assert articles == []
    assert len(errors) == 1
    assert crawler.max_pages == 20


def test_crawl_all_passes_site_max_pages_without_mutating_instance():
    crawler = WebCrawler(max_pages=20)

    with patch.object(crawler, "crawl_site", return_value=[]) as crawl_site:
        articles, errors = crawler.crawl_all(
            [{
                "name": "custom",
                "url": "https://example.com",
                "max_pages": 3,
                "link_selector": "a.article",
            }]
        )

    assert articles == []
    assert errors == []
    crawl_site.assert_called_once_with(
        "custom", "https://example.com", "a.article", 3, None, None, None, None
    )
    assert crawler.max_pages == 20


def test_thepaper_builtin_rules_accept_article_url():
    rules = _merge_rules("澎湃", "https://www.thepaper.cn/")

    assert _url_matches_rules(
        "https://www.thepaper.cn/newsDetail_forward_33198341",
        rules,
    )


def test_thepaper_builtin_rules_reject_section_download_and_comment_urls():
    rules = _merge_rules("澎湃", "https://www.thepaper.cn/")

    assert not _url_matches_rules("https://www.thepaper.cn/list_25425", rules)
    assert not _url_matches_rules("https://m.thepaper.cn/download?id=2", rules)
    assert not _url_matches_rules(
        "https://www.thepaper.cn/newsDetail_forward_33198341?commTag=true",
        rules,
    )


def test_bjnews_builtin_rules_accept_article_url():
    rules = _merge_rules("新京报", "https://www.bjnews.com.cn/")

    assert _url_matches_rules(
        "https://www.bjnews.com.cn/detail/1779150638129135.html",
        rules,
    )


def test_bjnews_builtin_rules_reject_non_article_and_share_urls():
    rules = _merge_rules("新京报", "https://www.bjnews.com.cn/")

    assert not _url_matches_rules("https://www.bjnews.com.cn/site/business", rules)
    assert not _url_matches_rules("https://www.bjnews.com.cn/subject", rules)
    assert not _url_matches_rules(
        "https://m.bjnews.com.cn/detail/1779150638129135.html",
        rules,
    )
    assert not _url_matches_rules(
        "http://service.weibo.com/share/share.php"
        "?url=https://www.bjnews.com.cn/detail/1779150638129135.html&title=x",
        rules,
    )


def test_infzm_builtin_rules_accept_article_url():
    rules = _merge_rules("南方周末", "https://www.infzm.com/")

    assert _url_matches_rules(
        "https://www.infzm.com/contents/321843?source=133&source_1=202",
        rules,
    )


def test_infzm_builtin_rules_reject_non_article_login_and_download_urls():
    rules = _merge_rules("南方周末", "https://www.infzm.com/")

    assert not _url_matches_rules("https://www.infzm.com/topics/t202.html", rules)
    assert not _url_matches_rules(
        "https://www.infzm.com/contents?term_id=121&form_content_id=321843",
        rules,
    )
    assert not _url_matches_rules("https://www.infzm.com/download", rules)
    assert not _url_matches_rules("https://passport.infzm.com/login", rules)


def test_unconfigured_site_keeps_legacy_url_acceptance():
    rules = _merge_rules("Example", "https://example.com/")

    assert _url_matches_rules("https://example.com/section", rules)
    assert _url_matches_rules("https://example.com/story/123", rules)


def test_canonicalize_url_removes_tracking_query_and_fragment():
    url = _canonicalize_url(
        "https://www.thepaper.cn/newsDetail_forward_33198341?commTag=true&utm_source=x#comments"
    )

    assert url == "https://www.thepaper.cn/newsDetail_forward_33198341"


def test_meets_content_threshold_requires_sufficient_chinese_body():
    crawler = WebCrawler()

    assert not crawler._meets_content_threshold("中" * 999)
    assert not crawler._meets_content_threshold("a" * 4000)
    assert crawler._meets_content_threshold("中" * 1000)


def test_crawl_all_passes_extended_site_rules():
    crawler = WebCrawler(max_pages=20)
    site = {
        "name": "custom",
        "url": "https://example.com",
        "max_pages": 3,
        "link_selector": "a.article",
        "article_url_patterns": [r"/story/\d+"],
        "exclude_url_patterns": [r"/tag/"],
        "content_selector": "article",
        "noise_selectors": [".sidebar"],
    }

    with patch.object(crawler, "crawl_site", return_value=[]) as crawl_site:
        articles, errors = crawler.crawl_all([site])

    assert articles == []
    assert errors == []
    crawl_site.assert_called_once_with(
        "custom",
        "https://example.com",
        "a.article",
        3,
        [r"/story/\d+"],
        [r"/tag/"],
        "article",
        [".sidebar"],
    )
