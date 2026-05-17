"""AI 问答 API — ReAct Agent 模式"""
import json
import uuid
import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/query", tags=["query"])
logger = structlog.get_logger(__name__)


class QueryRequest(BaseModel):
    question: str
    top_k: int = 10
    session_id: str | None = None


def _get_query_service():
    """从 ConfigManager 获取缓存的 QueryService 单例"""
    from core.config_manager import get_config_manager

    return get_config_manager().query_service


def _get_session_store():
    from core.config_manager import get_config_manager

    return get_config_manager().agent_session_store


def _session_preview(session) -> str:
    for message in reversed(session.messages or []):
        content = str(message.get("content") or "").strip()
        if content:
            return content[:160]
    return ""


def _session_summary(session) -> dict:
    return {
        "session_id": session.id,
        "id": session.id,
        "topic": session.topic,
        "status": session.status.value,
        "session_type": session.session_type,
        "message_count": len(session.messages or []),
        "last_message_preview": _session_preview(session),
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


@router.get("/sessions")
def list_query_sessions(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    store = _get_session_store()
    sessions = store.list_sessions(
        session_type="general_query",
        limit=limit,
        offset=offset,
    )
    return {"items": [_session_summary(session) for session in sessions]}


@router.get("/sessions/{session_id}")
def get_query_session(session_id: str):
    session = _get_session_store().get_session(session_id)
    if not session or session.session_type != "general_query":
        raise HTTPException(status_code=404, detail="普通问答会话不存在")
    return session.to_dict()


@router.post("")
def query(req: QueryRequest):
    """非流式问答（ReAct Agent 模式）"""
    run_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(agent_run_id=run_id)
    try:
        service = _get_query_service()
        logger.info(
            "agent.query_start",
            run_id=run_id,
            mode="non_stream",
            question_length=len(req.question),
        )
        try:
            result = service.answer_agent(
                req.question,
                run_id=run_id,
                session_id=req.session_id,
            )
        except TypeError:
            result = service.answer_agent(req.question, run_id=run_id)
        session_id = getattr(result.events[0], "run_id", run_id) if result.events else run_id
        return {
            "answer": result.answer,
            "session_id": session_id,
            "events": [e.to_dict() for e in result.events],
        }
    except Exception as e:
        logger.exception("agent.query_error", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"问答失败: {e}")


@router.post("/stream")
def query_stream(req: QueryRequest):
    """SSE 流式问答 — ReAct Agent 模式

    每个事件以 JSON 格式传输：
        data: {"event_type": "llm_delta", "content": "..."}
        data: {"event_type": "thought", "content": "..."}
        data: {"event_type": "action_start", "tool_name": "...", "tool_input": {...}}
        data: {"event_type": "action_result", "content": "...", "tool_result": {...}}
        data: {"event_type": "answer_delta", "content": "..."}
        data: {"event_type": "answer", "content": "..."}
        data: [DONE]
    """
    run_id = str(uuid.uuid4())
    try:
        service = _get_query_service()

        def event_generator():
            structlog.contextvars.bind_contextvars(agent_run_id=run_id)
            logger.info(
                "agent.stream_start",
                run_id=run_id,
                question_length=len(req.question),
            )
            try:
                try:
                    event_iter = service.answer_agent_stream(
                        req.question,
                        run_id=run_id,
                        session_id=req.session_id,
                    )
                except TypeError:
                    event_iter = service.answer_agent_stream(req.question, run_id=run_id)
                for event in event_iter:
                    event_data = json.dumps(
                        event.to_dict(), ensure_ascii=False
                    )
                    yield f"data: {event_data}\n\n"
                logger.info("agent.stream_complete", run_id=run_id)
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.exception(
                    "agent.stream_error",
                    run_id=run_id,
                    error=str(e),
                )
                error_event = json.dumps(
                    {
                        "event_type": "error",
                        "content": str(e),
                        "run_id": run_id,
                    },
                    ensure_ascii=False,
                )
                yield f"data: {error_event}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logger.exception("agent.stream_init_error", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"问答失败: {e}")
