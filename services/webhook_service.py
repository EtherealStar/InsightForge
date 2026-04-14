"""Webhook 推送服务 — 支持飞书/钉钉/企业微信/Telegram/ntfy"""
import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.getcwd(), "data")
_WEBHOOK_CONFIG_PATH = os.path.join(_DATA_DIR, "webhook_config.json")

# 各平台 Markdown 消息体最大字符数（保守估计）
_PLATFORM_MAX_LEN = {
    "feishu": 30000,
    "dingtalk": 20000,
    "wecom": 4096,
    "telegram": 4096,
    "ntfy": 4096,
}

SUPPORTED_PLATFORMS = [
    {
        "id": "feishu",
        "name": "飞书",
        "icon": "🪶",
        "fields": ["webhook_url"],
        "help": "群设置 → 群机器人 → 添加自定义机器人 → 复制 Webhook 地址",
    },
    {
        "id": "dingtalk",
        "name": "钉钉",
        "icon": "💬",
        "fields": ["webhook_url"],
        "help": "群设置 → 智能群助手 → 添加机器人 → 自定义(Webhook) → 复制 Webhook 地址",
    },
    {
        "id": "wecom",
        "name": "企业微信",
        "icon": "💼",
        "fields": ["webhook_url"],
        "help": "群聊 → 添加群机器人 → 复制 Webhook 地址",
    },
    {
        "id": "telegram",
        "name": "Telegram",
        "icon": "✈️",
        "fields": ["bot_token", "chat_id"],
        "help": "通过 @BotFather 创建 Bot 获取 Token；向 Bot 发消息后通过 getUpdates 获取 Chat ID",
    },
    {
        "id": "ntfy",
        "name": "ntfy",
        "icon": "🔔",
        "fields": ["server_url", "topic"],
        "help": "无需注册，填写 ntfy 服务器地址和 topic 名称即可。默认服务器: https://ntfy.sh",
    },
]


@dataclass
class WebhookChannel:
    """单个推送渠道"""
    id: str
    name: str
    platform: str
    enabled: bool = True
    webhook_url: str = ""
    bot_token: str = ""
    chat_id: str = ""
    server_url: str = "https://ntfy.sh"
    topic: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "WebhookChannel":
        # 只保留有效字段，忽略多余键
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


