"""AI 问答 API"""
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/query", tags=["query"])
logger = logging.getLogger(__name__)


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
    """非流式问答"""
    try:
        service = _get_query_service()
        answer = service.answer(req.question, top_k=req.top_k)
        return {"answer": answer}
    except Exception as e:
        logger.error(f"问答失败: {e}")
        raise HTTPException(status_code=500, detail=f"问答失败: {e}")


@router.post("/stream")
def query_stream(req: QueryRequest):
    """SSE 流式问答"""
    try:
        service = _get_query_service()

        def event_generator():
            try:
                for chunk in service.answer_stream(req.question, top_k=req.top_k):
                    # SSE 格式
                    yield f"data: {chunk}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"流式问答失败: {e}")
                yield f"data: [ERROR] {e}\n\n"

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
