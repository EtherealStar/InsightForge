"""评估执行器 — 编排数据采集、适配、评估、结果输出

LogosEvalRunner 是评估模块的核心编排器：
1. 加载黄金数据集
2. 调用 Logos 组件获取系统实际输出
3. 通过 adapters 转换为 RAGAs 数据格式
4. 调用 ragas.evaluate() 计算指标
5. 保存评估结果
"""

import json
import os
import time
from datetime import datetime

import structlog
from ragas import evaluate, EvaluationDataset, SingleTurnSample

from evals.adapters import (
    retrieval_to_sample,
    agent_result_to_sample,
    agent_events_to_multi_turn,
    build_evaluation_dataset,
)
from evals.config import (
    load_eval_config,
    create_judge_llm,
    create_judge_embeddings,
)
from evals.metrics import get_metrics_by_suite

logger = structlog.get_logger(__name__)

_DEFAULT_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
_DEFAULT_DATASET_PATH = os.path.join(
    os.path.dirname(__file__), "datasets", "golden_qa.json"
)


class LogosEvalRunner:
    """Logos RAGAs 评估执行器。

    封装完整的评估流程：数据采集 → 适配 → 评估 → 结果输出。

    Args:
        config_path: eval_config.json 路径（可选）。
        results_dir: 评估结果输出目录。
    """

    def __init__(
        self,
        config_path: str | None = None,
        results_dir: str = _DEFAULT_RESULTS_DIR,
    ):
        self.config = load_eval_config(config_path)
        self.results_dir = results_dir
        os.makedirs(self.results_dir, exist_ok=True)

        self._judge_llm = None
        self._judge_embeddings = None

    @property
    def judge_llm(self):
        if self._judge_llm is None:
            self._judge_llm = create_judge_llm(self.config)
        return self._judge_llm

    @property
    def judge_embeddings(self):
        if self._judge_embeddings is None:
            self._judge_embeddings = create_judge_embeddings(self.config)
        return self._judge_embeddings

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def run_retrieval_eval(
        self,
        dataset_path: str | None = None,
    ) -> dict:
        """运行维度 ① 检索质量评估。

        流程：加载黄金数据集 → 对每个问题执行混合检索 → 评估检索质量。

        Args:
            dataset_path: 黄金数据集路径。

        Returns:
            dict: 评估结果（含每个指标的分数）。
        """
        golden = self._load_golden_dataset(dataset_path)
        samples = self._collect_retrieval_samples(golden)

        if not samples:
            logger.warning("eval.no_samples", suite="retrieval")
            return {"error": "无法采集到有效样本"}

        has_ref = any(s.reference for s in samples)
        suite = "retrieval_ref" if has_ref else "retrieval"
        metrics = get_metrics_by_suite(suite)

        return self._run_evaluate(samples, metrics, suite_name="retrieval")

    def run_e2e_eval(
        self,
        dataset_path: str | None = None,
    ) -> dict:
        """运行维度 ② 端到端问答质量评估。

        流程：加载黄金数据集 → 对每个问题执行 Agent 问答 → 评估回答质量。

        Args:
            dataset_path: 黄金数据集路径。

        Returns:
            dict: 评估结果。
        """
        golden = self._load_golden_dataset(dataset_path)
        samples = self._collect_e2e_samples(golden)

        if not samples:
            logger.warning("eval.no_samples", suite="e2e")
            return {"error": "无法采集到有效样本"}

        metrics = get_metrics_by_suite("e2e")
        return self._run_evaluate(samples, metrics, suite_name="e2e")

    def run_agent_eval(
        self,
        dataset_path: str | None = None,
    ) -> dict:
        """运行维度 ③ Agent 工具调用质量评估。

        流程：加载黄金数据集 → 对每个问题执行 Agent → 评估工具调用准确性。

        Args:
            dataset_path: 黄金数据集路径。

        Returns:
            dict: 评估结果。
        """
        golden = self._load_golden_dataset(dataset_path)
        samples = self._collect_agent_samples(golden)

        if not samples:
            logger.warning("eval.no_samples", suite="agent")
            return {"error": "无法采集到有效样本"}

        metrics = get_metrics_by_suite("agent")
        return self._run_evaluate(samples, metrics, suite_name="agent")

    def run_all(
        self,
        dataset_path: str | None = None,
    ) -> dict:
        """运行全部三个维度的评估。

        Args:
            dataset_path: 黄金数据集路径。

        Returns:
            dict: 包含三个维度评估结果的汇总字典。
        """
        results = {}

        logger.info("eval.run_all_start")

        for suite_name, run_fn in [
            ("retrieval", self.run_retrieval_eval),
            ("e2e", self.run_e2e_eval),
            ("agent", self.run_agent_eval),
        ]:
            logger.info("eval.suite_start", suite=suite_name)
            try:
                results[suite_name] = run_fn(dataset_path)
            except Exception as e:
                logger.exception("eval.suite_error", suite=suite_name, error=str(e))
                results[suite_name] = {"error": str(e)}

        # 保存汇总结果
        self._save_results(results, "all")
        return results

    # ------------------------------------------------------------------
    # 数据采集
    # ------------------------------------------------------------------

    def _collect_retrieval_samples(
        self, golden: list[dict]
    ) -> list[SingleTurnSample]:
        """对黄金数据集执行混合检索，采集检索样本。"""
        from core.config_manager import ConfigManager

        mgr = ConfigManager()
        hybrid_search = mgr.hybrid_search_service
        top_k = self.config.get("default_top_k", 5)

        samples = []
        for i, item in enumerate(golden):
            question = item["question"]
            reference = item.get("reference")

            logger.info(
                "eval.collect_retrieval",
                index=i + 1,
                total=len(golden),
                question=question[:60],
            )

            try:
                results = hybrid_search.search(query=question, top_k=top_k)

                # 为检索评估创建一个占位回答（检索指标不依赖回答内容）
                sample = retrieval_to_sample(
                    question=question,
                    hybrid_results=results,
                    agent_answer="",  # 检索评估不需要回答
                    reference=reference,
                )
                samples.append(sample)

            except Exception as e:
                logger.warning(
                    "eval.collect_retrieval_error",
                    question=question[:60],
                    error=str(e),
                )

        return samples

    def _collect_e2e_samples(
        self, golden: list[dict]
    ) -> list[SingleTurnSample]:
        """对黄金数据集执行 Agent 问答，采集端到端样本。"""
        from core.config_manager import ConfigManager
        from core.factory import create_query_service

        mgr = ConfigManager()
        query_service = create_query_service(mgr.config, mgr)

        samples = []
        for i, item in enumerate(golden):
            question = item["question"]
            reference = item.get("reference")

            logger.info(
                "eval.collect_e2e",
                index=i + 1,
                total=len(golden),
                question=question[:60],
            )

            try:
                result = query_service.answer_agent(question)

                sample = agent_result_to_sample(
                    question=question,
                    result=result,
                    reference=reference,
                )
                samples.append(sample)

            except Exception as e:
                logger.warning(
                    "eval.collect_e2e_error",
                    question=question[:60],
                    error=str(e),
                )

        return samples

    def _collect_agent_samples(self, golden: list[dict]) -> list:
        """对黄金数据集执行 Agent，采集多轮交互样本。"""
        from core.config_manager import ConfigManager
        from core.factory import create_query_service

        mgr = ConfigManager()
        query_service = create_query_service(mgr.config, mgr)

        samples = []
        for i, item in enumerate(golden):
            question = item["question"]
            reference = item.get("reference")
            ref_tools = item.get("expected_tools")

            logger.info(
                "eval.collect_agent",
                index=i + 1,
                total=len(golden),
                question=question[:60],
            )

            try:
                result = query_service.answer_agent(question)

                sample = agent_events_to_multi_turn(
                    question=question,
                    events=result.events,
                    reference=reference,
                    reference_tool_calls=ref_tools,
                )
                samples.append(sample)

            except Exception as e:
                logger.warning(
                    "eval.collect_agent_error",
                    question=question[:60],
                    error=str(e),
                )

        return samples

    # ------------------------------------------------------------------
    # 评估执行
    # ------------------------------------------------------------------

    def _run_evaluate(
        self,
        samples: list,
        metrics: list,
        suite_name: str,
    ) -> dict:
        """执行 RAGAs 评估并保存结果。"""
        logger.info(
            "eval.evaluate_start",
            suite=suite_name,
            sample_count=len(samples),
            metric_count=len(metrics),
        )

        start = time.time()

        dataset = EvaluationDataset(samples=samples)
        results = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=self.judge_llm,
            embeddings=self.judge_embeddings,
        )

        elapsed = round(time.time() - start, 2)

        # 转为 dict
        result_dict = {
            "suite": suite_name,
            "sample_count": len(samples),
            "elapsed_seconds": elapsed,
            "scores": dict(results),
        }

        logger.info(
            "eval.evaluate_complete",
            suite=suite_name,
            elapsed_seconds=elapsed,
            scores=result_dict["scores"],
        )

        self._save_results(result_dict, suite_name)
        return result_dict

    # ------------------------------------------------------------------
    # 数据加载与结果保存
    # ------------------------------------------------------------------

    def _load_golden_dataset(self, path: str | None = None) -> list[dict]:
        """加载黄金 QA 数据集。"""
        dataset_path = path or _DEFAULT_DATASET_PATH
        if not os.path.exists(dataset_path):
            raise FileNotFoundError(
                f"黄金数据集不存在: {dataset_path}\n"
                f"请创建 evals/datasets/golden_qa.json。"
            )

        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        logger.info("eval.dataset_loaded", path=dataset_path, count=len(data))
        return data

    def _save_results(self, results: dict, suite_name: str) -> str:
        """将评估结果保存为 JSON 文件。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"eval_{suite_name}_{timestamp}.json"
        filepath = os.path.join(self.results_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        logger.info("eval.results_saved", path=filepath)
        return filepath
