"""功能设置 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from core.source_config import load_feeds, save_feeds, load_sites, save_sites
from delivery.auth import require_admin, require_viewer

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_viewer)])


class FeedItem(BaseModel):
    name: str
    url: str


class SiteItem(BaseModel):
    name: str
    url: str
    max_pages: int = 20
    link_selector: str = ""
    article_url_patterns: list[str] = Field(default_factory=list)
    exclude_url_patterns: list[str] = Field(default_factory=list)
    content_selector: str = ""
    noise_selectors: list[str] = Field(default_factory=list)


class ScheduleConfig(BaseModel):
    fetch_interval_hours: int = 4
    max_articles_per_fetch: int = 20
    article_retention_days: int = 90


@router.get("/feeds")
def get_feeds():
    """获取 RSS 源列表"""
    feeds = load_feeds()
    return {"feeds": [{"id": i, **feed} for i, feed in enumerate(feeds)]}


@router.post("/feeds", dependencies=[Depends(require_admin)])
def add_feed(feed: FeedItem):
    """添加 RSS 源"""
    feeds = load_feeds()
    # 检查重复
    for existing in feeds:
        if existing["url"] == feed.url:
            raise HTTPException(status_code=400, detail="该 RSS 源已存在")
    feeds.append({"name": feed.name, "url": feed.url})
    save_feeds(feeds)
    return {"status": "ok", "message": f"已添加: {feed.name}"}


@router.delete("/feeds/{feed_id}", dependencies=[Depends(require_admin)])
def delete_feed(feed_id: int):
    """删除 RSS 源"""
    feeds = load_feeds()
    if feed_id < 0 or feed_id >= len(feeds):
        raise HTTPException(status_code=404, detail="未找到该 RSS 源")
    removed = feeds.pop(feed_id)
    save_feeds(feeds)
    return {"status": "ok", "message": f"已删除: {removed['name']}"}


@router.get("/schedule")
def get_schedule():
    """获取调度配置"""
    from delivery.api.config_router import _read_env_file
    env = _read_env_file()
    return ScheduleConfig(
        fetch_interval_hours=int(env.get("FETCH_INTERVAL_HOURS", "4")),
        max_articles_per_fetch=int(env.get("MAX_ARTICLES_PER_FETCH", "20")),
        article_retention_days=int(env.get("ARTICLE_RETENTION_DAYS", "90")),
    )


@router.put("/schedule", dependencies=[Depends(require_admin)])
def update_schedule(schedule: ScheduleConfig):
    """更新调度配置"""
    from delivery.api.config_router import _write_env_file
    updates = {
        "FETCH_INTERVAL_HOURS": str(schedule.fetch_interval_hours),
        "MAX_ARTICLES_PER_FETCH": str(schedule.max_articles_per_fetch),
        "ARTICLE_RETENTION_DAYS": str(schedule.article_retention_days),
    }
    try:
        _write_env_file(updates)
        # 热重载调度配置
        from core.config_manager import get_config_manager
        get_config_manager().reload()
        return {"status": "ok", "message": "调度配置已保存并立即生效"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存调度配置失败: {e}")


# ==================== 网页爬取源管理 ====================

@router.get("/sites")
def get_sites():
    """获取网页爬取源列表"""
    sites = load_sites()
    return {"sites": [{"id": i, **site} for i, site in enumerate(sites)]}


@router.post("/sites", dependencies=[Depends(require_admin)])
def add_site(site: SiteItem):
    """添加网页爬取源"""
    sites = load_sites()
    for existing in sites:
        if existing["url"] == site.url:
            raise HTTPException(status_code=400, detail="该爬取源已存在")
    sites.append({
        "name": site.name,
        "url": site.url,
        "max_pages": site.max_pages,
        "link_selector": site.link_selector or "",
        "article_url_patterns": site.article_url_patterns,
        "exclude_url_patterns": site.exclude_url_patterns,
        "content_selector": site.content_selector or "",
        "noise_selectors": site.noise_selectors,
    })
    save_sites(sites)
    return {"status": "ok", "message": f"已添加: {site.name}"}


@router.put("/sites/{site_id}", dependencies=[Depends(require_admin)])
def update_site(site_id: int, site: SiteItem):
    """更新网页爬取源"""
    sites = load_sites()
    if site_id < 0 or site_id >= len(sites):
        raise HTTPException(status_code=404, detail="未找到该爬取源")
    sites[site_id] = {
        "name": site.name,
        "url": site.url,
        "max_pages": site.max_pages,
        "link_selector": site.link_selector or "",
        "article_url_patterns": site.article_url_patterns,
        "exclude_url_patterns": site.exclude_url_patterns,
        "content_selector": site.content_selector or "",
        "noise_selectors": site.noise_selectors,
    }
    save_sites(sites)
    return {"status": "ok", "message": f"已更新: {site.name}"}


@router.delete("/sites/{site_id}", dependencies=[Depends(require_admin)])
def delete_site(site_id: int):
    """删除网页爬取源"""
    sites = load_sites()
    if site_id < 0 or site_id >= len(sites):
        raise HTTPException(status_code=404, detail="未找到该爬取源")
    removed = sites.pop(site_id)
    save_sites(sites)
    return {"status": "ok", "message": f"已删除: {removed['name']}"}