class WebhookService:
    """Webhook 推送服务"""

    def __init__(self):
        self._config_path = _WEBHOOK_CONFIG_PATH

    # ==================== 配置读写 ====================

    def _load_config(self) -> dict:
        if os.path.exists(self._config_path):
            with open(self._config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"channels": [], "auto_push": False}

    def _save_config(self, config: dict):
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def load_channels(self) -> list[WebhookChannel]:
        config = self._load_config()
        return [WebhookChannel.from_dict(ch) for ch in config.get("channels", [])]

    def save_channels(self, channels: list[WebhookChannel]):
        config = self._load_config()
        config["channels"] = [ch.to_dict() for ch in channels]
        self._save_config(config)

    def get_auto_push(self) -> bool:
        return self._load_config().get("auto_push", False)

    def set_auto_push(self, enabled: bool):
        config = self._load_config()
        config["auto_push"] = enabled
        self._save_config(config)

    # ==================== CRUD ====================

    def add_channel(self, channel_data: dict) -> WebhookChannel:
        channels = self.load_channels()
        channel_data["id"] = str(uuid.uuid4())[:8]
        channel = WebhookChannel.from_dict(channel_data)
        channels.append(channel)
        self.save_channels(channels)
        logger.info(f"添加推送渠道: {channel.name} ({channel.platform})")
        return channel

    def update_channel(self, channel_id: str, updates: dict) -> Optional[WebhookChannel]:
        channels = self.load_channels()
        for i, ch in enumerate(channels):
            if ch.id == channel_id:
                # 合并更新
                data = ch.to_dict()
                data.update(updates)
                data["id"] = channel_id  # 确保 ID 不变
                channels[i] = WebhookChannel.from_dict(data)
                self.save_channels(channels)
                logger.info(f"更新推送渠道: {channels[i].name}")
                return channels[i]
        return None

    def delete_channel(self, channel_id: str) -> bool:
        channels = self.load_channels()
        original_len = len(channels)
        channels = [ch for ch in channels if ch.id != channel_id]
        if len(channels) < original_len:
            self.save_channels(channels)
            logger.info(f"删除推送渠道: {channel_id}")
            return True
        return False

    def get_channel(self, channel_id: str) -> Optional[WebhookChannel]:
        for ch in self.load_channels():
            if ch.id == channel_id:
                return ch
        return None

    # ==================== 消息发送 ====================

    def _truncate(self, text: str, max_len: int) -> str:
        """截断过长的消息"""
        if len(text) <= max_len:
            return text
        return text[: max_len - 50] + "\n\n--- ✂️ 内容过长，已截断 ---"

    def _send_feishu(self, channel: WebhookChannel, content: str) -> dict:
        """飞书群机器人"""
        content = self._truncate(content, _PLATFORM_MAX_LEN["feishu"])
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "📰 Logos 新闻简报"},
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content,
                    }
                ],
            },
        }
        resp = requests.post(channel.webhook_url, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _send_dingtalk(self, channel: WebhookChannel, content: str) -> dict:
        """钉钉群机器人"""
        content = self._truncate(content, _PLATFORM_MAX_LEN["dingtalk"])
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "📰 Logos 新闻简报",
                "text": content,
            },
        }
        resp = requests.post(channel.webhook_url, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _send_wecom(self, channel: WebhookChannel, content: str) -> dict:
        """企业微信群机器人"""
        content = self._truncate(content, _PLATFORM_MAX_LEN["wecom"])
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": content,
            },
        }
        resp = requests.post(channel.webhook_url, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _send_telegram(self, channel: WebhookChannel, content: str) -> dict:
        """Telegram Bot"""
        content = self._truncate(content, _PLATFORM_MAX_LEN["telegram"])
        url = f"https://api.telegram.org/bot{channel.bot_token}/sendMessage"
        payload = {
            "chat_id": channel.chat_id,
            "text": content,
            "parse_mode": "Markdown",
        }
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _send_ntfy(self, channel: WebhookChannel, content: str) -> dict:
        """ntfy 推送"""
        content = self._truncate(content, _PLATFORM_MAX_LEN["ntfy"])
        server = channel.server_url.rstrip("/") if channel.server_url else "https://ntfy.sh"
        url = f"{server}/{channel.topic}"
        resp = requests.post(
            url,
            data=content.encode("utf-8"),
            headers={
                "Title": "📰 Logos 新闻简报",
                "Content-Type": "text/markdown; charset=utf-8",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"ok": True}

    _SENDERS = {
        "feishu": "_send_feishu",
        "dingtalk": "_send_dingtalk",
        "wecom": "_send_wecom",
        "telegram": "_send_telegram",
        "ntfy": "_send_ntfy",
    }

    def send_to_channel(self, channel: WebhookChannel, content: str) -> dict:
        """向单个渠道发送消息"""
        sender_name = self._SENDERS.get(channel.platform)
        if not sender_name:
            raise ValueError(f"不支持的平台: {channel.platform}")
        sender = getattr(self, sender_name)
        try:
            result = sender(channel, content)
            logger.info(f"推送成功: {channel.name} ({channel.platform})")
            return {"status": "ok", "channel": channel.name, "result": result}
        except Exception as e:
            logger.error(f"推送失败: {channel.name} ({channel.platform}) — {e}")
            return {"status": "error", "channel": channel.name, "error": str(e)}

    def broadcast(self, content: str) -> list[dict]:
        """向所有已启用的渠道广播"""
        channels = self.load_channels()
        enabled = [ch for ch in channels if ch.enabled]
        if not enabled:
            logger.info("无已启用的推送渠道，跳过广播")
            return []
        results = []
        for ch in enabled:
            result = self.send_to_channel(ch, content)
            results.append(result)
        return results

    def test_channel(self, channel_id: str) -> dict:
        """发送测试消息"""
        channel = self.get_channel(channel_id)
        if not channel:
            return {"status": "error", "error": "渠道不存在"}
        test_content = (
            "# 🧪 Logos 推送测试\n\n"
            "这是一条来自 **Logos 新闻助手** 的测试消息。\n\n"
            "如果你能看到这条消息，说明推送渠道配置正确！ ✅\n\n"
            f"- 渠道名称: {channel.name}\n"
            f"- 平台: {channel.platform}\n"
        )
        return self.send_to_channel(channel, test_content)
