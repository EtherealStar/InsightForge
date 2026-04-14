"""简报管理 API"""
import os
import glob
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/briefs", tags=["briefs"])
logger = logging.getLogger(__name__)


@router.get("")
def list_briefs():
    """获取所有简报文件列表"""
    from core.config_manager import get_config_manager
    config = get_config_manager().config

    brief_files = sorted(
        glob.glob(os.path.join(config.output_path, "daily_brief_*.md")),
        reverse=True,
    )

    briefs = []
    for filepath in brief_files:
        filename = os.path.basename(filepath)
        mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
        # 从文件名提取日期
        date_str = filename.replace("daily_brief_", "").replace(".md", "")
        briefs.append({
            "filename": filename,
            "date": date_str,
            "generated_at": mod_time.isoformat(),
            "size_bytes": os.path.getsize(filepath),
        })

    return {"briefs": briefs}


@router.get("/{filename}")
def get_brief(filename: str):
    """获取单份简报内容"""
    from core.config_manager import get_config_manager
    config = get_config_manager().config

    # 安全检查：防止路径穿越
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    filepath = os.path.join(config.output_path, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="未找到该简报")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
    return {
        "filename": filename,
        "content": content,
        "generated_at": mod_time.isoformat(),
    }


@router.post("/generate")
def generate_brief():
    """手动生成简报"""
    try:
        from core.config_manager import get_config_manager
        from services.brief_service import BriefService

        mgr = get_config_manager()
        service = BriefService(mgr.article_store, mgr.llm_client, mgr.config.output_path)
        brief = service.generate(hours=24)

        # 自动推送（如果已启用）
        push_results = []
        try:
            from services.webhook_service import WebhookService
            webhook_service = WebhookService()
            if webhook_service.get_auto_push():
                push_results = webhook_service.broadcast(brief.content_markdown)
                push_ok = sum(1 for r in push_results if r["status"] == "ok")
                logger.info(f"自动推送: {push_ok}/{len(push_results)} 个渠道成功")
        except Exception as push_err:
            logger.warning(f"自动推送异常（不影响简报生成）: {push_err}")

        return {
            "status": "ok",
            "article_count": brief.article_count,
            "generated_at": brief.generated_at.isoformat(),
            "content": brief.content_markdown,
            "push_results": push_results,
        }
    except Exception as e:
        logger.error(f"简报生成失败: {e}")
        raise HTTPException(status_code=500, detail=f"简报生成失败: {e}")
