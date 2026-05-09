"""新闻数据 API"""
import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/api/news", tags=["news"])
logger = structlog.get_logger(__name__)


class ArticleResponse(BaseModel):
    id: int | None
    title: str
    url: str
    content: str
    html_content: str
    summary: str
    source: str
    author: str
    language: str
    published_at: str | None
    created_at: str
    status: str
    tags: list[str]


class ArticleListResponse(BaseModel):
    articles: list[ArticleResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

class BatchDeleteRequest(BaseModel):
    article_ids: list[int]


def _article_to_response(article) -> ArticleResponse:
    return ArticleResponse(
        id=article.id,
        title=article.title,
        url=article.url,
        content=article.content,
        html_content=article.html_content or "",
        summary=article.summary,
        source=article.source,
        author=article.author or "",
        language=article.language.value if hasattr(article.language, 'value') else str(article.language),
        published_at=article.published_at.isoformat() if article.published_at else None,
        created_at=article.created_at.isoformat() if article.created_at else "",
        status=article.status.value if hasattr(article.status, 'value') else str(article.status),
        tags=article.tags or [],
    )


def _get_article_store():
    """从 ConfigManager 获取配置与 ArticleStore 单例"""
    from core.config_manager import get_config_manager
    mgr = get_config_manager()
    return mgr.config, mgr.article_store


@router.get("", response_model=ArticleListResponse)
def get_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: str | None = Query(None),
    language: str | None = Query(None),
    keyword: str | None = Query(None),
):
    """分页获取新闻列表"""
    _, store = _get_article_store()
    articles = store.get_articles(
        page=page,
        page_size=page_size,
        source=source,
        language=language,
        keyword=keyword,
    )
    total = store.count_articles(source=source, language=language, keyword=keyword)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return ArticleListResponse(
        articles=[_article_to_response(a) for a in articles],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/stats")
def get_stats():
    """获取数据库统计"""
    _, store = _get_article_store()
    return store.get_stats()


@router.get("/sources")
def get_sources():
    """获取所有新闻来源"""
    _, store = _get_article_store()
    stats = store.get_stats()
    return {"sources": stats.get("sources", [])}



@router.post("/pipeline")
def run_pipeline():
    """手动触发 Pipeline 抓取（异步执行）"""
    try:
        from scheduler.tasks import run_pipeline_task
        task = run_pipeline_task.apply_async(kwargs={"manual": True})
        return {"status": "ok", "task_id": task.id, "message": "Pipeline 已在后台开始运行"}
    except Exception as e:
        logger.error(f"Pipeline 异步触发失败: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline 触发失败: {e}")

@router.post("/batch-delete")
def batch_delete_articles(req: BatchDeleteRequest):
    """批量彻底删除文章及其附属向量记录"""
    if not req.article_ids:
        return {"status": "ok", "deleted": 0}

    from core.config_manager import get_config_manager
    mgr = get_config_manager()
    store = mgr.article_store
    
    deleted_db = store.delete_articles(req.article_ids)
    
    try:
        mgr.vector_store.delete_by_article_ids(req.article_ids)
    except Exception as e:
        logger.error(f"同步删除 Qdrant chunk 向量记录未遂，不阻碍主流程: {e}")

    try:
        store.delete_parent_chunks_by_article_ids(req.article_ids)
    except Exception as e:
        logger.error(f"同步删除 PostgreSQL 父 chunks 未遂，不阻碍主流程: {e}")
        
    return {"status": "ok", "deleted": deleted_db}


class ResummarizeRequest(BaseModel):
    article_ids: list[int]


@router.post("/resummarize")
def resummarize_articles(req: ResummarizeRequest):
    """重新对指定文章执行 AI 摘要 + 打标签"""
    if not req.article_ids:
        return {"status": "ok", "result": {"success": 0, "failed": 0, "total": 0}}

    from core.config_manager import get_config_manager
    from services.summary_service import SummaryService

    mgr = get_config_manager()
    if not mgr.summary_llm_client:
        raise HTTPException(status_code=400, detail="AI 摘要服务未配置 LLM 客户端")

    service = SummaryService(
        llm_client=mgr.summary_llm_client,
        article_store=mgr.article_store,
        batch_size=mgr.config.summary_batch_size,
    )
    try:
        result = service.resummarize_articles(req.article_ids)
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"AI 重新摘要失败: {e}")
        raise HTTPException(status_code=500, detail=f"AI 重新摘要失败: {e}")


@router.get("/{article_id}", response_model=ArticleResponse)
def get_article(article_id: int):
    """获取单篇新闻全文"""
    _, store = _get_article_store()
    article = store.get_article_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="未找到该文章")
    return _article_to_response(article)
