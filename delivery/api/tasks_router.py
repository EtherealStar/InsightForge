import structlog
from fastapi import APIRouter, HTTPException
from celery.result import AsyncResult
from scheduler.celery_app import app as celery_app

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = structlog.get_logger(__name__)

@router.get("/{task_id}")
def get_task_status(task_id: str):
    """获取异步任务的状态和结果"""
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        
        response = {
            "task_id": task_id,
            "status": task_result.status,
            "ready": task_result.ready(),
        }
        
        if task_result.ready():
            if task_result.successful():
                response["result"] = task_result.result
            else:
                response["error"] = str(task_result.result)
                
        return response
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取任务状态失败: {e}")
