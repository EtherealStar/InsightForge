"""AI 问答 API — ReAct Agent 模式"""
import json
import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/query", tags=["query"])
logger = structlog.get_logger(__name__)


class QueryRequest(BaseModel):
    question: str
    top_k: int = 10


def _get_query_service():
    """从 ConfigManager 获取组件并构建 QueryService"""
    from core.config_manager import get_config_manager
    from services.query_service import QueryService

    mgr = get_config_manager()
    return QueryService(
        mgr.article_store, mgr.vector_store,
        mgr.llm_client, mgr.embedding_client,
    )


@router.post("")
def query(req: QueryRequest):
    """非流式问答（ReAct Agent 模式）"""
    try:
        service = _get_query_service()
        result = service.answer_agent(req.question)
        return {"answer": result.answer, "events": [e.to_dict() for e in result.events]}
    except Exception as e:
        logger.error(f"问答失败: {e}")
        raise HTTPException(status_code=500, detail=f"问答失败: {e}")


@router.post("/stream")
def query_stream(req: QueryRequest):
    """SSE 流式问答 — ReAct Agent 模式

    每个事件以 JSON 格式传输：
        data: {"event_type": "thought", "content": "..."}
        data: {"event_type": "action", "tool_name": "...", "tool_input": {...}}
        data: {"event_type": "observation", "content": "..."}
        data: {"event_type": "answer", "content": "..."}
        data: [DONE]
    """
    try:
        service = _get_query_service()

        def event_generator():
            try:
                for event in service.answer_agent_stream(req.question):
                    event_data = json.dumps(
                        event.to_dict(), ensure_ascii=False
                    )
                    yield f"data: {event_data}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"流式问答失败: {e}")
                error_event = json.dumps(
                    {"event_type": "error", "content": str(e)},
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
        logger.error(f"流式问答初始化失败: {e}")
        raise HTTPException(status_code=500, detail=f"问答失败: {e}")
