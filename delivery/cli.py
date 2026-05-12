"""
CLI 工具 — 方便调试各模块
用法：
    python -m delivery.cli pipeline          # 手动执行一次 Pipeline
    python -m delivery.cli brief             # 手动生成日报
    python -m delivery.cli ask "最近AI有什么进展？"  # 命令行提问
    python -m delivery.cli stats             # 查看数据库统计
    python -m delivery.cli cleanup           # 手动清理旧文章
"""
import argparse
import sys

from core.config import AppConfig
from core.logging import setup_logging
from core.factory import (
    create_article_store,
    create_vector_store,
    create_llm_client,
    create_embedding_client,
    create_chunking_service,
)
from infrastructure.collector import NewsCollector
from services.pipeline_service import PipelineService
from services.query_service import QueryService
from services.brief_service import BriefService


def cmd_pipeline(config: AppConfig):
    """手动执行一次 Pipeline"""
    article_store = create_article_store(config)
    vector_store = create_vector_store(config)
    embedding_client = create_embedding_client(config)
    chunking_service = create_chunking_service(config)
    collector = NewsCollector(config)

    service = PipelineService(
        collector, article_store, vector_store, embedding_client,
        chunking_service=chunking_service,
        markdown_output_path=config.markdown_output_path,
    )
    result = service.run()
    print(f"\n Pipeline 完成:")
    print(f"   抓取: {result['fetched']} 篇")
    print(f"   新增: {result['new']} 篇")
    print(f"   分块: {result.get('chunks', 0)} 子 chunks + {result.get('parent_chunks', 0)} 父 chunks")
    print(f"   向量化: {result['embedded']} 个子 chunks")
    if result["errors"]:
        print(f"    错误: {result['errors']}")


def cmd_brief(config: AppConfig):
    """手动生成日报"""
    article_store = create_article_store(config)
    llm_client = create_llm_client(config)

    service = BriefService(article_store, llm_client, config.output_path)
    brief = service.generate(hours=24)
    print(f"\n 日报已生成:")
    print(f"   文章数: {brief.article_count}")
    print(f"   生成时间: {brief.generated_at}")
    print(f"\n{brief.content_markdown}")


def cmd_ask(config: AppConfig, question: str):
    """命令行提问"""
    article_store = create_article_store(config)
    vector_store = create_vector_store(config)
    llm_client = create_llm_client(config)
    embedding_client = create_embedding_client(config)

    service = QueryService(
        article_store, vector_store, llm_client, embedding_client
    )

    print(f"\n 正在检索并分析...\n")
    final_answer = ""
    for event in service.answer_agent_stream(question):
        if event.event_type == "answer":
            final_answer = event.content
            break
    print(final_answer or "未获得回答，请稍后重试。")


def cmd_stats(config: AppConfig):
    """查看数据库统计"""
    article_store = create_article_store(config)
    stats = article_store.get_stats()

    print(f"\n 数据库统计:")
    print(f"   文章总数: {stats['total']}")
    print(f"   已向量化: {stats['embedded']}")
    print(f"   今日新增: {stats['today_new']}")
    print(f"   最早文章: {stats['oldest_date']}")
    print(f"   来源列表: {', '.join(stats['sources']) if stats['sources'] else '无'}")


def cmd_cleanup(config: AppConfig):
    """手动清理旧文章"""
    article_store = create_article_store(config)
    deleted = article_store.cleanup_old_articles(config.article_retention_days)
    print(f"\n 清理完成: 删除 {deleted} 篇旧文章（保留 {config.article_retention_days} 天）")


def main():
    parser = argparse.ArgumentParser(
        description="Logos 新闻分析助手 — CLI 工具"
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    subparsers.add_parser("pipeline", help="手动执行一次 Pipeline")
    subparsers.add_parser("brief", help="手动生成日报")

    ask_parser = subparsers.add_parser("ask", help="命令行提问")
    ask_parser.add_argument("question", type=str, help="问题内容")

    subparsers.add_parser("stats", help="查看数据库统计")
    subparsers.add_parser("cleanup", help="手动清理旧文章")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = AppConfig()
    setup_logging(config.log_level)

    match args.command:
        case "pipeline":
            cmd_pipeline(config)
        case "brief":
            cmd_brief(config)
        case "ask":
            cmd_ask(config, args.question)
        case "stats":
            cmd_stats(config)
        case "cleanup":
            cmd_cleanup(config)


if __name__ == "__main__":
    main()
