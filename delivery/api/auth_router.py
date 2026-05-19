"""Authentication API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from delivery.auth import AuthContext, get_current_actor

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
def get_me(ctx: AuthContext = Depends(get_current_actor)):
    return {
        "actor": ctx.actor,
        "role": ctx.role_value,
        "api_key_id": ctx.api_key_id,
    }
