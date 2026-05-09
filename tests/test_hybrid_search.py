"""混合检索（RRF 融合 + 关键词搜索）测试

测试覆盖：
1. RRF 算法单元测试
2. KeywordSearchService 测试
3. HybridSearchService 集成测试
4. QueryKnowledgeBaseTool search_mode 路由测试
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from infrastructure.hybrid_search_service import HybridSearchService
from infrastructure.keyword_search_service import KeywordSearchService
from models.chunk import Chunk, ParentChunk
from models.search import ChunkSearchResult, HybridSearchResult


# =====================================================================
# Fixtures
# =====================================================================

def _make_parent_chunk(pid: str, article_id: int = 1, content: str = "") -> ParentChunk:
    return ParentChunk(
        parent_chunk_id=pid,
        article_id=article_id,
        content=content or f"Content for {pid}",
        token_count=100,
        child_chunk_ids=[f"{pid}_c0"],
        doc_name=f"Doc-{pid}",
        source="test",
        url=f"https://example.com/{pid}",
    )


def _make_chunk_search_result(
    pid: str, score: float = 0.9, match_type: str = "semantic"
) -> ChunkSearchResult:
    chunk = Chunk(
        chunk_id=f"{pid}_c0",
        article_id=1,
        parent_chunk_id=pid,
        content=f"子 chunk for {pid}",
        token_count=50,
        doc_name=f"Doc-{pid}",
    )
    return ChunkSearchResult(
        chunk=chunk,
        parent_chunk=None,
        relevance_score=score,
        match_type=match_type,
    )


# =====================================================================
# RRF 算法单元测试
# =====================================================================

class TestRRFFusion:
    """测试 Reciprocal Rank Fusion 算法的正确性。"""

    def test_single_list(self):
        """单路输入时，RRF 分数应按排名递减。"""
        result = HybridSearchService._rrf_fuse(
            ranked_lists=[["a", "b", "c"]],
            k=60,
        )
        assert len(result) == 3
        assert result[0][0] == "a"
        assert result[1][0] == "b"
        assert result[2][0] == "c"
        # 分数递减
        assert result[0][1] > result[1][1] > result[2][1]

    def test_two_lists_consensus(self):
        """双路输入，两路都排第一的文档应该得到最高分。"""
        result = HybridSearchService._rrf_fuse(
            ranked_lists=[["a", "b", "c"], ["a", "c", "d"]],
            k=60,
        )
        # "a" 在两路中都排第 1，应得到最高分
        assert result[0][0] == "a"
        # "a" 的分数应该是 1/(60+1) + 1/(60+1) = 2/(61)
        expected_a = 2.0 / 61
        assert abs(result[0][1] - expected_a) < 1e-9

    def test_two_lists_unique_items(self):
        """双路输入，只出现在一路中的文档也应被包含。"""
        result = HybridSearchService._rrf_fuse(
            ranked_lists=[["a", "b"], ["c", "d"]],
            k=60,
        )
        result_ids = [r[0] for r in result]
        assert "a" in result_ids
        assert "b" in result_ids
        assert "c" in result_ids
        assert "d" in result_ids

    def test_weighted_rrf(self):
        """加权 RRF：高权重通道的排名应更有影响力。"""
        # 向量通道权重 2.0，关键词通道权重 0.5
        result = HybridSearchService._rrf_fuse(
            ranked_lists=[["a", "b"], ["b", "a"]],
            weights=[2.0, 0.5],
            k=60,
        )
        # "a" 在高权重通道排第 1，应得分更高
        assert result[0][0] == "a"

    def test_empty_lists(self):
        """空列表应返回空结果。"""
        result = HybridSearchService._rrf_fuse(
            ranked_lists=[[], []],
            k=60,
        )
        assert result == []

    def test_one_empty_list(self):
        """一路为空时应仍返回另一路的结果。"""
        result = HybridSearchService._rrf_fuse(
            ranked_lists=[["a", "b"], []],
            k=60,
        )
        assert len(result) == 2
        assert result[0][0] == "a"

    def test_k_parameter_effect(self):
        """k 值越小，排名差异对分数的影响越大。"""
        result_k1 = HybridSearchService._rrf_fuse(
            ranked_lists=[["a", "b"]],
            k=1,
        )
        result_k60 = HybridSearchService._rrf_fuse(
            ranked_lists=[["a", "b"]],
            k=60,
        )
        # k=1 时，rank 1 vs rank 2 的分数差异更大
        ratio_k1 = result_k1[0][1] / result_k1[1][1]
        ratio_k60 = result_k60[0][1] / result_k60[1][1]
        assert ratio_k1 > ratio_k60


# =====================================================================
# KeywordSearchService 测试
# =====================================================================

class TestKeywordSearchService:
    """测试关键词搜索服务。"""

    def test_search_wraps_results(self):
        """搜索结果应正确包装为 ChunkSearchResult。"""
        mock_store = MagicMock()
        pc = _make_parent_chunk("p1")
        mock_store.search_parent_chunks_by_keyword.return_value = [
            (pc, 0.85)
        ]

        service = KeywordSearchService(mock_store)
        results = service.search("AI 新闻", top_k=5)

        assert len(results) == 1
        assert results[0].match_type == "keyword"
        assert results[0].relevance_score == 0.85
        assert results[0].parent_chunk == pc

    def test_search_empty_results(self):
        """无匹配时应返回空列表。"""
        mock_store = MagicMock()
        mock_store.search_parent_chunks_by_keyword.return_value = []

        service = KeywordSearchService(mock_store)
        results = service.search("不存在的内容")

        assert results == []

    def test_search_handles_error(self):
        """搜索出错时应优雅处理。"""
        mock_store = MagicMock()
        mock_store.search_parent_chunks_by_keyword.side_effect = Exception("DB error")

        service = KeywordSearchService(mock_store)
        results = service.search("test")

        assert results == []


# =====================================================================
# HybridSearchService 集成测试
# =====================================================================

class TestHybridSearchService:
    """测试混合检索服务的完整流程。"""

    def _make_service(
        self,
        vector_results=None,
        keyword_results=None,
        parent_chunks=None,
    ):
        """构造带 mock 依赖的 HybridSearchService。"""
        mock_vector = MagicMock()
        mock_embed = MagicMock()
        mock_store = MagicMock()
        mock_kw = MagicMock()

        # Embedding
        mock_embed.embed.return_value = [[0.1, 0.2, 0.3]]

        # 向量检索
        mock_vector.search_chunks.return_value = vector_results or []

        # 关键词检索
        mock_kw.search.return_value = keyword_results or []

        # 父 chunk 获取
        mock_store.get_parent_chunks_by_ids.return_value = parent_chunks or []

        service = HybridSearchService(
            vector_store=mock_vector,
            embedding_client=mock_embed,
            article_store=mock_store,
            keyword_search_service=mock_kw,
            rrf_k=60,
        )
        return service

    def test_hybrid_both_channels(self):
        """双通道都有结果时，应融合两路结果。"""
        p1 = _make_parent_chunk("p1", content="向量命中")
        p2 = _make_parent_chunk("p2", content="关键词命中")
        p3 = _make_parent_chunk("p3", content="双重命中")

        # 向量通道: p1(rank0), p3(rank1)
        vec_results = [
            _make_chunk_search_result("p1", 0.95),
            _make_chunk_search_result("p3", 0.85),
        ]
        # 关键词通道: p3(rank0), p2(rank1)
        kw_results = [
            ChunkSearchResult(
                chunk=Chunk(chunk_id="p3_kw", article_id=1, parent_chunk_id="p3",
                            content="", token_count=0, doc_name=""),
                parent_chunk=p3,
                relevance_score=0.8,
                match_type="keyword",
            ),
            ChunkSearchResult(
                chunk=Chunk(chunk_id="p2_kw", article_id=1, parent_chunk_id="p2",
                            content="", token_count=0, doc_name=""),
                parent_chunk=p2,
                relevance_score=0.6,
                match_type="keyword",
            ),
        ]

        service = self._make_service(
            vector_results=vec_results,
            keyword_results=kw_results,
            parent_chunks=[p1, p2, p3],
        )

        results = service.search("测试查询", top_k=5)

        assert len(results) > 0
        # p3 双重命中应排最高
        assert results[0].parent_chunk.parent_chunk_id == "p3"
        assert "semantic" in results[0].match_sources
        assert "keyword" in results[0].match_sources

    def test_vector_only_fallback(self):
        """关键词通道为空时，应仅使用向量结果。"""
        p1 = _make_parent_chunk("p1")

        service = self._make_service(
            vector_results=[_make_chunk_search_result("p1", 0.9)],
            keyword_results=[],
            parent_chunks=[p1],
        )

        results = service.search("test", top_k=5)

        assert len(results) == 1
        assert results[0].match_sources == ["semantic"]

    def test_keyword_only_fallback(self):
        """向量通道失败时，应仅使用关键词结果。"""
        p1 = _make_parent_chunk("p1")

        mock_vector = MagicMock()
        mock_embed = MagicMock()
        mock_store = MagicMock()
        mock_kw = MagicMock()

        # Embedding 失败
        mock_embed.embed.return_value = []

        kw_result = ChunkSearchResult(
            chunk=Chunk(chunk_id="p1_kw", article_id=1, parent_chunk_id="p1",
                        content="", token_count=0, doc_name=""),
            parent_chunk=p1,
            relevance_score=0.7,
            match_type="keyword",
        )
        mock_kw.search.return_value = [kw_result]
        mock_store.get_parent_chunks_by_ids.return_value = [p1]

        service = HybridSearchService(
            vector_store=mock_vector,
            embedding_client=mock_embed,
            article_store=mock_store,
            keyword_search_service=mock_kw,
        )

        results = service.search("test", top_k=5)

        assert len(results) == 1
        assert results[0].match_sources == ["keyword"]

    def test_no_results(self):
        """双通道都无结果时，应返回空列表。"""
        service = self._make_service()
        results = service.search("no match", top_k=5)
        assert results == []


# =====================================================================
# jieba 分词测试
# =====================================================================

class TestJiebaSegmentation:
    """测试 jieba 分词集成。"""

    def test_segment_chinese(self):
        """中文文本应被正确分词。"""
        from infrastructure.postgres_article_store import PostgresArticleStore
        result = PostgresArticleStore._segment_text("人工智能改变世界")
        assert " " in result  # 应该有空格分隔
        assert len(result.split()) > 1  # 应分出多个词

    def test_segment_english(self):
        """英文文本应保持单词分隔。"""
        from infrastructure.postgres_article_store import PostgresArticleStore
        result = PostgresArticleStore._segment_text("artificial intelligence changes the world")
        assert "artificial" in result
        assert "intelligence" in result

    def test_segment_mixed(self):
        """中英混合文本应同时处理。"""
        from infrastructure.postgres_article_store import PostgresArticleStore
        result = PostgresArticleStore._segment_text("AI人工智能 GPT大模型")
        assert "AI" in result
        assert "GPT" in result
        # 应分出多个中文词
        assert len(result.split()) > 2

    def test_segment_empty(self):
        """空文本应返回空字符串。"""
        from infrastructure.postgres_article_store import PostgresArticleStore
        assert PostgresArticleStore._segment_text("") == ""
        assert PostgresArticleStore._segment_text(None) == ""
