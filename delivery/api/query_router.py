"""AI 问答 API — ReAct Agent 模式"""
import json
import uuid
import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/query", tags=["query"])
logger = structlog.get_logger(__name__)


class QueryRequest(BaseModel):
    question: str
    top_k: int = 10
    session_id: str | None = None


def _get_query_service():
    """从 ConfigManager 获取组件并构建 QueryService"""
    from core.config_manager import get_config_manager
    from services.query_service import QueryService
    from services.memory_service import MemoryService

    mgr = get_config_manager()
    return QueryService(
        mgr.article_store, mgr.vector_store,
        mgr.llm_client, mgr.embedding_client,
        session_store=mgr.agent_session_store,
        memory_service=MemoryService(
            mgr.memory_store,
            mgr.agent_session_store,
            mgr.llm_client,
        ),
    )


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
