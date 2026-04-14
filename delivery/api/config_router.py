"""配置管理 API"""
import os
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigResponse(BaseModel):
    llm_provider: str
    llm_api_key: str  # 脱敏后
    llm_base_url: str
    llm_model: str
    openai_api_key: str
    google_api_key: str
    anthropic_api_key: str
    embedding_api_key: str
    embedding_base_url: str
    embedding_model: str
    log_level: str
    article_retention_days: int
    news_api_key: str


class ConfigUpdate(BaseModel):
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    anthropic_api_key: str = ""
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""
    log_level: str = "INFO"
    article_retention_days: int = 90
    news_api_key: str = ""


def _mask_key(key: str) -> str:
    """脱敏 API Key，只显示前4位和后4位"""
    if not key or len(key) <= 8:
        return "*" * len(key) if key else ""
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _read_env_file() -> dict[str, str]:
    """解析 .env 文件为字典"""
    env_path = os.path.join(os.getcwd(), ".env")
    result = {}
    if not os.path.exists(env_path):
        return result
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip()
    return result


def _write_env_file(updates: dict[str, str]):
    """更新 .env 文件，保留注释和格式"""
    env_path = os.path.join(os.getcwd(), ".env")

    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # 添加新的键
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


@router.get("", response_model=ConfigResponse)
def get_config():
    """获取当前配置（API Key 脱敏）"""
    env = _read_env_file()
    return ConfigResponse(
        llm_provider=env.get("LLM_PROVIDER", "openai_compatible"),
        llm_api_key=_mask_key(env.get("LLM_API_KEY", "")),
        llm_base_url=env.get("LLM_BASE_URL", ""),
        llm_model=env.get("LLM_MODEL", ""),
        openai_api_key=_mask_key(env.get("OPENAI_API_KEY", "")),
        google_api_key=_mask_key(env.get("GOOGLE_API_KEY", "")),
        anthropic_api_key=_mask_key(env.get("ANTHROPIC_API_KEY", "")),
        embedding_api_key=_mask_key(env.get("EMBEDDING_API_KEY", "")),
        embedding_base_url=env.get("EMBEDDING_BASE_URL", ""),
        embedding_model=env.get("EMBEDDING_MODEL", ""),
        log_level=env.get("LOG_LEVEL", "INFO"),
        article_retention_days=int(env.get("ARTICLE_RETENTION_DAYS", "90")),
        news_api_key=_mask_key(env.get("NEWSAPI_KEY", "")),
    )


@router.put("")
def update_config(config: ConfigUpdate):
    """更新 .env 文件"""
    updates = {}
    data = config.model_dump()

    # 将 Pydantic 字段映射到 .env 键名
    field_to_env = {
        "llm_provider": "LLM_PROVIDER",
        "llm_api_key": "LLM_API_KEY",
        "llm_base_url": "LLM_BASE_URL",
        "llm_model": "LLM_MODEL",
        "openai_api_key": "OPENAI_API_KEY",
        "google_api_key": "GOOGLE_API_KEY",
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "embedding_api_key": "EMBEDDING_API_KEY",
        "embedding_base_url": "EMBEDDING_BASE_URL",
        "embedding_model": "EMBEDDING_MODEL",
        "log_level": "LOG_LEVEL",
        "article_retention_days": "ARTICLE_RETENTION_DAYS",
        "news_api_key": "NEWSAPI_KEY",
    }

    for field_name, env_key in field_to_env.items():
        value = data.get(field_name, "")
        # 跳过脱敏的值（含 *），保留原始值
        if isinstance(value, str) and "*" in value:
            continue
        updates[env_key] = str(value)

    try:
        _write_env_file(updates)
        # 热重载：写入 .env 后立即刷新运行时配置与组件
        from core.config_manager import get_config_manager
        reload_result = get_config_manager().reload()
        return {"status": "ok", "message": "配置已保存并立即生效", "reload": reload_result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {e}")


@router.post("/reload")
def reload_config():
    """手动触发配置热重载（重新读取 .env 并重建受影响组件）"""
    from core.config_manager import get_config_manager
    result = get_config_manager().reload()
    return {"status": "ok", **result}


@router.get("/providers")
def get_providers():
    """获取可用的 LLM 提供商列表"""
    return {
        "providers": [
            {
                "id": "openai_compatible",
                "name": "OpenAI 兼容 API",
                "description": "支持任何 OpenAI 格式的自定义端点",
                "fields": ["llm_api_key", "llm_base_url", "llm_model"],
            },
            {
                "id": "openai",
                "name": "OpenAI GPT",
                "description": "OpenAI 官方 GPT API",
                "fields": ["openai_api_key", "llm_model"],
            },
            {
                "id": "gemini",
                "name": "Google Gemini",
                "description": "Google Gemini 官方 API",
                "fields": ["google_api_key", "llm_model"],
            },
            {
                "id": "anthropic",
                "name": "Anthropic Claude",
                "description": "Anthropic Claude 官方 API",
                "fields": ["anthropic_api_key", "llm_model"],
            },
        ]
    }


class ModelFetchRequest(BaseModel):
    provider: str
    api_key: str = ""
    base_url: str = ""


@router.post("/models")
def fetch_models(req: ModelFetchRequest):
    """从远端获取可用模型列表"""
    import requests
    models = []
    
    real_key = req.api_key
    if "*" in real_key:
        env = _read_env_file()
        if req.provider == "openai":
            real_key = env.get("OPENAI_API_KEY", "")
        elif req.provider == "openai_compatible":
            real_key = env.get("LLM_API_KEY", "")
        elif req.provider == "gemini":
            real_key = env.get("GOOGLE_API_KEY", "")
            
    if req.provider in ("openai_compatible", "openai"):
        url = req.base_url.rstrip("/") + "/models" if req.base_url else "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {real_key}"}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if "data" in data:
                models = [m["id"] for m in data["data"]]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"获取模型列表失败: {e}")
            
    elif req.provider == "gemini":
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={real_key}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if "models" in data:
                models = [m["name"].replace("models/", "") for m in data["models"]]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"获取 Gemini 模型失败: {e}")
            
    else:
        raise HTTPException(status_code=400, detail="当前提供商不支持在线获取模型列表，请手动输入")
        
    return {"models": models}

