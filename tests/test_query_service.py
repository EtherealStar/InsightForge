"""QueryService 单元测试"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.query_service import QueryService


class TestQueryService:
    """QueryService 测试"""

    @pytest.fixture
    def mock_article_store(self):
        return MagicMock()

    @pytest.fixture
    def mock_vector_store(self):
        return MagicMock()

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

    def test_answer_agent_returns_result(self, service, monkeypatch):
        """answer_agent 应返回 AgentResult。"""
        expected = SimpleNamespace(answer="ok", events=[])
        fake_agent = MagicMock()
        fake_agent.run.return_value = expected
        monkeypatch.setattr(service, "_build_agent", lambda **kwargs: fake_agent)

        result = service.answer_agent("测试问题")
        assert result is expected
        fake_agent.run.assert_called_once_with("测试问题")

    def test_answer_agent_stream_yields_events(self, service, monkeypatch):
        """answer_agent_stream 应透传 Agent 事件。"""
        events = [
            SimpleNamespace(event_type="thought", content="thinking"),
            SimpleNamespace(event_type="answer", content="done"),
        ]
        fake_agent = MagicMock()
        fake_agent.run_stream.return_value = iter(events)
        monkeypatch.setattr(service, "_build_agent", lambda **kwargs: fake_agent)

        chunks = list(service.answer_agent_stream("测试问题"))
        assert chunks == events
        fake_agent.run_stream.assert_called_once_with("测试问题")

    def test_answer_agent_extracts_memory_after_persist(
        self,
        mock_article_store,
        mock_vector_store,
        mock_llm_client,
        mock_embedding_client,
        monkeypatch,
    ):
        session = SimpleNamespace(id="s1")
        session_store = MagicMock()
        session_store.create_general_session.return_value = session
        memory_service = MagicMock()
        service = QueryService(
            mock_article_store,
            mock_vector_store,
            mock_llm_client,
            mock_embedding_client,
            session_store=session_store,
            memory_service=memory_service,
        )
        expected = SimpleNamespace(
            answer="回答",
            events=[SimpleNamespace(to_dict=lambda: {"event_type": "answer", "content": "回答"})],
        )
        fake_agent = MagicMock()
        fake_agent.run.return_value = expected
        monkeypatch.setattr(service, "_build_agent", lambda **kwargs: fake_agent)

        service.answer_agent("问题")

        memory_service.maybe_compact_session.assert_called_once_with("s1")
        memory_service.extract_persistent_memory_candidates.assert_called_once_with(
            session_id="s1",
            latest_question="问题",
            latest_answer="回答",
        )

    def test_answer_agent_stream_extracts_memory_after_persist(
        self,
        mock_article_store,
        mock_vector_store,
        mock_llm_client,
        mock_embedding_client,
        monkeypatch,
    ):
        session = SimpleNamespace(id="s1")
        session_store = MagicMock()
        session_store.create_general_session.return_value = session
        memory_service = MagicMock()
        service = QueryService(
            mock_article_store,
            mock_vector_store,
            mock_llm_client,
            mock_embedding_client,
            session_store=session_store,
            memory_service=memory_service,
        )
        events = [
            SimpleNamespace(event_type="thought", content="thinking", to_dict=lambda: {"event_type": "thought"}),
            SimpleNamespace(event_type="answer", content="done", to_dict=lambda: {"event_type": "answer", "content": "done"}),
        ]
        fake_agent = MagicMock()
        fake_agent.run_stream.return_value = iter(events)
        monkeypatch.setattr(service, "_build_agent", lambda **kwargs: fake_agent)

        assert list(service.answer_agent_stream("问题")) == events

        memory_service.maybe_compact_session.assert_called_once_with("s1")
        memory_service.extract_persistent_memory_candidates.assert_called_once_with(
            session_id="s1",
            latest_question="问题",
            latest_answer="done",
        )
