# Logos — 个人 AI 新闻分析助手

一个运行在本地的个人 AI 新闻分析助手，具备两种核心能力：

1. **定时 Pipeline**：自动从多个新闻来源抓取内容，清洗、向量化后存储，每天早晨生成一份日报。
2. **交互查询**：用自然语言提问，系统通过 RAG 从历史新闻库中检索相关内容，调用 AI 给出分析回答。

## 快速开始

### 1. 环境准备

```bash
# 创建并激活 Python 虚拟环境
python -m venv .venv
.venv\Scripts\activate    # Windows

# 安装 Python 后端依赖
pip install -r requirements.txt

# 配置环境变量
copy .env.example .env
# 编辑 .env 填入 API Key 和自定义端点
```

### 2. 安装前端依赖

```bash
cd frontend
pnpm install
cd ..
```

### 3. 启动方式

#### 方式 A：开发模式（推荐开发时使用）

需要同时启动两个终端：

```bash
# 终端 1 — 启动 FastAPI 后端（端口 8000）
.venv\Scripts\python -m delivery.server

# 终端 2 — 启动 Vue 前端开发服务器（端口 5173，自动代理 API 到后端）
cd frontend
pnpm dev
```

浏览器访问 **http://localhost:5173**

> 前端开发服务器支持热更新（HMR），修改 Vue 文件后页面自动刷新。

#### 方式 B：生产模式（单进程启动）

先构建前端，再用后端统一托管：

```bash
# 构建 Vue 前端（产物输出到 delivery/static/）
cd frontend
pnpm build
cd ..

# 单命令启动（FastAPI 同时托管前端静态文件）
.venv\Scripts\python -m delivery.server
```

浏览器访问 **http://localhost:8000**

### 4. 启动调度器（可选）

调度器是独立进程，负责定时抓取新闻和生成日报：

```bash
# 新开一个终端
python -m scheduler.scheduler
```

### 5. CLI 调试工具

```bash
python -m delivery.cli pipeline        # 手动执行 Pipeline
python -m delivery.cli brief           # 手动生成日报
python -m delivery.cli ask "今天有什么重要新闻？"
python -m delivery.cli stats           # 查看数据库统计
python -m delivery.cli cleanup         # 手动清理旧文章
```

## 前端功能

| 页面 | 说明 |
|---|---|
| 📰 新闻展示 | 浏览抓取的新闻，按来源/语言标签筛选，点击查看全文 |
| 📋 新闻简报 | 查看 AI 生成的每日新闻简报，支持一键生成 |
| 💬 智能问答 | 基于新闻库的 RAG 流式问答 |
| ⚙️ 功能设置 | RSS 来源管理、调度参数、数据统计 |
| 🔧 API 配置 | 编辑 .env 配置，切换 LLM 提供商和 API Key |

## 项目结构

```
Logos/
├── models/          # 领域模型层（纯数据定义）
├── core/            # 横切关注点（配置、Protocol、异常、日志）
├── infrastructure/  # 基础设施层（可替换实现）
├── services/        # 应用服务层（业务编排）
├── delivery/        # 表现层
│   ├── api/         #   FastAPI REST API 路由
│   ├── server.py    #   FastAPI 服务入口
│   ├── static/      #   Vue 构建产物（pnpm build 生成）
│   ├── cli.py       #   CLI 调试工具
│   └── streamlit_app.py  # Streamlit UI（旧，保留兼容）
├── frontend/        # Vue 3 前端源码
│   ├── src/
│   │   ├── views/   #   页面组件
│   │   ├── components/  # 通用组件
│   │   ├── api/     #   API 封装
│   │   └── router/  #   路由配置
│   ├── package.json
│   └── vite.config.js
├── scheduler/       # 调度层（独立进程）
├── tests/           # 测试
├── data/            # 运行时数据（自动创建，已 gitignore）
└── output/          # 日报输出
```

## 技术栈

- **后端**: Python 3.11+ / FastAPI / Uvicorn
- **前端**: Vue 3 + Vite + Vue Router
- **AI**: OpenAI / Gemini / Claude 多后端
- **存储**: SQLite + ChromaDB
- **调度**: APScheduler
- **包管理**: pnpm（前端）/ pip（后端）
