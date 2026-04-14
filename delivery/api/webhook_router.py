"""推送渠道管理 API"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.webhook_service import WebhookService, SUPPORTED_PLATFORMS

router = APIRouter(prefix="/api/webhook", tags=["webhook"])
logger = logging.getLogger(__name__)


def _get_service() -> WebhookService:
    return WebhookService()


def _mask_url(url: str) -> str:
    """脱敏 Webhook URL"""
    if not url or len(url) <= 20:
        return "*" * len(url) if url else ""
    return url[:15] + "*" * 8 + url[-6:]


def _mask_token(token: str) -> str:
    """脱敏 Token"""
    if not token or len(token) <= 10:
        return "*" * len(token) if token else ""
    return token[:5] + "*" * (len(token) - 9) + token[-4:]


# ==================== Request / Response Models ====================

class ChannelCreate(BaseModel):
    name: str
    platform: str
    enabled: bool = True
    webhook_url: str = ""
    bot_token: str = ""
    chat_id: str = ""
    server_url: str = "https://ntfy.sh"
    topic: str = ""


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    server_url: Optional[str] = None
    topic: Optional[str] = None


class AutoPushUpdate(BaseModel):
    auto_push: bool


# ==================== 路由 ====================

@router.get("/platforms")
def get_platforms():
    """获取支持的推送平台列表"""
    return {"platforms": SUPPORTED_PLATFORMS}


@router.get("/channels")
def get_channels():
    """获取所有推送渠道（敏感信息脱敏）"""
    service = _get_service()
    channels = service.load_channels()
    result = []
    for ch in channels:
        data = ch.to_dict()
        # 脱敏
        if data.get("webhook_url"):
            data["webhook_url"] = _mask_url(data["webhook_url"])
        if data.get("bot_token"):
            data["bot_token"] = _mask_token(data["bot_token"])
        result.append(data)
    return {"channels": result, "auto_push": service.get_auto_push()}


@router.post("/channels")
def add_channel(channel: ChannelCreate):
    """添加推送渠道"""
    # 验证平台
    valid_platforms = {p["id"] for p in SUPPORTED_PLATFORMS}
    if channel.platform not in valid_platforms:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {channel.platform}")

    # 验证必要字段
    if channel.platform in ("feishu", "dingtalk", "wecom") and not channel.webhook_url:
        raise HTTPException(status_code=400, detail="请填写 Webhook URL")
    if channel.platform == "telegram" and (not channel.bot_token or not channel.chat_id):
        raise HTTPException(status_code=400, detail="请填写 Bot Token 和 Chat ID")
    if channel.platform == "ntfy" and not channel.topic:
        raise HTTPException(status_code=400, detail="请填写 ntfy Topic")

    service = _get_service()
    new_ch = service.add_channel(channel.model_dump())
    return {"status": "ok", "message": f"已添加: {new_ch.name}", "channel": new_ch.to_dict()}


@router.put("/channels/{channel_id}")
def update_channel(channel_id: str, update: ChannelUpdate):
    """更新推送渠道"""
    service = _get_service()
    # 过滤掉脱敏值和 None 值
    updates = {}
    for k, v in update.model_dump().items():
        if v is None:
            continue
        if isinstance(v, str) and "*" in v:
            continue
        updates[k] = v

    result = service.update_channel(channel_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="渠道不存在")
    return {"status": "ok", "message": f"已更新: {result.name}"}


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: str):
    """删除推送渠道"""
    service = _get_service()
    if not service.delete_channel(channel_id):
        raise HTTPException(status_code=404, detail="渠道不存在")
    return {"status": "ok", "message": "渠道已删除"}


@router.post("/channels/{channel_id}/test")
def test_channel(channel_id: str):
    """发送测试消息"""
    service = _get_service()
    result = service.test_channel(channel_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error", "发送失败"))
    return result


@router.post("/push")
def push_latest_brief():
    """推送最新简报到所有已启用渠道"""
    import os
    import glob
    from core.config_manager import get_config_manager

    config = get_config_manager().config
    brief_files = sorted(
        glob.glob(os.path.join(config.output_path, "daily_brief_*.md")),
        reverse=True,
    )
    if not brief_files:
        raise HTTPException(status_code=404, detail="暂无简报可以推送")

    with open(brief_files[0], "r", encoding="utf-8") as f:
        content = f.read()

    service = _get_service()
    results = service.broadcast(content)
    if not results:
        return {"status": "ok", "message": "无已启用的推送渠道", "results": []}

    success = sum(1 for r in results if r["status"] == "ok")
    return {
        "status": "ok",
        "message": f"推送完成: {success}/{len(results)} 个渠道成功",
        "results": results,
    }


@router.post("/push/{channel_id}")
def push_to_channel(channel_id: str):
    """推送最新简报到指定渠道"""
    import os
    import glob
    from core.config_manager import get_config_manager

    config = get_config_manager().config
    brief_files = sorted(
        glob.glob(os.path.join(config.output_path, "daily_brief_*.md")),
        reverse=True,
    )
    if not brief_files:
        raise HTTPException(status_code=404, detail="暂无简报可以推送")

    with open(brief_files[0], "r", encoding="utf-8") as f:
        content = f.read()

    service = _get_service()
    channel = service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="渠道不存在")

    result = service.send_to_channel(channel, content)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error", "推送失败"))
    return result


@router.get("/auto-push")
def get_auto_push():
    """获取自动推送设置"""
    service = _get_service()
    return {"auto_push": service.get_auto_push()}


@router.put("/auto-push")
def update_auto_push(update: AutoPushUpdate):
    """更新自动推送设置"""
    service = _get_service()
    service.set_auto_push(update.auto_push)
    state = "开启" if update.auto_push else "关闭"
    return {"status": "ok", "message": f"自动推送已{state}"}
