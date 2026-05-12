"""编排 ReAct Agent 查询流程"""
from typing import Iterator

from core.protocols import (
    ArticleStoreProtocol,
    AgentSessionStoreProtocol,
    VectorStoreProtocol,
    LLMClientProtocol,
    EmbeddingClientProtocol,
)
from services.memory_service import MemoryService


class QueryService:
    """编排 ReAct Agent 问答流程。"""

    def __init__(
        self,
        article_store: ArticleStoreProtocol,
        vector_store: VectorStoreProtocol,
        llm_client: LLMClientProtocol,
        embedding_client: EmbeddingClientProtocol,
        session_store: AgentSessionStoreProtocol | None = None,
        memory_service: MemoryService | None = None,
    ):
        self.article_store = article_store
        self.vector_store = vector_store
        self.llm_client = llm_client
        self.embedding_client = embedding_client
        self.session_store = session_store
        self.memory_service = memory_service

    def _build_agent(
        self,
        run_id: str | None = None,
        system_prompt_override: str | None = None,
    ):
        from agent.react.agent import ReActAgent
        from agent.tools.registry import get_tool_registry

        return ReActAgent(
            llm_client=self.llm_client,
            tool_registry=get_tool_registry(),
            max_steps=5,
            run_id=run_id,
            system_prompt_override=system_prompt_override,
        )

    def answer_agent(
        self,
        question: str,
        run_id: str | None = None,
        session_id: str | None = None,
    ):
        """ReAct Agent 非流式问答。"""
        session = self._ensure_general_session(question, session_id, run_id)
        prompt = self._build_memory_prompt(session.id if session else None, question)
        agent = self._safe_build_agent(
            run_id=session.id if session else run_id,
            system_prompt_override=prompt,
        )
        result = agent.run(question)
        if session:
            self._persist_query_result(session.id, question, result)
        return result

    def answer_agent_stream(
        self,
        question: str,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> Iterator:
        """ReAct Agent 流式问答。

        使用 ReAct 架构让 LLM 自主决策是否调用工具，
        逐步 yield AgentEvent 供 SSE 流式输出。

        Args:
            question: 用户问题。

        Yields:
            AgentEvent: 推理/行动/观察/回答事件。
        """
        session = self._ensure_general_session(question, session_id, run_id)
        prompt = self._build_memory_prompt(session.id if session else None, question)
        agent = self._safe_build_agent(
            run_id=session.id if session else run_id,
            system_prompt_override=prompt,
        )
        answer = ""
        for event in agent.run_stream(question):
            if session:
                self.session_store.append_event(session.id, event.to_dict())
            if event.event_type == "answer":
                answer = event.content
            yield event
        if session:
            self.session_store.append_message(session.id, {"role": "user", "content": question})
            if answer:
                self.session_store.append_message(session.id, {"role": "assistant", "content": answer})
            if self.memory_service:
                self.memory_service.maybe_compact_session(session.id)

    def _ensure_general_session(
        self,
        question: str,
        session_id: str | None,
        run_id: str | None,
    ):
        if not self.session_store:
            return None
        if session_id:
            session = self.session_store.get_session(session_id)
            if session:
                return session
        if run_id:
            existing = self.session_store.get_session(run_id)
            if existing:
                return existing
        return self.session_store.create_general_session(topic=question[:120])

    def _safe_build_agent(
        self,
        run_id: str | None,
        system_prompt_override: str | None,
    ):
        try:
            return self._build_agent(
                run_id=run_id,
                system_prompt_override=system_prompt_override,
            )
        except TypeError:
            return self._build_agent()

    def _build_memory_prompt(self, session_id: str | None, question: str) -> str | None:
        if not self.memory_service:
            return None
        from agent.react.prompts import build_react_system_prompt, format_tool_descriptions
        from agent.tools.registry import get_tool_registry

        tool_desc = format_tool_descriptions(get_tool_registry().list_tools())
        base_prompt = build_react_system_prompt(tool_desc, 5)
        memory_context = self.memory_service.build_memory_context(session_id, question)
        if not memory_context:
            return base_prompt
        return f"{memory_context}\n\n{base_prompt}"

    def _persist_query_result(self, session_id: str, question: str, result) -> None:
        self.session_store.append_message(session_id, {"role": "user", "content": question})
        for event in result.events:
            self.session_store.append_event(session_id, event.to_dict())
        if result.answer:
            self.session_store.append_message(session_id, {"role": "assistant", "content": result.answer})
        if self.memory_service:
            self.memory_service.maybe_compact_session(session_id)
