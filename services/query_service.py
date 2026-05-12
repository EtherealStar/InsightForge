"""编排 ReAct Agent 查询流程"""
from typing import Iterator

from core.protocols import (
    ArticleStoreProtocol,
    VectorStoreProtocol,
    LLMClientProtocol,
    EmbeddingClientProtocol,
)


class QueryService:
    """编排 ReAct Agent 问答流程。"""

    def __init__(
        self,
        article_store: ArticleStoreProtocol,
        vector_store: VectorStoreProtocol,
        llm_client: LLMClientProtocol,
        embedding_client: EmbeddingClientProtocol,
    ):
        self.article_store = article_store
        self.vector_store = vector_store
        self.llm_client = llm_client
        self.embedding_client = embedding_client

    def _build_agent(self, run_id: str | None = None):
        from agent.react.agent import ReActAgent
        from agent.tools.registry import get_tool_registry

        return ReActAgent(
            llm_client=self.llm_client,
            tool_registry=get_tool_registry(),
            max_steps=5,
            run_id=run_id,
        )

    def answer_agent(self, question: str, run_id: str | None = None):
        """ReAct Agent 非流式问答。"""
        agent = self._build_agent(run_id=run_id)
        return agent.run(question)

    def answer_agent_stream(
        self, question: str, run_id: str | None = None
    ) -> Iterator:
        """ReAct Agent 流式问答。

        使用 ReAct 架构让 LLM 自主决策是否调用工具，
        逐步 yield AgentEvent 供 SSE 流式输出。

        Args:
            question: 用户问题。

        Yields:
            AgentEvent: 推理/行动/观察/回答事件。
        """
        agent = self._build_agent(run_id=run_id)
        yield from agent.run_stream(question)
