"""深度研究 API — 研究报告 CRUD + SSE 流式研究"""
import io
import json
import os
import structlog
import zipfile
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/research", tags=["research"])
logger = structlog.get_logger(__name__)

_RESEARCH_DIR = os.path.join("output", "research")


class ResearchRequest(BaseModel):
    topic: str


class ResearchPlanUpdateRequest(BaseModel):
    plan: Any
    todos: list[dict]


class BatchFilenamesRequest(BaseModel):
    filenames: list[str]


def _validate_filename(filename: str) -> None:
    """校验文件名安全性，防止路径穿越"""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail=f"无效的文件名: {filename}")


def _get_plan_execute_runner():
    from core.config_manager import get_config_manager
    from agent.react.plan_execute_runner import PlanExecuteRunner
    from agent.tools.registry import get_tool_registry
    from services.deep_research_service import DeepResearchService
    from services.memory_service import MemoryService

    mgr = get_config_manager()
    if not mgr.llm_client:
        raise HTTPException(
            status_code=503, detail="LLM 客户端未配置，无法执行深度研究"
        )
    return PlanExecuteRunner(
        llm_client=mgr.llm_client,
        tool_registry=get_tool_registry(),
        session_store=mgr.agent_session_store,
        report_service=DeepResearchService(output_dir=_RESEARCH_DIR),
        memory_service=MemoryService(
            mgr.memory_store,
            mgr.agent_session_store,
            mgr.llm_client,
        ),
        max_steps=15,
    )


def _get_session_store():
    from core.config_manager import get_config_manager

    return get_config_manager().agent_session_store


@router.post("/sessions/plan")
def create_research_plan(req: ResearchRequest):
    """生成 Plan Execute 研究计划，等待用户审阅。"""
    try:
        runner = _get_plan_execute_runner()
        session = runner.generate_plan(req.topic)
        return {
            "session_id": session.id,
            "topic": session.topic,
            "plan": session.plan,
            "todos": [todo.to_dict() for todo in session.todos],
            "status": session.status.value,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("research.plan_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"生成研究计划失败: {e}")


@router.put("/sessions/{session_id}/plan")
def update_research_plan(session_id: str, req: ResearchPlanUpdateRequest):
    """保存用户审阅后的 plan 和 todo list。"""
    try:
        from models.agent_session import ResearchTodo

        todos = [
            ResearchTodo.from_dict(todo)
            for todo in req.todos
            if isinstance(todo, dict)
        ]
        session = _get_session_store().save_plan(session_id, req.plan, todos)
        return session.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(
            "research.plan_update_failed",
            session_id=session_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"保存研究计划失败: {e}")


@router.post("/sessions/{session_id}/execute/stream")
def execute_research_session(session_id: str):
    """按已确认计划流式执行深度研究。"""
    try:
        runner = _get_plan_execute_runner()
        session = _get_session_store().get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="研究会话不存在")

        def event_generator():
            try:
                for event in runner.execute(session):
                    event_data = json.dumps(
                        event.to_dict(), ensure_ascii=False
                    )
                    yield f"data: {event_data}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.exception(
                    "research.execute_failed",
                    session_id=session_id,
                    error=str(e),
                )
                error_event = json.dumps(
                    {
                        "event_type": "error",
                        "content": str(e),
                        "run_id": session_id,
                    },
                    ensure_ascii=False,
                )
                yield f"data: {error_event}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "research.execute_init_failed",
            session_id=session_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"执行研究失败: {e}")


@router.get("/sessions/{session_id}")
def get_research_session(session_id: str):
    """获取 Plan Execute 研究会话详情。"""
    session = _get_session_store().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="研究会话不存在")
    return session.to_dict()


@router.get("")
def list_reports():
    """获取所有研究报告列表"""
    from services.deep_research_service import DeepResearchService

    service = DeepResearchService(output_dir=_RESEARCH_DIR)
    reports = service.list_reports()
    return {"reports": reports}


@router.get("/{filename}")
def get_report(filename: str):
    """获取单份研究报告内容"""
    _validate_filename(filename)
    from services.deep_research_service import DeepResearchService

    service = DeepResearchService(output_dir=_RESEARCH_DIR)
    report = service.get_report(filename)
    if report is None:
        raise HTTPException(status_code=404, detail="未找到该研究报告")
    return report


@router.delete("/{filename}")
def delete_report(filename: str):
    """删除一份研究报告"""
    _validate_filename(filename)
    from services.deep_research_service import DeepResearchService

    service = DeepResearchService(output_dir=_RESEARCH_DIR)
    if service.delete_report(filename):
        return {"status": "ok", "message": f"已删除: {filename}"}
    raise HTTPException(status_code=404, detail="未找到该研究报告")


@router.post("/batch-delete")
def batch_delete_reports(req: BatchFilenamesRequest):
    """批量删除研究报告"""
    from services.deep_research_service import DeepResearchService

    if not req.filenames:
        raise HTTPException(status_code=400, detail="请至少选择一份报告")

    deleted = 0
    errors = []
    for filename in req.filenames:
        try:
            _validate_filename(filename)
            service = DeepResearchService(output_dir=_RESEARCH_DIR)
            if service.delete_report(filename):
                deleted += 1
            else:
                errors.append(f"文件不存在: {filename}")
        except HTTPException:
            errors.append(f"无效的文件名: {filename}")
        except Exception as e:
            errors.append(f"删除 {filename} 失败: {e}")

    return {"deleted": deleted, "errors": errors}


@router.post("/batch-export")
def batch_export_reports(req: BatchFilenamesRequest):
    """批量导出研究报告（单文件 .md，多文件 .zip）"""
    if not req.filenames:
        raise HTTPException(status_code=400, detail="请至少选择一份报告")

    valid_files: list[tuple[str, str]] = []
    for filename in req.filenames:
        _validate_filename(filename)
        filepath = os.path.join(_RESEARCH_DIR, filename)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail=f"未找到报告: {filename}")
        valid_files.append((filename, filepath))

    if len(valid_files) == 1:
        filename, filepath = valid_files[0]
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type="text/markdown",
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, filepath in valid_files:
            zf.write(filepath, arcname=filename)
    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="research_export.zip"',
        },
    )


@router.post("/push/{filename}")
def push_report(filename: str):
    """推送研究报告到所有启用的 Webhook 渠道"""
    _validate_filename(filename)
    from services.deep_research_service import DeepResearchService

    service = DeepResearchService(output_dir=_RESEARCH_DIR)
    report = service.get_report(filename)
    if report is None:
        raise HTTPException(status_code=404, detail="未找到该研究报告")

    try:
        from services.webhook_service import WebhookService
        webhook_service = WebhookService()
        results = webhook_service.broadcast(report["content"])
        push_ok = sum(1 for r in results if r["status"] == "ok")
        return {
            "status": "ok",
            "message": f"推送完成: {push_ok}/{len(results)} 个渠道成功",
            "push_results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"推送失败: {e}")
