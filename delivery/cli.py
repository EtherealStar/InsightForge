"""CLI helpers for local InsightForge operations.

Usage:
    python -m delivery.cli pipeline
    python -m delivery.cli ask "Cursor 和 Windsurf 有什么区别？"
"""
import argparse
import secrets
import sys

from core.config import AppConfig
from core.config_manager import get_config_manager
from core.factory import (
    create_chunking_service,
    create_document_store,
    create_embedding_client,
    create_auth_store,
    create_qdrant_vector_index,
)
from core.logging import setup_logging
from infrastructure.collector import NewsCollector
from services.pipeline_service import PipelineService
from delivery.auth import hash_api_key
from models.auth import ActorRole, ApiKeyRecord


def cmd_pipeline(config: AppConfig) -> None:
    """Run the intel ingestion pipeline once."""
    document_store = create_document_store(config)
    vector_index = create_qdrant_vector_index(config)
    embedding_client = create_embedding_client(config)
    chunking_service = create_chunking_service(config)
    collector = NewsCollector(config)

    from core.factory import create_document_clustering_service, create_document_version_service, create_source_profile_store
    from services.source_governance_service import SourceGovernanceService

    service = PipelineService(
        collector,
        document_store,
        vector_index,
        embedding_client,
        chunking_service=chunking_service,
        markdown_output_path=config.markdown_output_path,
        source_governance_service=SourceGovernanceService(create_source_profile_store(config)),
        document_clustering_service=create_document_clustering_service(config),
        document_version_service=create_document_version_service(config),
        source_governance_enabled=config.source_governance_enabled,
    )
    result = service.run()
    print("\nPipeline 完成:")
    print(f"   抓取: {result['fetched']} 篇")
    print(f"   SourceDocument: {result['documents']} 个")
    print(
        f"   分块: {result.get('chunks', 0)} 子 chunks + "
        f"{result.get('parent_chunks', 0)} 父 chunks"
    )
    print(f"   向量化: {result['embedded']} 个子 chunks")
    print(f"   facts: +{result['facts_created']} / 更新 {result['facts_updated']}")
    if result["errors"]:
        print(f"   错误: {result['errors']}")


def cmd_ask(question: str) -> None:
    """Ask through the agent query service."""
    service = get_config_manager().query_service

    print("\n正在检索并分析...\n")
    final_answer = ""
    for event in service.answer_agent_stream(question):
        if event.event_type == "answer":
            final_answer = event.content
            break
    print(final_answer or "未获得回答，请稍后重试。")


def cmd_create_api_key(config: AppConfig, name: str, role: str) -> None:
    """Create an application API key and print the plaintext once."""
    api_key = "if_" + secrets.token_urlsafe(32)
    store = create_auth_store(config)
    record = ApiKeyRecord(
        name=name,
        key_hash=hash_api_key(api_key),
        role=ActorRole(role),
        created_by="cli",
    )
    saved = store.create_api_key(record)
    print("API Key created.")
    print(f"Name: {saved.name}")
    print(f"Role: {saved.role.value if hasattr(saved.role, 'value') else saved.role}")
    print(f"ID: {saved.id}")
    print("Plaintext key, shown once:")
    print(api_key)


def main() -> None:
    parser = argparse.ArgumentParser(description="InsightForge 竞品分析助手 CLI")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    subparsers.add_parser("pipeline", help="手动执行一次情报采集 Pipeline")

    ask_parser = subparsers.add_parser("ask", help="命令行提问")
    ask_parser.add_argument("question", type=str, help="问题内容")

    auth_parser = subparsers.add_parser("auth", help="认证管理")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command")
    create_key_parser = auth_subparsers.add_parser(
        "create-key",
        help="创建应用 API Key，明文只打印一次",
    )
    create_key_parser.add_argument("--name", required=True, help="API Key 名称")
    create_key_parser.add_argument(
        "--role",
        required=True,
        choices=[role.value for role in ActorRole],
        help="角色",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = AppConfig()
    setup_logging(config.log_level)

    match args.command:
        case "pipeline":
            cmd_pipeline(config)
        case "ask":
            cmd_ask(args.question)
        case "auth":
            if args.auth_command == "create-key":
                cmd_create_api_key(config, args.name, args.role)
            else:
                auth_parser.print_help()
                sys.exit(1)


if __name__ == "__main__":
    main()
