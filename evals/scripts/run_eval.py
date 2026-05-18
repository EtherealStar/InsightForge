"""RAGAs 评估 CLI 入口 — 一键运行评估

用法：
    # 运行全部三个维度评估
    python -m evals.scripts.run_eval --suite all

    # 仅运行检索质量评估
    python -m evals.scripts.run_eval --suite retrieval

    # 仅运行端到端问答评估
    python -m evals.scripts.run_eval --suite e2e

    # 仅运行 Agent 工具调用评估
    python -m evals.scripts.run_eval --suite agent

    # 快速核心指标评估
    python -m evals.scripts.run_eval --suite quick

    # 指定自定义数据集和配置
    python -m evals.scripts.run_eval --suite all --dataset path/to/qa.json --config path/to/config.json
"""

import argparse
import json
import sys

import structlog

logger = structlog.get_logger(__name__)


def _print_results(results: dict) -> None:
    """将评估结果格式化输出到控制台。"""
    print("\n" + "=" * 60)
    print("  Logos × RAGAs 评估报告")
    print("=" * 60)

    if "error" in results:
        print(f"\n❌ 评估失败: {results['error']}")
        return

    # 全量评估（包含多个子 suite）
    if all(k in results for k in ["retrieval", "e2e", "agent"]):
        for suite_name, suite_result in results.items():
            _print_suite_result(suite_name, suite_result)
    else:
        # 单个 suite 的结果
        _print_suite_result(
            results.get("suite", "unknown"),
            results,
        )

    print("\n" + "=" * 60)


def _print_suite_result(suite_name: str, result: dict) -> None:
    """打印单个评估套件的结果。"""
    suite_labels = {
        "retrieval": "① 检索质量",
        "e2e": "② 端到端问答",
        "agent": "③ Agent 工具调用",
        "quick": "快速评估",
    }
    label = suite_labels.get(suite_name, suite_name)

    print(f"\n── {label} ──")

    if isinstance(result, dict) and "error" in result:
        print(f"  ❌ {result['error']}")
        return

    scores = result.get("scores", result)
    sample_count = result.get("sample_count", "?")
    elapsed = result.get("elapsed_seconds", "?")

    print(f"  样本数: {sample_count}  |  耗时: {elapsed}s")
    print()

    if isinstance(scores, dict):
        for metric_name, score in scores.items():
            if isinstance(score, (int, float)):
                bar = _score_bar(score)
                print(f"  {metric_name:40s}  {score:.4f}  {bar}")
            else:
                print(f"  {metric_name:40s}  {score}")


def _score_bar(score: float, width: int = 20) -> str:
    """生成分数可视化条。"""
    filled = int(score * width)
    bar = "█" * filled + "░" * (width - filled)

    if score >= 0.8:
        status = "✅"
    elif score >= 0.6:
        status = "⚠️"
    else:
        status = "❌"

    return f"[{bar}] {status}"


def main():
    parser = argparse.ArgumentParser(
        description="Logos × RAGAs 评估工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "评估套件:\n"
            "  retrieval   维度①: RAG 检索质量（Context Precision / Recall）\n"
            "  e2e         维度②: 端到端问答（Faithfulness / Response Relevancy）\n"
            "  agent       维度③: Agent 工具调用（ToolCallAccuracy / GoalAccuracy）\n"
            "  all         全部三个维度\n"
            "  quick       快速核心指标（Faithfulness + Relevancy + Precision）\n"
        ),
    )
    parser.add_argument(
        "--suite",
        type=str,
        default="all",
        choices=["retrieval", "e2e", "agent", "all", "quick"],
        help="评估套件（默认: all）",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="黄金数据集路径（默认: evals/datasets/golden_qa.json）",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="评估配置文件路径（默认: evals/eval_config.json）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="结果输出目录（默认: evals/results/）",
    )

    args = parser.parse_args()

    # 初始化 Runner
    from evals.runner import LogosEvalRunner

    runner_kwargs = {}
    if args.config:
        runner_kwargs["config_path"] = args.config
    if args.output:
        runner_kwargs["results_dir"] = args.output

    runner = LogosEvalRunner(**runner_kwargs)

    # 执行评估
    print(f"\n🚀 开始评估（套件: {args.suite}）...")

    try:
        if args.suite == "all":
            results = runner.run_all(dataset_path=args.dataset)
        elif args.suite == "retrieval":
            results = runner.run_retrieval_eval(dataset_path=args.dataset)
        elif args.suite == "e2e":
            results = runner.run_e2e_eval(dataset_path=args.dataset)
        elif args.suite == "agent":
            results = runner.run_agent_eval(dataset_path=args.dataset)
        elif args.suite == "quick":
            # quick 使用 e2e 通道但用 quick 指标
            results = runner.run_e2e_eval(dataset_path=args.dataset)
        else:
            print(f"❌ 未知套件: {args.suite}")
            sys.exit(1)

        _print_results(results)

    except FileNotFoundError as e:
        print(f"\n❌ 文件未找到: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception("eval.cli_error", error=str(e))
        print(f"\n❌ 评估执行异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
