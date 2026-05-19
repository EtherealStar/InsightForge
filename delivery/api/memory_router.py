"""记忆系统 API。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from delivery.auth import require_analyst, require_viewer
from models.memory import CoreMemoryKind, MemoryStatus, MemoryType

router = APIRouter(prefix="/api/memory", tags=["memory"], dependencies=[Depends(require_viewer)])


class CoreMemoryRequest(BaseModel):
    kind: CoreMemoryKind
    title: str
    content: str


class PersistentMemoryRequest(BaseModel):
    memory_type: MemoryType
    title: str
    summary: str
    content: str
    source_session_id: str | None = None
    confidence: float | None = None


class MemoryStatusRequest(BaseModel):
    status: MemoryStatus


def _get_memory_store():
    from core.config_manager import get_config_manager

    return get_config_manager().memory_store


@router.get("/core")
def list_core_memories(kind: CoreMemoryKind | None = None):
    store = _get_memory_store()
    return {
        "items": [
            item.to_dict()
            for item in store.get_active_core_memories(kind.value if kind else None)
        ]
    }


@router.post("/core", dependencies=[Depends(require_analyst)])
def create_core_memory(req: CoreMemoryRequest):
    store = _get_memory_store()
    item = store.create_core_memory_revision(
        kind=req.kind.value,
        title=req.title,
        content=req.content,
    )
    return item.to_dict()


@router.get("/index")
def get_memory_index():
    store = _get_memory_store()
    items = store.list_memory_index()
    return {
        "items": [item.to_dict() for item in items],
        "memory_document": "\n".join(item.line for item in items),
    }


@router.get("/persistent")
def list_persistent_memories(
    status: MemoryStatus | None = None,
    memory_type: MemoryType | None = None,
):
    store = _get_memory_store()
    return {
        "items": [
            item.to_dict()
            for item in store.list_persistent_memories(
                status=status,
                memory_type=memory_type,
            )
        ]
    }


@router.post("/persistent", dependencies=[Depends(require_analyst)])
def create_persistent_memory(req: PersistentMemoryRequest):
    store = _get_memory_store()
    item = store.create_persistent_memory(
        memory_type=req.memory_type,
        title=req.title,
        summary=req.summary,
        content=req.content,
        source_session_id=req.source_session_id,
        confidence=req.confidence,
        status=MemoryStatus.PENDING,
    )
    return item.to_dict()


@router.put("/persistent/{memory_id}/status", dependencies=[Depends(require_analyst)])
def update_persistent_memory_status(memory_id: str, req: MemoryStatusRequest):
    try:
        item = _get_memory_store().update_persistent_memory_status(
            memory_id,
            req.status,
        )
        return item.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/persistent/{memory_id}", dependencies=[Depends(require_analyst)])
def delete_persistent_memory(memory_id: str):
    try:
        _get_memory_store().delete_persistent_memory(memory_id)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
