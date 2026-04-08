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
    from core.config import AppConfig
    config = AppConfig()

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
    from core.config import AppConfig
    config = AppConfig()

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
        from core.config import AppConfig
        from core.factory import create_article_store, create_llm_client
        from services.brief_service import BriefService

        config = AppConfig()
        article_store = create_article_store(config)
        llm_client = create_llm_client(config)

        service = BriefService(article_store, llm_client, config.output_path)
        brief = service.generate(hours=24)

        return {
            "status": "ok",
            "article_count": brief.article_count,
            "generated_at": brief.generated_at.isoformat(),
            "content": brief.content_markdown,
        }
    except Exception as e:
        logger.error(f"简报生成失败: {e}")
        raise HTTPException(status_code=500, detail=f"简报生成失败: {e}")
