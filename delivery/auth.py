"""Application API key authentication and role dependencies."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, Header, HTTPException, Request, status

from models.auth import ActorRole, ApiKeyStatus


ROLE_RANK = {
    ActorRole.VIEWER.value: 10,
    ActorRole.ANALYST.value: 20,
    ActorRole.ADMIN.value: 30,
}


@dataclass(frozen=True)
class AuthContext:
    actor: str
    role: ActorRole | str
    api_key_id: str = ""

    @property
    def role_value(self) -> str:
        return self.role.value if hasattr(self.role, "value") else str(self.role)


def hash_api_key(api_key: str) -> str:
    """Hash plaintext API keys before persistence or lookup."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return ""
    return token.strip()


def _get_manager():
    from core.config_manager import get_config_manager

    return get_config_manager()


def _auth_disabled(config) -> bool:
    app_env = getattr(config, "app_env", "development")
    auth_enabled = bool(getattr(config, "auth_enabled", False))
    return app_env == "development" and not auth_enabled


def _status_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _env_key_context(config, api_key: str) -> AuthContext | None:
    configured = getattr(config, "app_api_keys", []) or []
    api_key_hash = hash_api_key(api_key)
    for configured_key in configured:
        configured_key = str(configured_key)
        if hmac.compare_digest(api_key, configured_key) or hmac.compare_digest(
            api_key_hash, configured_key
        ):
            return AuthContext(
                actor="env-api-key",
                role=ActorRole.ADMIN,
                api_key_id="env",
            )
    return None


def get_current_actor(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthContext:
    """Resolve the current API actor.

    Development mode with AUTH_ENABLED=false returns a synthetic admin actor so
    local tools and existing tests remain frictionless.
    """
    existing = getattr(request.state, "auth_context", None)
    if existing:
        return existing

    try:
        config = _get_manager().config
    except Exception:
        config = None
    if config is None or _auth_disabled(config):
        ctx = AuthContext(actor="system", role=ActorRole.ADMIN, api_key_id="dev")
        request.state.auth_context = ctx
        return ctx

    api_key = _extract_bearer(authorization) or (x_api_key or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    key_hash = hash_api_key(api_key)
    mgr = _get_manager()
    auth_store = getattr(mgr, "auth_store", None)
    record = auth_store.get_api_key_by_hash(key_hash) if auth_store else None
    if record is None:
        env_ctx = _env_key_context(config, api_key)
        if env_ctx:
            request.state.auth_context = env_ctx
            return env_ctx
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    if _status_value(record.status) != ApiKeyStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is revoked",
        )

    try:
        auth_store.update_last_used(record.id)
    except Exception:
        # Authentication should not fail because last-used telemetry failed.
        pass

    ctx = AuthContext(
        actor=record.name or record.id,
        role=record.role,
        api_key_id=record.id,
    )
    request.state.auth_context = ctx
    return ctx


def require_role(*roles: ActorRole | str) -> Callable[[AuthContext], AuthContext]:
    required_rank = min(ROLE_RANK[r.value if hasattr(r, "value") else str(r)] for r in roles)

    def dependency(ctx: AuthContext = Depends(get_current_actor)) -> AuthContext:
        actual_rank = ROLE_RANK.get(ctx.role_value, 0)
        if actual_rank < required_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return ctx

    return dependency


require_viewer = require_role(ActorRole.VIEWER)
require_analyst = require_role(ActorRole.ANALYST)
require_admin = require_role(ActorRole.ADMIN)
