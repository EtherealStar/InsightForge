from __future__ import annotations

import math
import json
from types import SimpleNamespace

import pytest


class _FakeFrame:
    def __init__(self, records):
        self._records = records

    def to_dict(self, orient="records"):
        assert orient == "records"
        return self._records


class _FakeEvaluateResult:
    def __init__(self):
        self.scores = [
            {"faithfulness": 1.0, "response_relevancy": 0.5},
            {"faithfulness": math.nan, "response_relevancy": 0.75},
        ]

    def to_pandas(self):
        return _FakeFrame(
            [
                {
                    "user_input": "q1",
                    "faithfulness": 1.0,
                    "response_relevancy": 0.5,
                },
                {
                    "user_input": "q2",
                    "faithfulness": math.nan,
                    "response_relevancy": 0.75,
                },
            ]
        )


class _OneMetricEvaluateResult:
    def __init__(self, metric_name="answer_relevancy", score=0.8):
        self.scores = [{metric_name: score}]
        self._record = {
            "user_input": "q",
            metric_name: score,
        }

    def to_pandas(self):
        return _FakeFrame([self._record])


def test_run_evaluate_returns_structured_results(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    runner._judge_llm = object()
    runner._judge_embeddings = object()

    saved = {}

    def fake_save_results(results, suite_name):
        saved["suite"] = suite_name
        saved["results"] = results
        return "saved.json"

    monkeypatch.setattr(runner, "_save_results", fake_save_results)
    monkeypatch.setattr(runner_module, "evaluate", lambda **kwargs: _FakeEvaluateResult())

    result = runner._run_evaluate(
        samples=[SimpleNamespace(), SimpleNamespace()],
        metrics=[SimpleNamespace(), SimpleNamespace()],
        suite_name="e2e",
        collection_errors=[{"stage": "collect", "error": "boom"}],
    )

    assert saved["suite"] == "e2e"
    assert result["scores"]["faithfulness"] == 1.0
    assert result["scores"]["response_relevancy"] == 0.625
    assert result["per_sample_scores"][1]["faithfulness"] is None
    assert result["failed_samples"] == [
        {"index": 1, "question": "q2", "failed_metrics": ["faithfulness"]}
    ]
    assert result["collection_errors"][0]["error"] == "boom"


def test_run_evaluate_marks_all_null_metric_unhealthy(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    runner._judge_llm = object()
    runner._judge_embeddings = object()

    class NullEvaluateResult:
        scores = [{"answer_relevancy": None}, {"answer_relevancy": None}]

        def to_pandas(self):
            return _FakeFrame(
                [
                    {"user_input": "q1", "answer_relevancy": None},
                    {"user_input": "q2", "answer_relevancy": None},
                ]
            )

    monkeypatch.setattr(runner_module, "evaluate", lambda **kwargs: NullEvaluateResult())

    result = runner._run_evaluate(
        samples=[SimpleNamespace(), SimpleNamespace()],
        metrics=[SimpleNamespace()],
        suite_name="e2e",
    )

    assert result["scores"]["answer_relevancy"] is None
    assert result["judge_llm"] == {
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
    }
    assert result["metric_health_issues"] == [
        {
            "metric": "answer_relevancy",
            "issue": "all_null",
            "sample_count": 2,
            "null_count": 2,
            "message": "该指标所有样本均未返回有效分数，通常表示 judge 调用结果不可解析或兼容端点返回格式异常。",
            "judge_call_exceptions": False,
            "failed_sample_summaries": [
                {
                    "index": 0,
                    "question": "q1",
                    "failed_metrics": ["answer_relevancy"],
                },
                {
                    "index": 1,
                    "question": "q2",
                    "failed_metrics": ["answer_relevancy"],
                },
            ],
            "judge_llm": {
                "model": "gpt-4o-mini",
                "base_url": "https://api.openai.com/v1",
            },
        }
    ]


def test_run_evaluate_merges_retrieval_article_ids(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    runner._judge_llm = object()
    runner._judge_embeddings = object()

    class FakeEvaluateResult:
        def __init__(self):
            self.scores = [{"metric_a": 1.0}]

        def to_pandas(self):
            return _FakeFrame([{"user_input": "q1", "metric_a": 1.0}])

    monkeypatch.setattr(runner_module, "evaluate", lambda **kwargs: FakeEvaluateResult())

    result = runner._run_evaluate(
        samples=[SimpleNamespace()],
        metrics=[SimpleNamespace()],
        suite_name="retrieval",
        sample_metadata=[
            {
                "source_article_ids": [1, 2],
                "retrieved_article_ids": [2, 3],
                "article_id_hit": True,
                "article_id_recall": 0.5,
                "article_id_precision": 0.5,
            }
        ],
    )

    assert result["per_sample_results"][0]["source_article_ids"] == [1, 2]
    assert result["per_sample_results"][0]["retrieved_article_ids"] == [2, 3]
    assert result["retrieval_article_id_scores"] == {
        "article_id_hit_rate": 1.0,
        "article_id_recall": 0.5,
        "article_id_precision": 0.5,
    }


def test_run_replay_eval_e2e_uses_existing_result(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    source_path = tmp_path / "eval_e2e_old.json"
    source_path.write_text(
        json.dumps(
            {
                "suite": "e2e",
                "per_sample_results": [
                    {
                        "user_input": "q",
                        "retrieved_contexts": ["ctx"],
                        "response": "answer",
                        "reference": "ref",
                    }
                ],
                "collection_errors": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    runner._judge_llm = object()
    runner._judge_embeddings = object()
    monkeypatch.setattr(
        runner,
        "_collect_e2e_samples",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("replay must not collect e2e samples")
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "evaluate",
        lambda **kwargs: _OneMetricEvaluateResult("answer_relevancy", 0.8),
    )

    result = runner.run_replay_eval(str(source_path), suite_name="e2e")

    assert result["suite"] == "e2e"
    assert result["sample_count"] == 1
    assert result["scores"]["answer_relevancy"] == 0.8
    assert result["replay_source_path"] == str(source_path)


def test_run_replay_eval_retrieval_keeps_local_precision(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    source_path = tmp_path / "eval_retrieval_old.json"
    source_path.write_text(
        json.dumps(
            {
                "suite": "retrieval",
                "per_sample_results": [
                    {
                        "user_input": "q",
                        "retrieved_contexts": ["ctx"],
                        "response": "",
                        "reference": "ref",
                        "source_article_ids": [1, 2],
                        "retrieved_article_ids": [1, 3],
                        "article_id_hit": True,
                        "article_id_recall": 0.5,
                        "article_id_precision": 0.5,
                    }
                ],
                "collection_errors": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    runner._judge_llm = object()
    runner._judge_embeddings = object()

    class LLMContextPrecisionWithoutReference:
        pass

    class LLMContextRecall:
        pass

    captured = {}

    def fake_get_metrics_by_suite(suite):
        captured["suite"] = suite
        return [LLMContextPrecisionWithoutReference(), LLMContextRecall()]

    def fake_evaluate(**kwargs):
        captured["metric_names"] = [
            metric.__class__.__name__ for metric in kwargs["metrics"]
        ]
        return _OneMetricEvaluateResult("context_recall", 0.75)

    monkeypatch.setattr(runner_module, "get_metrics_by_suite", fake_get_metrics_by_suite)
    monkeypatch.setattr(runner_module, "evaluate", fake_evaluate)

    result = runner.run_replay_eval(str(source_path), suite_name="retrieval")

    assert captured["suite"] == "retrieval_ref"
    assert captured["metric_names"] == ["LLMContextRecall"]
    assert result["scores"]["llm_context_precision_without_reference"] == 0.5
    assert result["scores"]["context_recall"] == 0.75


def test_run_replay_eval_all_replays_three_subsuites(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    source_path = tmp_path / "eval_all_old.json"
    source_path.write_text(
        json.dumps(
            {
                "suite": "all",
                "retrieval": {
                    "suite": "retrieval",
                    "per_sample_results": [
                        {
                            "user_input": "q1",
                            "retrieved_contexts": ["ctx"],
                            "response": "",
                            "reference": "ref",
                        }
                    ],
                },
                "e2e": {
                    "suite": "e2e",
                    "per_sample_results": [
                        {
                            "user_input": "q2",
                            "retrieved_contexts": ["ctx"],
                            "response": "answer",
                            "reference": "ref",
                        }
                    ],
                },
                "agent": {
                    "suite": "agent",
                    "per_sample_results": [
                        {
                            "user_input": [
                                {"type": "human", "content": "q3"},
                                {"type": "ai", "content": "answer"},
                            ],
                            "reference": "ref",
                        }
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    calls = []

    def fake_run_replay_suite(payload, *, result_path, suite_name):
        calls.append(suite_name)
        return {"suite": suite_name, "replay_source_path": result_path}

    monkeypatch.setattr(runner, "_run_replay_suite", fake_run_replay_suite)

    result = runner.run_replay_eval(str(source_path), suite_name="all")

    assert calls == ["retrieval", "e2e", "agent"]
    assert set(result.keys()) == {"retrieval", "e2e", "agent"}


def test_run_replay_eval_agent_restores_multi_turn_samples(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    source_path = tmp_path / "eval_agent_old.json"
    source_path.write_text(
        json.dumps(
            {
                "suite": "agent",
                "per_sample_results": [
                    {
                        "user_input": [
                            {"type": "human", "content": "q"},
                            {"type": "ai", "content": "answer"},
                        ],
                        "reference": "ref",
                    }
                ],
                "collection_errors": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    runner._judge_llm = object()
    runner._judge_embeddings = object()
    monkeypatch.setattr(
        runner,
        "_collect_agent_samples",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("replay must not collect agent samples")
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "evaluate",
        lambda **kwargs: _OneMetricEvaluateResult("tool_call_accuracy", 1.0),
    )

    result = runner.run_replay_eval(str(source_path), suite_name="agent")

    assert result["suite"] == "agent"
    assert result["sample_count"] == 1
    assert result["scores"]["tool_call_accuracy"] == 1.0


def test_run_replay_eval_rejects_suite_mismatch(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    source_path = tmp_path / "eval_retrieval_old.json"
    source_path.write_text(
        json.dumps({"suite": "retrieval", "per_sample_results": []}),
        encoding="utf-8",
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    with pytest.raises(ValueError, match="请求回放 'e2e'"):
        runner.run_replay_eval(str(source_path), suite_name="e2e")


def test_run_quick_eval_uses_quick_metrics(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    runner._judge_llm = object()
    runner._judge_embeddings = object()

    monkeypatch.setattr(
        runner,
        "_load_golden_dataset",
        lambda dataset_path=None: [{"question": "q", "reference": "ref"}],
    )
    monkeypatch.setattr(
        runner,
        "_collect_e2e_samples",
        lambda golden, suite_name="e2e": ([SimpleNamespace(reference="ref")], []),
    )

    captured = {}

    def fake_get_metrics_by_suite(suite):
        captured["suite"] = suite
        return ["metric"]

    def fake_run_evaluate(samples, metrics, suite_name, collection_errors=None):
        captured["suite_name"] = suite_name
        captured["metrics"] = metrics
        captured["collection_errors"] = collection_errors
        return {"suite": suite_name, "scores": {"metric": 1.0}}

    monkeypatch.setattr(runner_module, "get_metrics_by_suite", fake_get_metrics_by_suite)
    monkeypatch.setattr(runner, "_run_evaluate", fake_run_evaluate)

    result = runner.run_quick_eval()

    assert captured["suite"] == "quick"
    assert captured["suite_name"] == "quick"
    assert result["suite"] == "quick"


def test_run_e2e_eval_uses_e2e_metrics(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    runner._judge_llm = object()
    runner._judge_embeddings = object()

    monkeypatch.setattr(
        runner,
        "_load_golden_dataset",
        lambda dataset_path=None: [{"question": "q", "reference": "ref"}],
    )
    monkeypatch.setattr(
        runner,
        "_collect_e2e_samples",
        lambda golden, suite_name="e2e": ([SimpleNamespace(reference="ref")], []),
    )

    captured = {}

    def fake_get_metrics_by_suite(suite):
        captured["suite"] = suite
        return ["faithfulness_metric", "response_relevancy_metric"]

    def fake_run_evaluate(samples, metrics, suite_name, collection_errors=None):
        captured["suite_name"] = suite_name
        captured["metrics"] = metrics
        return {"suite": suite_name, "scores": {"faithfulness": 1.0}}

    monkeypatch.setattr(runner_module, "get_metrics_by_suite", fake_get_metrics_by_suite)
    monkeypatch.setattr(runner, "_run_evaluate", fake_run_evaluate)

    result = runner.run_e2e_eval()

    assert captured["suite"] == "e2e"
    assert captured["suite_name"] == "e2e"
    assert result["suite"] == "e2e"


def test_run_all_returns_three_suites(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    saved = {}

    monkeypatch.setattr(runner, "run_retrieval_eval", lambda dataset_path=None: {"suite": "retrieval"})
    monkeypatch.setattr(runner, "run_e2e_eval", lambda dataset_path=None: {"suite": "e2e"})
    monkeypatch.setattr(runner, "run_agent_eval", lambda dataset_path=None: {"suite": "agent"})

    def fake_save_results(results, suite_name):
        saved["suite"] = suite_name
        saved["results"] = results
        return "saved.json"

    monkeypatch.setattr(runner, "_save_results", fake_save_results)

    result = runner.run_all()

    assert set(result.keys()) == {"retrieval", "e2e", "agent"}
    assert saved["suite"] == "all"
    assert set(saved["results"].keys()) == {"retrieval", "e2e", "agent"}


def test_eval_cli_rejects_e2e_relevancy_suite(monkeypatch):
    from evals.scripts import run_eval

    monkeypatch.setattr(
        "sys.argv",
        ["run_eval", "--suite", "e2e_relevancy"],
    )

    with pytest.raises(SystemExit) as exc_info:
        run_eval.main()

    assert exc_info.value.code == 2


def test_load_golden_dataset_accepts_ragas_generated_rows(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    dataset_path = tmp_path / "generated.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "user_input": "最近有什么情报？",
                    "reference": "参考答案",
                    "reference_tool_calls": [
                        {"name": "search_evidence", "args": {"query": "情报"}}
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    rows = runner._load_golden_dataset(str(dataset_path))

    assert rows[0]["question"] == "最近有什么情报？"
    assert rows[0]["expected_tool_calls"][0]["name"] == "search_evidence"


def test_search_retrieval_applies_eval_reranker(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {
            "default_top_k": 2,
            "eval_timeout_seconds": 300,
            "reranker": {
                "enabled": True,
                "model": "rerank-model",
                "base_url": "https://example.com/v1",
                "api_key": "from-config",
                "top_k_multiplier": 4,
            },
        },
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))

    class FakeRerankClient:
        def rerank(self, query, documents, top_n=None):
            return [
                {"index": 1, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.8},
            ]

    runner._rerank_client = FakeRerankClient()

    results = [
        SimpleNamespace(parent_chunk=SimpleNamespace(content="a")),
        SimpleNamespace(parent_chunk=SimpleNamespace(content="b")),
        SimpleNamespace(parent_chunk=SimpleNamespace(content="c")),
        SimpleNamespace(parent_chunk=SimpleNamespace(content="d")),
    ]

    class FakeHybridSearch:
        def __init__(self):
            self.calls = []

        def search(self, query, top_k):
            self.calls.append((query, top_k))
            return results

    hybrid_search = FakeHybridSearch()
    mgr = SimpleNamespace(
        config=SimpleNamespace(rerank_enabled=True, rerank_top_k_multiplier=4),
        rerank_client=runner._rerank_client,
    )
    ordered = runner._search_retrieval(
        hybrid_search=hybrid_search,
        query="news",
        top_k=2,
        mgr=mgr,
    )

    assert hybrid_search.calls[0][1] == 8
    assert [item.parent_chunk.content for item in ordered] == ["b", "a"]


def test_retrieval_sample_can_carry_eval_ids():
    from evals.adapters import retrieval_to_sample
    from models.document import ParentDocumentChunk
    from models.search import HybridSearchResult

    sample = retrieval_to_sample(
        question="q",
        hybrid_results=[
            HybridSearchResult(
                parent_chunk=ParentDocumentChunk(
                    parent_chunk_id="1244_p0",
                    document_id="1244",
                    content="context body",
                    token_count=10,
                    child_point_ids=["1244_c0"],
                ),
                rrf_score=1.0,
            )
        ],
        agent_answer="",
        reference="标准答案",
        source_article_ids=[1244, 1238],
        include_eval_ids=True,
    )

    assert sample.retrieved_contexts[0].startswith(
        "[parent_chunk_id=1244_p0]\n"
    )
    assert sample.reference.startswith("[source_article_ids=1244, 1238]\n")


def test_run_retrieval_eval_computes_precision_locally(monkeypatch, tmp_path):
    import evals.runner as runner_module
    from evals.runner import LogosEvalRunner

    monkeypatch.setattr(
        runner_module,
        "load_eval_config",
        lambda config_path=None: {"default_top_k": 5, "eval_timeout_seconds": 300},
    )

    runner = LogosEvalRunner(results_dir=str(tmp_path))
    runner._judge_llm = object()
    runner._judge_embeddings = object()

    class LLMContextPrecisionWithoutReference:
        pass

    class LLMContextRecall:
        pass

    captured = {}

    class FakeEvaluateResult:
        def __init__(self):
            self.scores = [{"context_recall": 0.75}]

        def to_pandas(self):
            return _FakeFrame([{"user_input": "q1", "context_recall": 0.75}])

    def fake_get_metrics_by_suite(_suite):
        return [LLMContextPrecisionWithoutReference(), LLMContextRecall()]

    def fake_evaluate(**kwargs):
        captured["metric_names"] = [metric.__class__.__name__ for metric in kwargs["metrics"]]
        return FakeEvaluateResult()

    monkeypatch.setattr(runner_module, "get_metrics_by_suite", fake_get_metrics_by_suite)
    monkeypatch.setattr(runner_module, "evaluate", fake_evaluate)
    monkeypatch.setattr(
        runner,
        "_load_golden_dataset",
        lambda dataset_path=None: [
            {
                "question": "q1",
                "reference": "ref",
                "source_article_ids": [1244, 1238],
            }
        ],
    )

    def fake_collect_retrieval_samples(_golden):
        runner._retrieval_eval_metadata = [
            {
                "question": "q1",
                "source_article_ids": [1244, 1238],
                "retrieved_parent_chunk_ids": ["1244_p0"],
                "retrieved_parent_article_ids": [1244],
                "retrieved_article_ids": [1244],
                "article_id_hit_count": 1,
                "article_id_hit": True,
                "article_id_recall": 0.5,
                "article_id_precision": 1.0,
                "article_id_match_rate": 0.5,
                "top_k": 5,
            }
        ]
        return ([SimpleNamespace(reference="ref")], [])

    monkeypatch.setattr(runner, "_collect_retrieval_samples", fake_collect_retrieval_samples)

    result = runner.run_retrieval_eval()

    assert captured["metric_names"] == ["LLMContextRecall"]
    assert result["metric_names"] == [
        "llm_context_precision_without_reference",
        "context_recall",
    ]
    assert result["scores"]["llm_context_precision_without_reference"] == 1.0
    assert result["per_sample_scores"][0]["llm_context_precision_without_reference"] == 1.0
    assert result["per_sample_results"][0]["retrieved_parent_chunk_ids"] == ["1244_p0"]
