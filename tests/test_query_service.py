"""QueryService 单元测试"""
import pytest
from unittest.mock import MagicMock

from services.query_service import QueryService
from models.article import Article, Language
from models.search import SearchResult


class TestQueryService:
    """QueryService 测试"""

    @pytest.fixture
    def mock_article_store(self):
        store = MagicMock()
        store.search_by_keyword.return_value = [
            Article(
                title="Keyword result",
                url="https://example.com/kw",
                content="Keyword content",
                source="TestSource",
            )
        ]
        return store

    @pytest.fixture
    def mock_vector_store(self):
        vs = MagicMock()
        vs.search.return_value = [
            SearchResult(
                article=Article(
                    title="Semantic result",
                    url="https://example.com/sem",
                    content="Semantic content",
                    source="TestSource",
                ),
                relevance_score=0.85,
                match_type="semantic",
            )
        ]
        return vs

    @pytest.fixture
    def service(
        self,
        mock_article_store,
        mock_vector_store,
        mock_llm_client,
        mock_embedding_client,
    ):
        return QueryService(
            mock_article_store,
            mock_vector_store,
            mock_llm_client,
            mock_embedding_client,
        )

    def test_answer_returns_string(self, service):
        """answer 应返回字符串"""
        result = service.answer("测试问题")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_answer_stream_yields(self, service):
        """answer_stream 应 yield 文本块"""
        chunks = list(service.answer_stream("测试问题"))
        assert len(chunks) > 0

    def test_search_returns_results(self, service):
        """search 应返回 SearchResult 列表"""
        from models.search import SearchQuery

        results = service.search(SearchQuery(text="test query"))
        assert len(results) > 0
        assert isinstance(results[0], SearchResult)

    def test_answer_no_results(
        self, mock_article_store, mock_llm_client, mock_embedding_client
    ):
        """无检索结果时应返回提示信息"""
        empty_vs = MagicMock()
        empty_vs.search.return_value = []

        service = QueryService(
            mock_article_store, empty_vs, mock_llm_client, mock_embedding_client
        )
        result = service.answer("不存在的主题")
        assert "未找到" in result
