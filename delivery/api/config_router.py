"""配置管理 API."""
from __future__ import annotations

import structlog

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from core.config_manager import get_config_manager
from delivery.auth import AuthContext, require_admin
from services.config_audit_service import ConfigAuditService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/config", tags=["config"])

SECRET_FIELDS = {
    "llm_api_key",
    "openai_api_key",
    "google_api_key",
    "anthropic_api_key",
    "embedding_api_key",
    "rerank_api_key",
    "structured_extraction_api_key",
    "judge_api_key",
    "news_api_key",
    "tavily_api_key",
}

FIELD_TO_ENV = {
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
    "embedding_vector_size": "EMBEDDING_VECTOR_SIZE",
    "rerank_enabled": "RERANK_ENABLED",
    "rerank_api_key": "RERANK_API_KEY",
    "rerank_base_url": "RERANK_BASE_URL",
    "rerank_model": "RERANK_MODEL",
    "rerank_top_k_multiplier": "RERANK_TOP_K_MULTIPLIER",
    "structured_extraction_provider": "STRUCTURED_EXTRACTION_PROVIDER",
    "structured_extraction_api_key": "STRUCTURED_EXTRACTION_API_KEY",
    "structured_extraction_base_url": "STRUCTURED_EXTRACTION_BASE_URL",
    "structured_extraction_model": "STRUCTURED_EXTRACTION_MODEL",
    "structured_extraction_temperature": "STRUCTURED_EXTRACTION_TEMPERATURE",
    "structured_extraction_max_tokens": "STRUCTURED_EXTRACTION_MAX_TOKENS",
    "judge_provider": "JUDGE_PROVIDER",
    "judge_api_key": "JUDGE_API_KEY",
    "judge_base_url": "JUDGE_BASE_URL",
    "judge_model": "JUDGE_MODEL",
    "judge_temperature": "JUDGE_TEMPERATURE",
    "judge_max_tokens": "JUDGE_MAX_TOKENS",
    "app_env": "APP_ENV",
    "auth_enabled": "AUTH_ENABLED",
    "report_quality_min_score": "REPORT_QUALITY_MIN_SCORE",
    "report_quality_auto_publish": "REPORT_QUALITY_AUTO_PUBLISH",
    "log_level": "LOG_LEVEL",
    "article_retention_days": "ARTICLE_RETENTION_DAYS",
    "news_api_key": "NEWSAPI_KEY",
    "tavily_api_key": "TAVILY_API_KEY",
}

PRODUCTION_READONLY_ENV = {
    "APP_ENV",
    "AUTH_ENABLED",
    "APP_API_KEYS",
    "PG_DSN",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_DOCUMENTS_COLLECTION",
    "QDRANT_DISTANCE",
    "VECTOR_BACKEND",
    "UPLOAD_STORAGE_ROOT",
    "UPLOAD_MAX_FILE_SIZE_MB",
    "UPLOAD_MAX_BATCH_SIZE_MB",
    "UPLOAD_MAX_ARCHIVE_FILES",
    "UPLOAD_MAX_ARCHIVE_UNPACKED_MB",
}


