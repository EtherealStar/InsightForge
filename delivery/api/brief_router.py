"""简报管理 API"""
import io
import os
import glob
import structlog
import zipfile
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/briefs", tags=["briefs"])
logger = structlog.get_logger(__name__)


class BatchFilenamesRequest(BaseModel):
    """批量操作请求体"""
    filenames: list[str]


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
    """手动生成简报（同步执行，直接返回结果或报错）"""
    from core.config_manager import get_config_manager
    from services.brief_service import BriefService

    mgr = get_config_manager()
    mgr.reload()

    # 检查 LLM 客户端是否可用
    if mgr.llm_client is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "LLM 未就绪：请检查 .env 中的 llm_provider、llm_api_key、"
                "llm_base_url 配置是否正确，以及 API 地址是否可访问"
            ),
        )

    # 检查文章存储是否可用
    if mgr.article_store is None:
        raise HTTPException(
            status_code=503,
            detail="数据库未就绪：PostgreSQL 连接失败，请检查 pg_dsn 配置",
        )

    try:
        service = BriefService(
            article_store=mgr.article_store,
            llm_client=mgr.llm_client,
            output_path=mgr.config.output_path,
        )
        brief = service.generate(hours=mgr.config.brief_fetch_hours)
        return {
            "status": "ok",
            "filename": f"daily_brief_{brief.date.strftime("%Y-%m-%d")}.md",
            "article_count": brief.article_count,
            "generated_at": brief.generated_at.isoformat(),
            "message": f"简报已生成，覆盖 {brief.article_count} 篇文章",
        }
    except RuntimeError as e:
        err_msg = str(e)
        logger.error(f"简报生成失败: {err_msg}")
        raise HTTPException(status_code=502, detail=err_msg)
    except Exception as e:
        logger.error(f"简报生成失败: {e}")
        raise HTTPException(status_code=500, detail=f"简报生成失败: {e}")


def _validate_filename(filename: str) -> None:
    """校验文件名安全性，防止路径穿越"""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail=f"无效的文件名: {filename}")


@router.post("/batch-delete")
def batch_delete_briefs(req: BatchFilenamesRequest):
    """批量删除简报文件"""
    from core.config_manager import get_config_manager
    config = get_config_manager().config

    if not req.filenames:
        raise HTTPException(status_code=400, detail="请至少选择一份简报")

    deleted = 0
    errors = []
    for filename in req.filenames:
        try:
            _validate_filename(filename)
            filepath = os.path.join(config.output_path, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                deleted += 1
                logger.info(f"已删除简报: {filename}")
            else:
                errors.append(f"文件不存在: {filename}")
        except HTTPException:
            errors.append(f"无效的文件名: {filename}")
        except Exception as e:
            errors.append(f"删除 {filename} 失败: {e}")

    return {"deleted": deleted, "errors": errors}


@router.post("/batch-export")
def batch_export_briefs(req: BatchFilenamesRequest):
    """批量导出简报文件（单文件返回 .md，多文件返回 .zip）"""
    from core.config_manager import get_config_manager
    config = get_config_manager().config

    if not req.filenames:
        raise HTTPException(status_code=400, detail="请至少选择一份简报")

    # 校验并收集有效文件路径
    valid_files: list[tuple[str, str]] = []  # (filename, filepath)
    for filename in req.filenames:
        _validate_filename(filename)
        filepath = os.path.join(config.output_path, filename)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail=f"未找到简报: {filename}")
        valid_files.append((filename, filepath))

    # 单文件：直接返回 .md 下载
    if len(valid_files) == 1:
        filename, filepath = valid_files[0]
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type="text/markdown",
        )

    # 多文件：打包为 ZIP 返回
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, filepath in valid_files:
            zf.write(filepath, arcname=filename)
    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="briefs_export.zip"',
        },
    )
