"""NewsCollector 单元测试（mock 外部依赖）"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from infrastructure.collector import NewsCollector
from core.config import AppConfig
from models.article import Language


class TestNewsCollector:
    """NewsCollector 测试"""

    @pytest.fixture
    def config(self):
        return AppConfig(
            rss_feeds=[
                {"name": "TestFeed", "url": "https://test.com/rss"},
            ],
            max_articles_per_fetch=5,
        )

    @pytest.fixture
    def collector(self, config):
        return NewsCollector(config)

    def test_detect_language_chinese(self, collector):
        """中文文本应检测为 ZH"""
        text = "这是一段中文新闻内容，用于测试语言检测功能"
        assert collector._detect_language(text) == Language.ZH

    def test_detect_language_english(self, collector):
        """英文文本应检测为 EN"""
        text = "This is an English news article for testing purpose"
        assert collector._detect_language(text) == Language.EN

    def test_detect_language_empty(self, collector):
        """空文本应返回 UNKNOWN"""
        assert collector._detect_language("") == Language.UNKNOWN

    @patch("infrastructure.collector.feedparser")
    def test_fetch_source_with_entries(self, mock_fp, collector):
        """有 entries 时应返回 Article 列表"""
        mock_entry = MagicMock()
        mock_entry.get = lambda k, d="": {
            "title": "Test Title",
            "link": "https://test.com/1",
            "summary": "Test summary",
        }.get(k, d)
        mock_entry.published_parsed = None
        mock_entry.author = ""
        # feedparser entry 没有 content 和 description 属性时
        del mock_entry.content
        del mock_entry.description

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [mock_entry]
        mock_fp.parse.return_value = mock_feed

        with patch.object(collector, "_extract_full_text", return_value=(None, None)):
            articles = collector.fetch_source("TestFeed", "https://test.com/rss")

        assert len(articles) == 1
        assert articles[0].title == "Test Title"

    @patch("infrastructure.collector.feedparser")
    def test_fetch_source_empty(self, mock_fp, collector):
        """空 feed 且 bozo 应抛异常"""
        mock_feed = MagicMock()
        mock_feed.bozo = True
        mock_feed.entries = []
        mock_feed.bozo_exception = Exception("Parse error")
        mock_fp.parse.return_value = mock_feed

        with pytest.raises(Exception):
            collector.fetch_source("TestFeed", "https://test.com/rss")

    @patch("infrastructure.collector.feedparser")
    def test_fetch_all_recovers_from_error(self, mock_fp, config):
        """单源失败不影响其他源"""
        config.rss_feeds = [
            {"name": "FailFeed", "url": "https://fail.com/rss"},
            {"name": "GoodFeed", "url": "https://good.com/rss"},
        ]
        collector = NewsCollector(config)

        mock_entry = MagicMock()
        mock_entry.get = lambda k, d="": {
            "title": "Good Title",
            "link": "https://good.com/1",
            "summary": "Good summary",
        }.get(k, d)
        mock_entry.published_parsed = None
        mock_entry.author = ""
        del mock_entry.content
        del mock_entry.description

        def side_effect(url):
            if "fail" in url:
                feed = MagicMock()
                feed.bozo = True
                feed.entries = []
                feed.bozo_exception = Exception("Fail")
                return feed
            feed = MagicMock()
            feed.bozo = False
            feed.entries = [mock_entry]
            return feed

        mock_fp.parse.side_effect = side_effect

        with patch.object(collector, "_extract_full_text", return_value=(None, None)):
            articles = collector.fetch_all()

        # FailFeed 失败但 GoodFeed 成功
        assert len(articles) == 1