class ConfigResponse(BaseModel):
    llm_provider: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    openai_api_key: str
    google_api_key: str
    anthropic_api_key: str
    embedding_api_key: str
    embedding_base_url: str
    embedding_model: str
    embedding_vector_size: int
    rerank_enabled: bool
    rerank_api_key: str
    rerank_base_url: str
    rerank_model: str
    rerank_top_k_multiplier: int
    structured_extraction_provider: str
    structured_extraction_api_key: str
    structured_extraction_base_url: str
    structured_extraction_model: str
    structured_extraction_temperature: float
    structured_extraction_max_tokens: int
    judge_provider: str
    judge_api_key: str
    judge_base_url: str
    judge_model: str
    judge_temperature: float
    judge_max_tokens: int
    app_env: str
    auth_enabled: bool
    report_quality_min_score: float
    report_quality_auto_publish: bool
    production_readonly_fields: list[str]
    log_level: str
    article_retention_days: int
    news_api_key: str
    tavily_api_key: str


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
    embedding_vector_size: int = 1536
    rerank_enabled: bool = False
    rerank_api_key: str = ""
    rerank_base_url: str = ""
    rerank_model: str = ""
    rerank_top_k_multiplier: int = 3
    structured_extraction_provider: str = "openai_compatible"
    structured_extraction_api_key: str = ""
    structured_extraction_base_url: str = ""
    structured_extraction_model: str = ""
    structured_extraction_temperature: float = 0.0
    structured_extraction_max_tokens: int = 2048
    judge_provider: str = "openai_compatible"
    judge_api_key: str = ""
    judge_base_url: str = ""
    judge_model: str = ""
    judge_temperature: float = 0.0
    judge_max_tokens: int = 2048
    app_env: str = "development"
    auth_enabled: bool = False
    report_quality_min_score: float = 0.75
    report_quality_auto_publish: bool = False
    log_level: str = "INFO"
    article_retention_days: int = 90
    news_api_key: str = ""
    tavily_api_key: str = ""


class ModelFetchRequest(BaseModel):
    provider: str
    api_key: str = ""
    base_url: str = ""


def _mask_key(key: str) -> str:
    if not key or len(key) <= 8:
        return "*" * len(key) if key else ""
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _env_path() -> Path:
    return Path(os.getcwd()) / ".env"


def _read_env_file() -> dict[str, str]:
    env_path = _env_path()
    result: dict[str, str] = {}
    if not env_path.exists():
        return result
    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            result[key.strip()] = value.strip()
    return result


def _write_env_file(updates: dict[str, str]) -> None:
    env_path = _env_path()
    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True) if env_path.exists() else []
    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    temp_path = env_path.with_suffix(env_path.suffix + ".tmp")
    temp_path.write_text("".join(new_lines), encoding="utf-8")
    os.replace(temp_path, env_path)


def _bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.lower() in ("true", "1", "yes", "on")


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _config_audit_service():
    return ConfigAuditService(get_config_manager().config_audit_store)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or request.headers.get("X-Request-ID", "")


def _updates_from_model(config: ConfigUpdate, current_env: dict[str, str]) -> dict[str, str]:
    data = config.model_dump()
    app_env = current_env.get("APP_ENV", getattr(get_config_manager().config, "app_env", "development"))
    updates: dict[str, str] = {}
    for field_name, env_key in FIELD_TO_ENV.items():
        value = data.get(field_name, "")
        if app_env == "production" and env_key in PRODUCTION_READONLY_ENV:
            if not _same_env_value(current_env.get(env_key, ""), value):
                raise HTTPException(
                    status_code=400,
                    detail=f"{env_key} is read-only in production",
                )
            continue
        if field_name in SECRET_FIELDS and isinstance(value, str) and "*" in value:
            continue
        updates[env_key] = str(value)
    return updates


def _same_env_value(current: str, next_value) -> bool:
    if isinstance(next_value, bool):
        return current.lower() in ("true", "1", "yes", "on") if next_value else current.lower() in ("false", "0", "no", "off", "")
    return str(current) == str(next_value)


