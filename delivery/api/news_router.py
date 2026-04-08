"""新闻数据 API"""
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/api/news", tags=["news"])
logger = logging.getLogger(__name__)


class ArticleResponse(BaseModel):
    id: int | None
    title: str
    url: str
    content: str
    html_content: str
    summary: str
    source: str
    language: str
    published_at: str | None
    created_at: str
    status: str


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
        language=article.language.value if hasattr(article.language, 'value') else str(article.language),
        published_at=article.published_at.isoformat() if article.published_at else None,
        created_at=article.created_at.isoformat() if article.created_at else "",
        status=article.status.value if hasattr(article.status, 'value') else str(article.status),
    )


def _get_article_store():
    """延迟导入以避免循环依赖"""
    from core.config import AppConfig
    from core.factory import create_article_store
    config = AppConfig()
    return config, create_article_store(config)


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
    """手动触发 Pipeline 抓取（RSS + 网页爬取）"""
    try:
        from core.config import AppConfig
        from core.factory import (
            create_article_store,
            create_vector_store,
            create_embedding_client,
        )
        from infrastructure.collector import NewsCollector
        from infrastructure.web_crawler import WebCrawler
        from services.pipeline_service import PipelineService
        from delivery.api.settings_router import _load_feeds, _load_sites

        config = AppConfig()
        config.rss_feeds = _load_feeds()
        article_store = create_article_store(config)
        vector_store = create_vector_store(config)
        embedding_client = create_embedding_client(config)
        collector = NewsCollector(config)

        crawl_sites = _load_sites()
        web_crawler = WebCrawler() if crawl_sites else None

        service = PipelineService(
            collector, article_store, vector_store, embedding_client,
            web_crawler=web_crawler,
            crawl_sites=crawl_sites,
        )
        result = service.run()
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"Pipeline 执行失败: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline 执行失败: {e}")

@router.post("/batch-delete")
def batch_delete_articles(req: BatchDeleteRequest):
    """批量彻底删除文章及其附属向量记录"""
    if not req.article_ids:
        return {"status": "ok", "deleted": 0}

    config, store = _get_article_store()
    from core.factory import create_vector_store
    
    deleted_db = store.delete_articles(req.article_ids)
    
    try:
        vector_store = create_vector_store(config)
        vector_store.delete_articles(req.article_ids)
    except Exception as e:
        logger.error(f"同步删除 ChromaDB 记录未遂，不阻碍主流程: {e}")
        
    return {"status": "ok", "deleted": deleted_db}


@router.get("/{article_id}", response_model=ArticleResponse)
def get_article(article_id: int):
    """获取单篇新闻全文"""
    _, store = _get_article_store()
    article = store.get_article_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="未找到该文章")
    return _article_to_response(article)
