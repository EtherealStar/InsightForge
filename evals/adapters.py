"""Logos 数据结构 → RAGAs 评估数据模型的适配器

将 Logos 的检索结果、Agent 事件流等数据结构转换为
RAGAs 的 SingleTurnSample / MultiTurnSample，
以便传入 ragas.evaluate() 进行评估。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ragas import SingleTurnSample, EvaluationDataset

if TYPE_CHECKING:
    from agent.react.agent import AgentEvent, AgentResult
    from models.search import HybridSearchResult, ChunkSearchResult


def retrieval_to_sample(
    question: str,
    hybrid_results: list[HybridSearchResult],
    agent_answer: str,
    reference: str | None = None,
) -> SingleTurnSample:
    """将一次混合检索 + Agent 问答结果转换为 RAGAs SingleTurnSample。

    用于评估维度 ①（检索质量）和 ②（端到端问答）。

    Args:
        question: 用户原始问题。
        hybrid_results: HybridSearchService.search() 返回的混合检索结果。
        agent_answer: ReActAgent 生成的最终回答。
        reference: 人工标注的参考答案（可选，用于 Context Recall 等指标）。

    Returns:
        SingleTurnSample: RAGAs 评估样本。
    """
    contexts = [r.parent_chunk.content for r in hybrid_results]

    return SingleTurnSample(
        user_input=question,
        retrieved_contexts=contexts,
        response=agent_answer,
        reference=reference,
    )


def semantic_results_to_sample(
    question: str,
    chunk_results: list[ChunkSearchResult],
    agent_answer: str,
    reference: str | None = None,
) -> SingleTurnSample:
    """将纯语义检索结果转换为 RAGAs SingleTurnSample。

    当使用 semantic 模式检索时使用。

    Args:
        question: 用户原始问题。
        chunk_results: PgVectorStore.search_chunks() 返回的子 chunk 结果。
        agent_answer: Agent 最终回答。
        reference: 参考答案（可选）。

    Returns:
        SingleTurnSample: RAGAs 评估样本。
    """
    contexts = []
    for cr in chunk_results:
        if cr.parent_chunk:
            contexts.append(cr.parent_chunk.content)
        else:
            contexts.append(cr.chunk.content)

    return SingleTurnSample(
        user_input=question,
        retrieved_contexts=contexts,
        response=agent_answer,
        reference=reference,
    )


def agent_result_to_sample(
    question: str,
    result: AgentResult,
    retrieved_contexts: list[str] | None = None,
    reference: str | None = None,
) -> SingleTurnSample:
    """将 AgentResult 转换为 SingleTurnSample。

    用于端到端评估：问题 → Agent 完整执行 → 最终回答。
    如果提供 retrieved_contexts，可同时评估检索和生成质量。

    Args:
        question: 用户原始问题。
        result: ReActAgent.run() 返回的完整结果。
        retrieved_contexts: 从 Agent 事件中提取的检索上下文（可选）。
        reference: 参考答案（可选）。

    Returns:
        SingleTurnSample: RAGAs 评估样本。
    """
    # 如果未显式提供上下文，尝试从 Agent 事件中提取工具返回的内容
    if retrieved_contexts is None:
        retrieved_contexts = _extract_contexts_from_events(result.events)

    return SingleTurnSample(
        user_input=question,
        retrieved_contexts=retrieved_contexts,
        response=result.answer,
        reference=reference,
    )


def agent_events_to_multi_turn(
    question: str,
    events: list[AgentEvent],
    reference: str | None = None,
    reference_tool_calls: list[dict] | None = None,
) -> "MultiTurnSample":
    """将 ReActAgent 事件流转换为 RAGAs MultiTurnSample。

    用于评估维度 ③（Agent 工具调用质量）。

    Args:
        question: 用户原始问题。
        events: ReActAgent 执行过程中产生的事件列表。
        reference: 期望的目标达成描述（用于 AgentGoalAccuracy）。
        reference_tool_calls: 期望的工具调用序列（用于 ToolCallAccuracy）。

    Returns:
        MultiTurnSample: RAGAs 多轮评估样本。
    """
    from ragas import MultiTurnSample
    from ragas.messages import HumanMessage, AIMessage, ToolMessage, ToolCall

    messages = [HumanMessage(content=question)]

    for event in events:
        if event.event_type == "thought":
            messages.append(AIMessage(content=f"Thought: {event.content}"))

        elif event.event_type == "action_start":
            tool_calls = []
            if event.tool_name:
                tool_calls.append(ToolCall(
                    name=event.tool_name,
                    args=event.tool_input or {},
                ))
            messages.append(AIMessage(
                content=event.content or "",
                tool_calls=tool_calls,
            ))

        elif event.event_type == "action_result":
            messages.append(ToolMessage(content=event.content or ""))

        elif event.event_type == "answer":
            messages.append(AIMessage(content=event.content))

    return MultiTurnSample(
        user_input=messages,
        reference=reference,
        reference_tool_calls=reference_tool_calls,
    )


def build_evaluation_dataset(
    samples: list[SingleTurnSample],
) -> EvaluationDataset:
    """将多个样本打包为 RAGAs EvaluationDataset。

    Args:
        samples: SingleTurnSample 列表。

    Returns:
        EvaluationDataset: 可传入 ragas.evaluate() 的数据集。
    """
    return EvaluationDataset(samples=samples)


def _extract_contexts_from_events(
    events: list[AgentEvent],
) -> list[str]:
    """从 Agent 事件流中提取工具返回的检索上下文。

    解析 action_result 事件，提取 query_knowledge_base 工具返回的内容
    作为 retrieved_contexts。

    Args:
        events: AgentEvent 列表。

    Returns:
        list[str]: 提取到的上下文文本列表。
    """
    contexts = []
    for event in events:
        if (
            event.event_type == "action_result"
            and event.tool_name == "query_knowledge_base"
            and event.content
        ):
            # 工具返回的完整文本作为一个 context
            contexts.append(event.content)
    return contexts
