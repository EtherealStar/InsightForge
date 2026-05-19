from unittest.mock import MagicMock

from core.config_manager import ConfigManager
from infrastructure.hybrid_search_service import HybridSearchService
from infrastructure.keyword_search_service import KeywordSearchService


def test_config_manager_exposes_local_hybrid_search_service(monkeypatch):
    """ConfigManager 应该提供本地关键词 + 向量的混合检索服务。"""
    import core.config_manager as cm
    import agent.tools.builtin as builtin_module

    monkeypatch.setattr(ConfigManager, "_instance", None, raising=False)

    document_store = MagicMock(name="document_store")
    agent_session_store = MagicMock(name="agent_session_store")
    memory_store = MagicMock(name="memory_store")
    task_run_store = MagicMock(name="task_run_store")
    upload_store = MagicMock(name="upload_store")
    redis_state_store = MagicMock(name="redis_state_store")
    file_type_detector = MagicMock(name="file_type_detector")
    file_blob_store = MagicMock(name="file_blob_store")
    archive_extractor = MagicMock(name="archive_extractor")
    document_parser = MagicMock(name="document_parser")
    vector_index = MagicMock(name="vector_index")
    llm_client = MagicMock(name="llm_client")
    embedding_client = MagicMock(name="embedding_client")
    chunking_service = MagicMock(name="chunking_service")
    webhook_service = MagicMock(name="webhook_service")
    deep_research_service = MagicMock(name="deep_research_service")
    competitor_store = MagicMock(name="competitor_store")
    report_store = MagicMock(name="report_store")
    auth_store = MagicMock(name="auth_store")
    config_audit_store = MagicMock(name="config_audit_store")
    intel_store = MagicMock(name="intel_store")
    insight_store = MagicMock(name="insight_store")
    structured_extraction_client = MagicMock(name="structured_extraction_client")
    judge_client = MagicMock(name="judge_client")

    monkeypatch.setattr(cm, "create_document_store", lambda config: document_store)
    monkeypatch.setattr(
        cm, "create_agent_session_store", lambda config: agent_session_store
    )
    monkeypatch.setattr(cm, "create_memory_store", lambda config: memory_store)
    monkeypatch.setattr(cm, "create_task_run_store", lambda config: task_run_store)
    monkeypatch.setattr(cm, "create_upload_store", lambda config: upload_store)
    monkeypatch.setattr(
        cm, "create_redis_state_store", lambda config: redis_state_store
    )
    monkeypatch.setattr(
        cm, "create_file_type_detector", lambda config: file_type_detector
    )
    monkeypatch.setattr(
        cm, "create_file_blob_store", lambda config: file_blob_store
    )
    monkeypatch.setattr(
        cm, "create_archive_extractor", lambda config: archive_extractor
    )
    monkeypatch.setattr(
        cm, "create_document_parser", lambda config: document_parser
    )
    monkeypatch.setattr(cm, "create_competitor_store", lambda config: competitor_store)
    monkeypatch.setattr(cm, "create_report_store", lambda config: report_store)
    monkeypatch.setattr(cm, "create_auth_store", lambda config: auth_store)
    monkeypatch.setattr(
        cm, "create_config_audit_store", lambda config: config_audit_store
    )
    monkeypatch.setattr(cm, "create_intel_store", lambda config: intel_store)
    monkeypatch.setattr(cm, "create_insight_store", lambda config: insight_store)
    monkeypatch.setattr(cm, "create_qdrant_vector_index", lambda config: vector_index)
    monkeypatch.setattr(cm, "create_llm_client", lambda config: llm_client)
    monkeypatch.setattr(
        cm,
        "create_structured_extraction_client",
        lambda config: structured_extraction_client,
    )
    monkeypatch.setattr(cm, "create_judge_client", lambda config: judge_client)
    monkeypatch.setattr(
        cm, "create_embedding_client", lambda config: embedding_client
    )
    monkeypatch.setattr(cm, "create_rerank_client", lambda config: None)
    monkeypatch.setattr(
        cm, "create_chunking_service", lambda config: chunking_service
    )
    monkeypatch.setattr(
        cm, "create_webhook_service", lambda: webhook_service
    )
    monkeypatch.setattr(
        cm, "create_deep_research_service", lambda: deep_research_service
    )
    register_mock = MagicMock(return_value=6)
    monkeypatch.setattr(
        builtin_module, "register_builtin_tools", register_mock
    )

    mgr = ConfigManager()
    service = mgr.hybrid_search_service

    assert isinstance(service, HybridSearchService)
    assert isinstance(service._keyword_search, KeywordSearchService)
    assert service._document_store is document_store
    assert service._vector_index is vector_index
    assert service._embedding_client is embedding_client
    assert service._keyword_search._document_store is document_store
    register_mock.assert_called_with(mgr, refresh=True)
