"""从 Logos 知识库文章自动生成 RAGAs 合成测试数据集

使用 RAGAs TestsetGenerator 基于知识库中的真实文章内容，
自动生成多样化的 QA 测试对（单跳、多跳、推理等类型），
用于评估 RAG 管线的检索和生成质量。

用法：
    python -m evals.scripts.generate_testset [--count 50] [--size 30] [--output PATH]
"""

import argparse
import json
import os
import sys

import structlog

logger = structlog.get_logger(__name__)


def generate_from_logos_articles(
    article_count: int = 50,
    testset_size: int = 30,
    output_path: str | None = None,
) -> None:
    """从数据库取出文章，使用 RAGAs TestsetGenerator 生成测试集。

    Args:
        article_count: 从数据库获取的文章数量（作为源文档）。
        testset_size: 生成的测试集大小。
        output_path: 输出 JSON 文件路径。
    """
    from core.config_manager import ConfigManager
    from evals.config import load_eval_config, create_judge_llm, create_judge_embeddings

    # 1. 获取文章
    logger.info(
        "testset.fetch_articles",
        article_count=article_count,
    )
    mgr = ConfigManager()
    store = mgr.article_store
    articles = store.get_recent(hours=168, limit=article_count)  # 最近 7 天

    if not articles:
        logger.error("testset.no_articles", msg="知识库中没有文章，请先运行 Pipeline。")
        sys.exit(1)

    logger.info("testset.articles_fetched", count=len(articles))

    # 2. 转换为 LangChain Document 格式
    from langchain_core.documents import Document

    docs = []
    for a in articles:
        content = a.content_markdown if hasattr(a, "content_markdown") and a.content_markdown else a.content
        if not content:
            continue
        docs.append(Document(
            page_content=content,
            metadata={
                "source": a.source,
                "title": a.title,
                "url": a.url,
            },
        ))

    if not docs:
        logger.error("testset.no_valid_docs", msg="没有有效的文章内容。")
        sys.exit(1)

    logger.info("testset.docs_prepared", count=len(docs))

    # 3. 初始化生成器
    config = load_eval_config()
    judge_llm = create_judge_llm(config)
    judge_embeddings = create_judge_embeddings(config)

    from ragas.testset import TestsetGenerator

    generator = TestsetGenerator(
        llm=judge_llm,
        embedding_model=judge_embeddings,
    )

    # 4. 生成测试集
    logger.info(
        "testset.generating",
        doc_count=len(docs),
        testset_size=testset_size,
    )

    testset = generator.generate_with_langchain_docs(
        docs,
        testset_size=testset_size,
    )

    # 5. 保存结果
    if output_path is None:
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "datasets", "generated",
        )
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "testset.json")

    df = testset.to_pandas()
    df.to_json(output_path, orient="records", force_ascii=False, indent=2)

    logger.info(
        "testset.saved",
        path=output_path,
        size=len(df),
    )
    print(f"\n✅ 测试集已生成: {output_path} ({len(df)} 条)")


def main():
    parser = argparse.ArgumentParser(
        description="从 Logos 知识库生成 RAGAs 合成测试数据集",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        help="从数据库获取的文章数量（默认 50）",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=30,
        help="生成的测试集大小（默认 30）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出 JSON 文件路径",
    )

    args = parser.parse_args()

    generate_from_logos_articles(
        article_count=args.count,
        testset_size=args.size,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
