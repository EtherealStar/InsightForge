"""Plan Execute 深度研究 Runner。"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Iterator

from agent.react.agent import AgentEvent, ReActAgent
from agent.react.prompts import (
    build_plan_execute_research_prompt,
    build_research_plan_prompt,
    format_tool_descriptions,
)
from agent.tools.registry import ToolRegistry
from core.protocols import AgentSessionStoreProtocol, LLMClientProtocol
from models.agent_session import AgentSession, ResearchTodo, SessionStatus
from services.deep_research_service import DeepResearchService
from services.memory_service import MemoryService


class PlanExecuteRunner:
    """生成可审阅研究计划，并按确认后的 plan/todos 执行。"""

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        tool_registry: ToolRegistry,
        session_store: AgentSessionStoreProtocol,
        report_service: DeepResearchService,
        memory_service: MemoryService | None = None,
        max_steps: int = 15,
    ):
        self._llm_client = llm_client
        self._tool_registry = tool_registry
        self._session_store = session_store
        self._report_service = report_service
        self._memory_service = memory_service
        self._max_steps = max_steps

    def generate_plan(self, topic: str) -> AgentSession:
        """生成计划并创建 planned 会话。"""
        system_prompt = build_research_plan_prompt()
        raw_plan = self._generate_text(system_prompt, topic)
        plan = _parse_plan(raw_plan)
        todos = _extract_todos(plan)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": topic},
            {"role": "assistant", "content": raw_plan},
        ]
        return self._session_store.create_session(
            topic=topic,
            plan=plan,
            todos=todos,
            messages=messages,
        )

    def execute(self, session: AgentSession) -> Iterator[AgentEvent]:
        """按已确认计划执行深度研究。"""
        self._session_store.update_status(session.id, SessionStatus.APPROVED)
        session = self._session_store.update_status(session.id, SessionStatus.RUNNING)
        todos = [ResearchTodo.from_dict(todo.to_dict()) for todo in session.todos]
        current_todo_index = 0

        tools = self._tool_registry.list_tools()
        tool_desc = format_tool_descriptions(tools)
        system_prompt = build_plan_execute_research_prompt(
            tool_descriptions=tool_desc,
            plan=_format_plan(session.plan),
            todos=_format_todos(todos),
            max_steps=self._max_steps,
        )
        if self._memory_service:
            memory_context = self._memory_service.build_memory_context(
                session_id=session.id,
                query=session.topic,
            )
            if memory_context:
                system_prompt = f"{memory_context}\n\n{system_prompt}"
        agent = ReActAgent(
            llm_client=self._llm_client,
            tool_registry=self._tool_registry,
            max_steps=self._max_steps,
            system_prompt_override=system_prompt,
            run_id=session.id,
        )

        answer_content = ""
        try:
            for event in agent.run_stream(
                f"请执行已确认的深度研究计划，研究主题：{session.topic}"
            ):
                if event.event_type == "action_start":
                    todo_event = _advance_todo(
                        session.id,
                        todos,
                        current_todo_index,
                        "in_progress",
                    )
                    if todo_event:
                        self._session_store.update_todos(session.id, todos)
                        self._session_store.append_event(
                            session.id, todo_event.to_dict()
                        )
                        yield todo_event
                yield event
                self._session_store.append_event(session.id, event.to_dict())

                if event.event_type == "action_result":
                    todo_event = _advance_todo(
                        session.id,
                        todos,
                        current_todo_index,
                        "completed",
                    )
                    if todo_event:
                        current_todo_index += 1
                        self._session_store.update_todos(session.id, todos)
                        self._session_store.append_event(
                            session.id, todo_event.to_dict()
                        )
                        yield todo_event
                elif event.event_type == "answer":
                    answer_content = event.content

            if answer_content:
                for idx, todo in enumerate(todos):
                    if todo.status != "completed":
                        todo.status = "completed"
                        todo_event = _todo_event(session.id, todo, todos, idx)
                        self._session_store.update_todos(session.id, todos)
                        self._session_store.append_event(session.id, todo_event.to_dict())
                        yield todo_event
                report_path = self._report_service.save_report(
                    topic=session.topic,
                    content=answer_content,
                )
                self._session_store.complete_session(
                    session_id=session.id,
                    final_answer=answer_content,
                    report_filename=os.path.basename(report_path),
                )
                if self._memory_service:
                    self._memory_service.maybe_compact_session(session.id)
            else:
                self._session_store.fail_session(session.id, "Agent 未生成最终回答")
        except Exception as e:
            self._session_store.fail_session(session.id, str(e))
            yield AgentEvent(
                event_type="error",
                content=str(e),
                run_id=session.id,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _generate_text(self, system_prompt: str, user_message: str) -> str:
        if hasattr(self._llm_client, "generate"):
            return self._llm_client.generate(system_prompt, user_message)
        return self._llm_client.generate_with_history([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ])


def _parse_plan(raw: str) -> dict[str, Any]:
    text = raw.strip()
    json_text = _extract_json_text(text)
    if json_text:
        try:
            parsed = json.loads(json_text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {"raw": raw, "todos": [_fallback_todo_dict(line, i) for i, line in enumerate(_extract_markdown_items(raw), start=1)]}


def _extract_json_text(text: str) -> str | None:
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return None


def _extract_todos(plan: dict[str, Any]) -> list[ResearchTodo]:
    raw_todos = plan.get("todos")
    if isinstance(raw_todos, list) and raw_todos:
        todos = []
        for idx, item in enumerate(raw_todos, start=1):
            if isinstance(item, dict):
                todo = ResearchTodo.from_dict(item)
                if not todo.id:
                    todo.id = f"todo-{idx}"
                if not todo.title:
                    todo.title = f"研究步骤 {idx}"
                todo.status = todo.status or "pending"
                todos.append(todo)
            else:
                todos.append(ResearchTodo(
                    id=f"todo-{idx}",
                    title=str(item),
                    status="pending",
                ))
        return todos

    steps = plan.get("steps")
    if isinstance(steps, list) and steps:
        return [
            ResearchTodo(id=f"todo-{idx}", title=str(step), status="pending")
            for idx, step in enumerate(steps, start=1)
        ]

    return [
        ResearchTodo.from_dict(item)
        for item in plan.get("todos", [])
        if isinstance(item, dict)
    ] or [ResearchTodo(id="todo-1", title="执行深度研究并生成报告", status="pending")]


def _extract_markdown_items(raw: str) -> list[str]:
    items: list[str] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        text = re.sub(r"^#{1,6}\s*", "", text)
        text = re.sub(r"^[-*]\s+", "", text)
        text = re.sub(r"^\d+[.)、]\s*", "", text)
        if len(text) >= 4:
            items.append(text)
        if len(items) >= 6:
            break
    return items or ["分析研究主题", "检索本地知识库", "补充网络资料", "生成研究报告"]


def _fallback_todo_dict(title: str, index: int) -> dict[str, str]:
    return {"id": f"todo-{index}", "title": title, "status": "pending"}


def _format_plan(plan: dict[str, Any] | str | None) -> str:
    if plan is None:
        return "{}"
    if isinstance(plan, str):
        return plan
    return json.dumps(plan, ensure_ascii=False, indent=2)


def _format_todos(todos: list[ResearchTodo]) -> str:
    return json.dumps([todo.to_dict() for todo in todos], ensure_ascii=False, indent=2)


def _advance_todo(
    session_id: str,
    todos: list[ResearchTodo],
    index: int,
    status: str,
) -> AgentEvent | None:
    if index >= len(todos):
        return None
    todo = todos[index]
    if todo.status == status:
        return None
    todo.status = status
    return _todo_event(session_id, todo, todos, index)


def _todo_event(
    session_id: str,
    todo: ResearchTodo,
    todos: list[ResearchTodo],
    index: int,
) -> AgentEvent:
    return AgentEvent(
        event_type="todo_update",
        content=todo.title,
        run_id=session_id,
        step_index=index + 1,
        timestamp=datetime.now(timezone.utc).isoformat(),
        metadata={
            "todo": todo.to_dict(),
            "todos": [item.to_dict() for item in todos],
        },
    )
