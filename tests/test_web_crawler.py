"""WebCrawler 行为测试"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from infrastructure.web_crawler import WebCrawler, _build_storage_name


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
        "custom", "https://example.com", "a.article", 3
    )
    assert crawler.max_pages == 20
