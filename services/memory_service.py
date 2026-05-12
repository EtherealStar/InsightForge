"""三层记忆系统服务。"""

from __future__ import annotations

import json
from typing import Any

import structlog

from core.protocols import AgentSessionStoreProtocol, LLMClientProtocol, MemoryStoreProtocol
from models.agent_session import AgentSession
from models.memory import MemoryStatus, MemoryType, PersistentMemory

logger = structlog.get_logger(__name__)

SESSION_COMPACT_INITIAL_TOKENS = 10_000
SESSION_COMPACT_INCREMENT_TOKENS = 5_000
SESSION_COMPACT_BACKOFF_TOKENS = 10_000


class MemoryService:
    """负责记忆上下文构建、会话摘要与持久记忆候选写入。"""

    def __init__(
        self,
        memory_store: MemoryStoreProtocol,
        session_store: AgentSessionStoreProtocol,
        llm_client: LLMClientProtocol | None = None,
    ):
        self.memory_store = memory_store
        self.session_store = session_store
        self.llm_client = llm_client

    def build_memory_context(
        self,
        session_id: str | None = None,
        query: str | None = None,
    ) -> str:
        """构建注入 Agent system prompt 的记忆上下文。"""
        parts: list[str] = []
        core = self.memory_store.get_active_core_memories()
        if core:
            parts.append("## 核心记忆\n" + "\n\n".join(item.content for item in core))

        index_items = self.memory_store.list_memory_index()
        if index_items:
            parts.append("## MEMORY 索引\n" + "\n".join(item.line for item in index_items))

        selected = self.select_persistent_memories(query or "")
        if selected:
            parts.append(
                "## 相关持久记忆\n"
                + "\n\n".join(
                    f"### {item.memory_type.value}-{item.title}\n{item.content}"
                    for item in selected
                )
            )

        if session_id:
            session = self.session_store.get_session(session_id)
            if session and session.summary:
                parts.append("## 会话记忆\n" + session.summary)

        if not parts:
            return ""
        return "\n\n".join(parts)

    def select_persistent_memories(
        self,
        query: str,
        limit: int = 5,
    ) -> list[PersistentMemory]:
        """第一版用轻量关键词匹配选择持久记忆。"""
        memories = self.memory_store.list_persistent_memories(status=MemoryStatus.ACTIVE)
        if not query.strip():
            return memories[:limit]
        lowered = query.lower()
        scored: list[tuple[int, PersistentMemory]] = []
        for memory in memories:
            haystack = f"{memory.title} {memory.summary} {memory.content}".lower()
            score = sum(1 for token in _query_tokens(lowered) if token in haystack)
            if score > 0:
                scored.append((score, memory))
        scored.sort(key=lambda item: item[0], reverse=True)
        if scored:
            return [memory for _, memory in scored[:limit]]
        return memories[: min(limit, 3)]

    def maybe_compact_session(self, session_id: str) -> AgentSession | None:
        """根据 token 阈值尝试更新会话摘要。"""
        session = self.session_store.get_session(session_id)
        if not session:
            return None
        token_count = estimate_tokens(_messages_text(session.messages))
        threshold = _next_compact_threshold(session)
        if token_count < threshold:
            if token_count != session.token_count:
                session = self.session_store.update_summary(
                    session_id=session.id,
                    summary=session.summary or "",
                    token_count=token_count,
                    last_compacted_tokens=session.last_compacted_tokens,
                    compact_failures=session.compact_failures,
                )
            return session
        if not self.llm_client:
            return self.session_store.update_summary(
                session_id=session.id,
                summary=session.summary or "",
                token_count=token_count,
                last_compacted_tokens=session.last_compacted_tokens,
                compact_failures=session.compact_failures + 1,
            )
        try:
            summary = self._summarize_session(session)
            return self.session_store.update_summary(
                session_id=session.id,
                summary=summary,
                token_count=token_count,
                last_compacted_tokens=token_count,
                compact_failures=0,
            )
        except Exception as e:
            logger.warning(
                "memory.session_compact_failed",
                session_id=session.id,
                error=str(e),
            )
            return self.session_store.update_summary(
                session_id=session.id,
                summary=session.summary or "",
                token_count=token_count,
                last_compacted_tokens=session.last_compacted_tokens,
                compact_failures=session.compact_failures + 1,
            )

    def create_memory_candidate(
        self,
        memory_type: MemoryType,
        title: str,
        summary: str,
        content: str,
        source_session_id: str | None = None,
        confidence: float | None = None,
    ) -> PersistentMemory:
        """创建待用户确认的持久记忆候选。"""
        return self.memory_store.create_persistent_memory(
            memory_type=memory_type,
            title=title,
            summary=summary,
            content=content,
            source_session_id=source_session_id,
            confidence=confidence,
            status=MemoryStatus.PENDING,
        )

    def _summarize_session(self, session: AgentSession) -> str:
        template = session.summary_template or DEFAULT_SESSION_MEMORY_PROMPT
        payload = {
            "existing_summary": session.summary or "",
            "messages": session.messages,
            "events": session.events[-50:],
        }
        return self.llm_client.generate(
            template,
            json.dumps(payload, ensure_ascii=False),
        )


DEFAULT_SESSION_MEMORY_PROMPT = """你是会话记忆压缩器。请根据现有摘要、消息和事件，输出结构化会话记忆。保留当前任务、待跟进线索、已检索查询、已访问来源、关键发现、输出成果、错误与修正、会话工作日志。使用中文，简洁但信息完整。"""


def estimate_tokens(text: str) -> int:
    """轻量 token 估算，避免把记忆系统绑定到特定 tokenizer。"""
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    non_ascii_chars = len(text) - ascii_chars
    return max(1, ascii_chars // 4 + non_ascii_chars)


def _messages_text(messages: list[dict[str, Any]]) -> str:
    return "\n".join(str(message.get("content") or "") for message in messages)


def _next_compact_threshold(session: AgentSession) -> int:
    if session.last_compacted_tokens <= 0:
        return SESSION_COMPACT_INITIAL_TOKENS
    increment = (
        SESSION_COMPACT_BACKOFF_TOKENS
        if session.compact_failures >= 3
        else SESSION_COMPACT_INCREMENT_TOKENS
    )
    return session.last_compacted_tokens + increment


def _query_tokens(query: str) -> list[str]:
    return [token for token in query.replace("，", " ").replace("。", " ").split() if token]
