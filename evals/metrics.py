"""针对 Logos 三个评估维度的指标预设组合

维度 ①：RAG 检索质量 — 检索到的上下文是否精准且完整
维度 ②：端到端问答质量 — 最终回答是否忠实于上下文且切题
维度 ③：Agent 工具调用 — 工具选择/参数是否正确、是否达成目标
"""

from ragas.metrics import (
    # --- 维度 ①: 检索质量指标 ---
    LLMContextPrecisionWithoutReference,
    LLMContextRecall,
    NoiseSensitivity,
    # --- 维度 ②: 生成质量指标 ---
    Faithfulness,
    ResponseRelevancy,
    # --- 维度 ③: Agent 指标 ---
    ToolCallAccuracy,
    AgentGoalAccuracyWithoutReference,
)


# ======================================================================
# 维度 ①：RAG 检索质量
# ======================================================================

# 无需 ground truth（日常快速评估）
RETRIEVAL_METRICS_NO_REF = [
    LLMContextPrecisionWithoutReference(),  # 检索结果中有多少是相关的
    NoiseSensitivity(),                      # 对噪声上下文的敏感度
]

# 有 ground truth（精确评估）
RETRIEVAL_METRICS_WITH_REF = [
    LLMContextPrecisionWithoutReference(),
    LLMContextRecall(),                      # 是否召回了所有必要信息
]


# ======================================================================
# 维度 ②：端到端问答质量
# ======================================================================

E2E_METRICS = [
    Faithfulness(),       # 回答是否基于上下文（幻觉检测）
    ResponseRelevancy(),  # 回答是否切题
]


# ======================================================================
# 维度 ③：Agent 工具调用质量
# ======================================================================

AGENT_METRICS = [
    ToolCallAccuracy(),                  # 工具选择和参数是否正确
    AgentGoalAccuracyWithoutReference(),  # 是否达成用户目标（无需参考答案）
]


# ======================================================================
# 组合预设
# ======================================================================

# 全量评估（检索 + 端到端 + Agent）
ALL_METRICS = RETRIEVAL_METRICS_NO_REF + E2E_METRICS + AGENT_METRICS

# 快速评估（仅核心指标）
QUICK_METRICS = [
    Faithfulness(),
    ResponseRelevancy(),
    LLMContextPrecisionWithoutReference(),
]


def get_metrics_by_suite(suite: str) -> list:
    """根据评估套件名称获取指标列表。

    Args:
        suite: 套件名称，支持：
            - "retrieval": 检索质量
            - "retrieval_ref": 检索质量（有参考答案）
            - "e2e": 端到端问答
            - "agent": Agent 工具调用
            - "all": 全量
            - "quick": 快速核心指标

    Returns:
        list: RAGAs 指标实例列表。

    Raises:
        ValueError: 未知的套件名称。
    """
    suites = {
        "retrieval": RETRIEVAL_METRICS_NO_REF,
        "retrieval_ref": RETRIEVAL_METRICS_WITH_REF,
        "e2e": E2E_METRICS,
        "agent": AGENT_METRICS,
        "all": ALL_METRICS,
        "quick": QUICK_METRICS,
    }

    if suite not in suites:
        available = ", ".join(suites.keys())
        raise ValueError(
            f"未知评估套件: '{suite}'。可选: {available}"
        )

    return suites[suite]
