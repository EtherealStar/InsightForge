"""PipelineService 集成测试"""
import pytest
from unittest.mock import MagicMock, patch

from services.pipeline_service import PipelineService
from models.article import Article, Language
from datetime import datetime


class TestPipelineService:
    """PipelineService 测试"""

    @pytest.fixture
    def store(self):
        store = MagicMock()
        store.save_articles.return_value = 1
        store.get_unembedded.return_value = [
            Article(
                id=1,
                title="Pipeline Test",
                url="https://example.com/pipeline",
                content="Pipeline test content",
                source="PipelineSource",
                language=Language.EN,
                published_at=datetime.now(),
            )
        ]
        return store

    @pytest.fixture
    def mock_collector(self):
        collector = MagicMock()
        collector.fetch_all.return_value = [
            Article(
                title="Pipeline Test",
                url="https://example.com/pipeline",
                content="Pipeline test content",
                source="PipelineSource",
                language=Language.EN,
                published_at=datetime.now(),
            ),
        ]
        return collector

    @pytest.fixture
    def mock_vector_store(self):
        vs = MagicMock()
        vs.add_chunks.return_value = 1
        return vs

    @pytest.fixture
    def mock_chunking_service(self):
        from models.chunk import Chunk, ParentChunk
        cs = MagicMock()
        child = Chunk(chunk_id="c1", article_id=1, parent_chunk_id="p1", content="child chunk", token_count=10, doc_name="test doc")
        parent = ParentChunk(parent_chunk_id="p1", article_id=1, content="parent chunk", token_count=10, doc_name="test doc")
        cs.chunk_articles.return_value = ([child], [parent])
        return cs

    def test_pipeline_full_run(
        self, store, mock_collector, mock_vector_store, mock_embedding_client, mock_chunking_service
    ):
        """完整 Pipeline 应成功执行"""
        service = PipelineService(
            collector=mock_collector, 
            article_store=store, 
            vector_store=mock_vector_store, 
            embedding_client=mock_embedding_client,
            chunking_service=mock_chunking_service
        )
        result = service.run()

        assert result["fetched"] == 1
        assert result["new"] == 1
        assert result["embedded"] == 1
        assert result["errors"] == []

    def test_pipeline_collector_failure(
        self, store, mock_vector_store, mock_embedding_client
    ):
        """抓取失败不应终止后续步骤"""
        collector = MagicMock()
        collector.fetch_all.side_effect = Exception("Network error")

        service = PipelineService(
            collector, store, mock_vector_store, mock_embedding_client
        )
        result = service.run()

        assert result["fetched"] == 0
        assert len(result["errors"]) == 1
        assert "抓取" in result["errors"][0]

    def test_pipeline_embedding_failure(
        self, store, mock_collector, mock_vector_store, mock_chunking_service
    ):
        """向量化失败应记录错误"""
        bad_embedding = MagicMock()
        bad_embedding.embed.side_effect = Exception("Embedding API error")

        service = PipelineService(
            collector=mock_collector, 
            article_store=store, 
            vector_store=mock_vector_store, 
            embedding_client=bad_embedding,
            chunking_service=mock_chunking_service
        )
        result = service.run()

        assert result["fetched"] == 1
        assert result["new"] == 1
        assert result["embedded"] == 0
        assert len(result["errors"]) == 1

    def test_pipeline_no_new_articles(
        self, store, mock_vector_store, mock_embedding_client
    ):
        """无新文章时应正常完成"""
        collector = MagicMock()
        collector.fetch_all.return_value = []

        service = PipelineService(
            collector, store, mock_vector_store, mock_embedding_client
        )
        result = service.run()

        assert result["fetched"] == 0
        assert result["new"] == 0
        assert result["errors"] == []
