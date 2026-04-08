"""
FastAPI 服务入口
启动方式：python -m delivery.server
"""
import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from delivery.api.config_router import router as config_router
from delivery.api.settings_router import router as settings_router
from delivery.api.news_router import router as news_router
from delivery.api.brief_router import router as brief_router
from delivery.api.query_router import router as query_router

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

# 注册 API 路由
app.include_router(config_router)
app.include_router(settings_router)
app.include_router(news_router)
app.include_router(brief_router)
app.include_router(query_router)

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


@app.get("/api/health")
def health():
    return {"status": "ok", "message": "Logos 后端运行中"}


def main():
    import uvicorn
    print("\n📰 Logos — AI 新闻分析助手")
    print("=" * 40)

    # 检查是否有前端构建产物
    if os.path.exists(_STATIC_DIR):
        print("✅ 检测到前端构建产物，生产模式启动")
        print("🌐 访问: http://localhost:8005")
    else:
        print("⚠  未检测到前端构建产物")
        print("   前端开发模式请运行: cd frontend && npm run dev")
        print("🌐 API 文档: http://localhost:8005/docs")

    print("=" * 40 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8005)


if __name__ == "__main__":
    main()