@router.get("", response_model=ConfigResponse)
def get_config(_actor: AuthContext = Depends(require_admin)):
    env = _read_env_file()
    app_env = env.get("APP_ENV", getattr(get_config_manager().config, "app_env", "development"))
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
        embedding_vector_size=_int(env.get("EMBEDDING_VECTOR_SIZE", ""), 1536),
        rerank_enabled=_bool(env.get("RERANK_ENABLED", ""), False),
        rerank_api_key=_mask_key(env.get("RERANK_API_KEY", "")),
        rerank_base_url=env.get("RERANK_BASE_URL", ""),
        rerank_model=env.get("RERANK_MODEL", ""),
        rerank_top_k_multiplier=_int(env.get("RERANK_TOP_K_MULTIPLIER", ""), 3),
        structured_extraction_provider=env.get("STRUCTURED_EXTRACTION_PROVIDER", "openai_compatible"),
        structured_extraction_api_key=_mask_key(env.get("STRUCTURED_EXTRACTION_API_KEY", "")),
        structured_extraction_base_url=env.get("STRUCTURED_EXTRACTION_BASE_URL", ""),
        structured_extraction_model=env.get("STRUCTURED_EXTRACTION_MODEL", ""),
        structured_extraction_temperature=_float(env.get("STRUCTURED_EXTRACTION_TEMPERATURE", ""), 0.0),
        structured_extraction_max_tokens=_int(env.get("STRUCTURED_EXTRACTION_MAX_TOKENS", ""), 2048),
        judge_provider=env.get("JUDGE_PROVIDER", "openai_compatible"),
        judge_api_key=_mask_key(env.get("JUDGE_API_KEY", "")),
        judge_base_url=env.get("JUDGE_BASE_URL", ""),
        judge_model=env.get("JUDGE_MODEL", ""),
        judge_temperature=_float(env.get("JUDGE_TEMPERATURE", ""), 0.0),
        judge_max_tokens=_int(env.get("JUDGE_MAX_TOKENS", ""), 2048),
        app_env=app_env,
        auth_enabled=_bool(env.get("AUTH_ENABLED", ""), False),
        report_quality_min_score=_float(env.get("REPORT_QUALITY_MIN_SCORE", ""), 0.75),
        report_quality_auto_publish=_bool(env.get("REPORT_QUALITY_AUTO_PUBLISH", ""), False),
        production_readonly_fields=sorted(PRODUCTION_READONLY_ENV) if app_env == "production" else [],
        log_level=env.get("LOG_LEVEL", "INFO"),
        article_retention_days=_int(env.get("ARTICLE_RETENTION_DAYS", ""), 90),
        news_api_key=_mask_key(env.get("NEWSAPI_KEY", "")),
        tavily_api_key=_mask_key(env.get("TAVILY_API_KEY", "")),
    )


@router.put("")
def update_config(
    config: ConfigUpdate,
    request: Request,
    actor: AuthContext = Depends(require_admin),
):
    before = _read_env_file()
    updates = _updates_from_model(config, before)
    try:
        _write_env_file(updates)
        reload_result = get_config_manager().reload()
        after = _read_env_file()
        _config_audit_service().append(
            actor=actor.actor,
            action="config_updated",
            target=".env",
            before=before,
            after=after,
            request_id=_request_id(request),
        )
        return {"status": "ok", "message": "配置已保存并立即生效", "reload": reload_result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {e}")


@router.post("/reload")
def reload_config(
    request: Request,
    actor: AuthContext = Depends(require_admin),
):
    before = _read_env_file()
    try:
        result = get_config_manager().reload()
        after = _read_env_file()
        _config_audit_service().append(
            actor=actor.actor,
            action="config_reloaded",
            target=".env",
            before=before,
            after=after,
            request_id=_request_id(request),
        )
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"配置重载失败: {e}")


@router.get("/audit")
def list_config_audit(
    target: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _actor: AuthContext = Depends(require_admin),
):
    logs = get_config_manager().config_audit_store.list_config_audit(
        target=target,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [
            {
                **log.__dict__,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/providers")
def get_providers(_actor: AuthContext = Depends(require_admin)):
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


@router.post("/models")
def fetch_models(
    req: ModelFetchRequest,
    _actor: AuthContext = Depends(require_admin),
):
    """从远端获取可用模型列表."""
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
            logger.warning("fetch_models_failed", provider=req.provider, error=str(e))
            raise HTTPException(status_code=400, detail="获取模型列表失败，请检查 API Key 和 Base URL 是否正确")

    elif req.provider == "gemini":
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models"
            headers = {"x-goog-api-key": real_key}
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if "models" in data:
                models = [m["name"].replace("models/", "") for m in data["models"]]
        except Exception as e:
            logger.warning("fetch_gemini_models_failed", error=str(e))
            raise HTTPException(status_code=400, detail="获取 Gemini 模型失败，请检查 API Key 是否正确")
    else:
        raise HTTPException(status_code=400, detail="当前提供商不支持在线获取模型列表，请手动输入")

    return {"models": models}
