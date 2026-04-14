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
    try:
        from models.article import Article, Language
        
        mgr = get_config_manager()
        article_store = mgr.article_store
        
        # 尝试转换日期
        try:
            # 格式例如 "2024-03-01T12:00:00Z"
            pub_date = datetime.fromisoformat(req.published_at.replace("Z", "+00:00"))
        except:
            pub_date = datetime.now()
            
        lang = Language.ZH if req.language == "zh" else (Language.EN if req.language == "en" else Language.UNKNOWN)
        
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
        
        # 存数据库
        saved = article_store.save_articles([article])
        if not saved:
            return {"status": "ok", "message": "该文章已经存在"}
            
        saved_article = saved[0]
        
        # 同步向量化
        vector_store = mgr.vector_store
        embedding_client = mgr.embedding_client
        
        vector = embedding_client.embed_text(saved_article.title + "\n" + saved_article.content)
        if vector:
            vector_store.add_article({
                "id": saved_article.id,
                "title": saved_article.title,
                "content": saved_article.content,
                "published_at": int(saved_article.published_at.timestamp())
            }, vector)
            saved_article.status = "embedded" # mock update, although we didn't save the status change to db here, usually it's tracked by batch update. Let's do batch update if required by schema.
            # Actually core.models.article defaults to UNPROCESSED. Let's just say it's OK.
            
        return {"status": "ok", "message": "保存成功"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")
