"""功能设置 API"""
import json
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/settings", tags=["settings"])

_DATA_DIR = os.path.join(os.getcwd(), "data")
_FEEDS_CONFIG_PATH = os.path.join(_DATA_DIR, "feeds_config.json")
_SITES_CONFIG_PATH = os.path.join(_DATA_DIR, "sites_config.json")


class FeedItem(BaseModel):
    name: str
    url: str


class SiteItem(BaseModel):
    name: str
    url: str
    max_pages: int = 20
    link_selector: str = ""


class ScheduleConfig(BaseModel):
    fetch_interval_hours: int = 4
    daily_brief_hour: int = 8
    brief_fetch_hours: int = 24
    brief_mode: str = "daily"  # "daily" or "interval"
    brief_interval_hours: int = 8
    max_articles_per_fetch: int = 20
    article_retention_days: int = 90


def _load_feeds() -> list[dict]:
    """加载 RSS 源列表"""
    if os.path.exists(_FEEDS_CONFIG_PATH):
        with open(_FEEDS_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    from core.config_manager import get_config_manager
    config = get_config_manager().config
    return list(config.rss_feeds)


def _save_feeds(feeds: list[dict]):
    """保存 RSS 源列表"""
    os.makedirs(os.path.dirname(_FEEDS_CONFIG_PATH), exist_ok=True)
    with open(_FEEDS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(feeds, f, ensure_ascii=False, indent=2)


def _load_sites() -> list[dict]:
    """加载网页爬取源列表"""
    if os.path.exists(_SITES_CONFIG_PATH):
        with open(_SITES_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_sites(sites: list[dict]):
    """保存网页爬取源列表"""
    os.makedirs(os.path.dirname(_SITES_CONFIG_PATH), exist_ok=True)
    with open(_SITES_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)


@router.get("/feeds")
def get_feeds():
    """获取 RSS 源列表"""
    feeds = _load_feeds()
    return {"feeds": [{"id": i, **feed} for i, feed in enumerate(feeds)]}


@router.post("/feeds")
def add_feed(feed: FeedItem):
    """添加 RSS 源"""
    feeds = _load_feeds()
    # 检查重复
    for existing in feeds:
        if existing["url"] == feed.url:
            raise HTTPException(status_code=400, detail="该 RSS 源已存在")
    feeds.append({"name": feed.name, "url": feed.url})
    _save_feeds(feeds)
    return {"status": "ok", "message": f"已添加: {feed.name}"}


@router.delete("/feeds/{feed_id}")
def delete_feed(feed_id: int):
    """删除 RSS 源"""
    feeds = _load_feeds()
    if feed_id < 0 or feed_id >= len(feeds):
        raise HTTPException(status_code=404, detail="未找到该 RSS 源")
    removed = feeds.pop(feed_id)
    _save_feeds(feeds)
    return {"status": "ok", "message": f"已删除: {removed['name']}"}


@router.get("/schedule")
def get_schedule():
    """获取调度配置"""
    from delivery.api.config_router import _read_env_file
    env = _read_env_file()
    return ScheduleConfig(
        fetch_interval_hours=int(env.get("FETCH_INTERVAL_HOURS", "4")),
        daily_brief_hour=int(env.get("DAILY_BRIEF_HOUR", "8")),
        brief_fetch_hours=int(env.get("BRIEF_FETCH_HOURS", "24")),
        brief_mode=env.get("BRIEF_MODE", "daily"),
        brief_interval_hours=int(env.get("BRIEF_INTERVAL_HOURS", "8")),
        max_articles_per_fetch=int(env.get("MAX_ARTICLES_PER_FETCH", "20")),
        article_retention_days=int(env.get("ARTICLE_RETENTION_DAYS", "90")),
    )


@router.put("/schedule")
def update_schedule(schedule: ScheduleConfig):
    """更新调度配置"""
    from delivery.api.config_router import _write_env_file
    updates = {
        "FETCH_INTERVAL_HOURS": str(schedule.fetch_interval_hours),
        "DAILY_BRIEF_HOUR": str(schedule.daily_brief_hour),
        "BRIEF_FETCH_HOURS": str(schedule.brief_fetch_hours),
        "BRIEF_MODE": schedule.brief_mode,
        "BRIEF_INTERVAL_HOURS": str(schedule.brief_interval_hours),
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
    sites = _load_sites()
    return {"sites": [{"id": i, **site} for i, site in enumerate(sites)]}


@router.post("/sites")
def add_site(site: SiteItem):
    """添加网页爬取源"""
    sites = _load_sites()
    for existing in sites:
        if existing["url"] == site.url:
            raise HTTPException(status_code=400, detail="该爬取源已存在")
    sites.append({
        "name": site.name,
        "url": site.url,
        "max_pages": site.max_pages,
        "link_selector": site.link_selector or "",
    })
    _save_sites(sites)
    return {"status": "ok", "message": f"已添加: {site.name}"}


@router.put("/sites/{site_id}")
def update_site(site_id: int, site: SiteItem):
    """更新网页爬取源"""
    sites = _load_sites()
    if site_id < 0 or site_id >= len(sites):
        raise HTTPException(status_code=404, detail="未找到该爬取源")
    sites[site_id] = {
        "name": site.name,
        "url": site.url,
        "max_pages": site.max_pages,
        "link_selector": site.link_selector or "",
    }
    _save_sites(sites)
    return {"status": "ok", "message": f"已更新: {site.name}"}


@router.delete("/sites/{site_id}")
def delete_site(site_id: int):
    """删除网页爬取源"""
    sites = _load_sites()
    if site_id < 0 or site_id >= len(sites):
        raise HTTPException(status_code=404, detail="未找到该爬取源")
    removed = sites.pop(site_id)
    _save_sites(sites)
    return {"status": "ok", "message": f"已删除: {removed['name']}"}
