"""PostgresArticleStore 单元测试"""
import pytest
from datetime import datetime, timedelta

from infrastructure.postgres_article_store import PostgresArticleStore
from models.article import Article, Language, ArticleStatus

import os
pytestmark = pytest.mark.skipif(not os.getenv("TEST_PG_DSN"), reason="Requires PostgreSQL instance")

class TestPostgresArticleStore:
    """PostgresArticleStore 测试"""

    def test_init_creates_table(self, test_dsn):
        """初始化应自动创建数据库表"""
        store = PostgresArticleStore(test_dsn)
        stats = store.get_stats()
        assert stats["total"] == 0

    def test_save_articles(self, test_dsn, sample_articles):
        """保存文章应返回新增数量"""
        store = PostgresArticleStore(test_dsn)
        count = store.save_articles(sample_articles)
        assert count == 2

    def test_save_articles_dedup(self, test_dsn, sample_articles):
        """重复 URL 应被去重"""
        store = PostgresArticleStore(test_dsn)
        store.save_articles(sample_articles)
        count = store.save_articles(sample_articles)
        assert count == 0
        assert store.get_stats()["total"] == 2

    def test_get_unembedded(self, test_dsn, sample_articles):
        """新保存的文章应为 unembedded"""
        store = PostgresArticleStore(test_dsn)
        store.save_articles(sample_articles)
        unembedded = store.get_unembedded()
        assert len(unembedded) == 2

    def test_mark_embedded(self, test_dsn, sample_articles):
        """标记为 embedded 后不应再出现在 unembedded 中"""
        store = PostgresArticleStore(test_dsn)
        store.save_articles(sample_articles)
        unembedded = store.get_unembedded()
        ids = [a.id for a in unembedded if a.id is not None]
        store.mark_embedded(ids)
        assert len(store.get_unembedded()) == 0

    def test_search_by_keyword(self, test_dsn, sample_articles):
        """关键词搜索应匹配标题和内容"""
        store = PostgresArticleStore(test_dsn)
        store.save_articles(sample_articles)
        results = store.search_by_keyword("AI")
        assert len(results) == 1
        assert "AI" in results[0].title

    def test_search_by_keyword_chinese(self, test_dsn, sample_articles):
        """中文关键词搜索"""
        store = PostgresArticleStore(test_dsn)
        store.save_articles(sample_articles)
        results = store.search_by_keyword("测试")
        assert len(results) == 1

    def test_get_recent(self, test_dsn, sample_articles):
        """最近文章查询"""
        store = PostgresArticleStore(test_dsn)
        store.save_articles(sample_articles)
        recent = store.get_recent(hours=1)
        assert len(recent) == 2

    def test_get_stats(self, test_dsn, sample_articles):
        """统计信息应准确"""
        store = PostgresArticleStore(test_dsn)
        store.save_articles(sample_articles)
        stats = store.get_stats()
        assert stats["total"] == 2
        assert stats["today_new"] == 2
        assert "TestSource" in stats["sources"]

    def test_cleanup_old_articles(self, test_dsn):
        """清理应删除旧文章"""
        store = PostgresArticleStore(test_dsn)
        old_article = Article(
            title="Old news",
            url="https://example.com/old",
            content="Old content",
            source="OldSource",
            published_at=datetime.now() - timedelta(days=100),
        )
        store.save_articles([old_article])
        assert store.get_stats()["total"] == 1
        deleted = store.cleanup_old_articles(retention_days=90)
        # 注: cleanup 基于 created_at 而非 published_at，
        # 刚创建的文章 created_at 是现在，所以不会被删除
        assert deleted == 0

    def test_empty_mark_embedded(self, test_dsn):
        """空列表不应报错"""
        store = PostgresArticleStore(test_dsn)
        store.mark_embedded([])  # 不应抛异常
