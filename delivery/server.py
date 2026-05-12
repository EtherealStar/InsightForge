"""
FastAPI 服务入口
启动方式：python -m delivery.server
"""
import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uuid
import time
import structlog

from delivery.api.config_router import router as config_router
from delivery.api.settings_router import router as settings_router
from delivery.api.news_router import router as news_router
from delivery.api.brief_router import router as brief_router
from delivery.api.query_router import router as query_router
from delivery.api.newsapi_router import router as newsapi_router
from delivery.api.webhook_router import router as webhook_router
from delivery.api.research_router import router as research_router
from delivery.api.tasks_router import router as tasks_router
from delivery.api.memory_router import router as memory_router

app = FastAPI(
    title="Logos — AI 新闻分析助手",
    description="个人 AI 新闻分析助手 API",
    version="1.0.0",
)

# CORS — 开发模式允许 Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def structlog_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        client_ip=request.client.host if request.client else None,
        method=request.method,
        path=request.url.path,
    )
    
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        structlog.get_logger("fastapi.access").info(
            "request_finished",
            status_code=response.status_code,
            duration=process_time
        )
        return response
    except Exception as e:
        process_time = time.time() - start_time
        structlog.get_logger("fastapi.error").exception(
            "request_failed",
            duration=process_time
        )
        raise

# 注册 API 路由
app.include_router(config_router)
app.include_router(settings_router)
app.include_router(news_router)
app.include_router(brief_router)
app.include_router(query_router)
app.include_router(newsapi_router)
app.include_router(webhook_router)
app.include_router(research_router)
app.include_router(tasks_router)
app.include_router(memory_router)

# 生产模式：挂载 Vue 构建产物
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(_STATIC_DIR):
    # SPA 路由回退：所有非 /api 的请求返回 index.html
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # 优先返回静态文件
        file_path = os.path.join(_STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # 其他路径返回 index.html（SPA 路由）
        return FileResponse(os.path.join(_STATIC_DIR, "index.html"))

    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")


@app.on_event("startup")
def startup_register_tools():
    """应用启动时注册内置 Agent 工具。"""
    try:
        from agent.tools.builtin import register_builtin_tools
        from core.config_manager import get_config_manager

        mgr = get_config_manager()
        count = register_builtin_tools(mgr)
        print(f" 已注册 {count} 个内置 Agent 工具")
    except Exception as e:
        # 工具注册失败不阻止服务启动
        print(f"  Agent 工具注册失败 (不影响基本功能): {e}")


@app.get("/api/health")
def health():
    return {"status": "ok", "message": "Logos 后端运行中"}


def main():
    import uvicorn
    import logging
    from core.config_manager import get_config_manager
    from core.logging import setup_logging
    
    config = get_config_manager().config
    setup_logging(level=config.log_level)
    
    # 接管 uvicorn 日志
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True

    print("\n Logos — AI 新闻分析助手")
    print("=" * 40)

    # 检查是否有前端构建产物
    if os.path.exists(_STATIC_DIR):
        print(" 检测到前端构建产物，生产模式启动")
        print(" 访问: http://localhost:8005")
    else:
        print("  未检测到前端构建产物")
        print("   前端开发模式请运行: cd frontend && npm run dev")
        print(" API 文档: http://localhost:8005/docs")

    print("=" * 40 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8005, log_config=None)


if __name__ == "__main__":
    main()
