"""NewsAPI 代理及操作 API"""
import os
import requests
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from delivery.api.config_router import _read_env_file

router = APIRouter(prefix="/api/newsapi", tags=["newsapi"])

class SaveArticleRequest(BaseModel):
    title: str
    url: str
    content: str
    source_name: str
    language: str
    published_at: str

def get_newsapi_key():
    env = _read_env_file()
    key = env.get("NEWSAPI_KEY", "")
    if not key:
        raise HTTPException(status_code=400, detail="未配置 NewsAPI Key，请前往配置页面设置。")
    return key

@router.get("/everything")
def search_everything(
    q: str = Query(..., min_length=1),
    language: str | None = Query(None),
    sort_by: str | None = Query("publishedAt"),
    page: int = Query(1),
    page_size: int = Query(20)
):
    """代理完整的 newsapi everything 搜索请求"""
    api_key = get_newsapi_key()
    url = "https://newsapi.org/v2/everything"
    
    params = {
        "q": q,
        "page": page,
        "pageSize": page_size,
    }
    if language:
        params["language"] = language
    if sort_by:
        params["sortBy"] = sort_by
        
    headers = {"X-Api-Key": api_key, "User-Agent": "Logos/1.0"}
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=data.get("message", "NewsAPI 请求失败"))
        return data
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/top-headlines")
def search_top_headlines(
    q: str | None = Query(None),
    country: str | None = Query(None),
    category: str | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(20)
):
    """代理 newsapi top-headlines 搜索请求"""
    api_key = get_newsapi_key()
    url = "https://newsapi.org/v2/top-headlines"
    
    params = {
        "page": page,
        "pageSize": page_size,
    }
    # NewsAPI 规定不能混用 source 和 country/category。这里按照 country+category 或者 q 来。
    # 至少需要一个参数（q, category, country等之一），如果没有就默认用 country=us。
    if not q and not country and not category:
        country = "us"
        
    if q: params["q"] = q
    if country: params["country"] = country
    if category: params["category"] = category
        
    headers = {"X-Api-Key": api_key, "User-Agent": "Logos/1.0"}
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=data.get("message", "NewsAPI 请求失败"))
        return data
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/save")
def save_article(req: SaveArticleRequest):
    """保存单篇 NewsAPI 的文章到本地数据库及向量库"""
    from core.config_manager import get_config_manager
    from models.article import Article, Language

    def _parse_published_at(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now()

    def _parse_language(value: str) -> Language:
        normalized = (value or "").lower()
        if normalized == "zh":
            return Language.ZH
        if normalized == "en":
            return Language.EN
        return Language.UNKNOWN

    try:
        mgr = get_config_manager()
        article_store = mgr.article_store

        pub_date = _parse_published_at(req.published_at)
        lang = _parse_language(req.language)

        article = Article(
            title=req.title,
            url=req.url,
            content=req.content,
            html_content="",
            summary=req.content[:500] if req.content else "",
            source=req.source_name,
            language=lang,
            published_at=pub_date
        )
        
        # save_articles 返回的是新增数量，不是文章列表
        saved_count = article_store.save_articles([article])
        if saved_count == 0:
            return {"status": "ok", "message": "该文章已经存在"}

        # 尝试拿到刚保存文章的 id，用于向量化
        saved_article = None
        if hasattr(article_store, "get_articles"):
            candidates = article_store.get_articles(
                page=1,
                page_size=10,
                keyword=req.title,
            )
            for candidate in candidates:
                if candidate.url == req.url:
                    saved_article = candidate
                    break

        vectorized = False
        if saved_article and saved_article.id is not None:
            try:
                embedding_client = mgr.embedding_client
                vector_store = mgr.vector_store
                chunking_service = mgr.chunking_service

                if chunking_service and embedding_client and vector_store:
                    # 分块 → 向量化
                    children, parents = chunking_service.chunk_article(saved_article)
                    if children:
                        child_texts = [c.content for c in children]
                        embeddings = embedding_client.embed(child_texts)
                        if embeddings:
                            vector_store.add_chunks(children, embeddings)
                            if parents:
                                article_store.save_parent_chunks(parents)
                            article_store.mark_embedded([saved_article.id])
                            vectorized = True
            except Exception:
                # 向量化失败不影响文章主流程保存
                vectorized = False

        return {
            "status": "ok",
            "message": "保存成功",
            "saved_count": saved_count,
            "vectorized": vectorized,
            "article": {
                "title": article.title,
                "url": article.url,
                "source": article.source,
                "language": article.language.value,
                "published_at": (
                    article.published_at.isoformat() if article.published_at else None
                ),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")
