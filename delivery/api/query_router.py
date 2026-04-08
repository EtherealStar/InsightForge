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
    """延迟导入以避免循环依赖"""
    from core.config import AppConfig
    from core.factory import (
        create_article_store,
        create_vector_store,
        create_llm_client,
        create_embedding_client,
    )
    from services.query_service import QueryService

    config = AppConfig()
    article_store = create_article_store(config)
    vector_store = create_vector_store(config)
    llm_client = create_llm_client(config)
    embedding_client = create_embedding_client(config)

    return QueryService(article_store, vector_store, llm_client, embedding_client)


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
