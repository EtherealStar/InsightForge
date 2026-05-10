# Logos — 个人 AI 新闻分析助手

一个运行在本地的个人 AI 新闻分析助手，具备以下核心能力：

1. **定时 Pipeline**：自动从多个新闻来源（RSS + 网页爬取）抓取内容，Markdown 转换、AI 摘要、父子分块向量化后存储，定时生成新闻简报。
2. **ReAct Agent 问答**：自然语言提问，Agent 自主推理并调用工具（混合检索、统计查询、Web 搜索等），基于真实数据生成回答。
3. **深度研究**：多步研究模式，自动保存研究报告。
4. **Webhook 推送**：将简报/报告推送到飞书、钉钉、企业微信、Telegram、ntfy 等平台。

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
# 编辑 .env 填入 API Key 和端点配置
```

### 2. 安装前端依赖

```bash
cd frontend
pnpm install
cd ..
```

### 3. 启动方式

#### 方式 A：一键启动（推荐 Windows 开发环境）

```bash
start_dev.bat
```

> 脚本会自动启动 Docker Compose 基础设施 + FastAPI 后端 + Celery Worker + Celery Beat + Flower 监控 + Vue 前端，共 6 个服务。

浏览器访问 **http://localhost:5173** （前端支持热更新 HMR）

#### 方式 B：手动分布启动

```bash
# 启动基础设施 (PostgreSQL + pgvector + Redis)
docker compose up -d

# 终端 1 — FastAPI 后端 (:8005)
python -m delivery.server

# 终端 2 — Vue 前端 (:5173)
cd frontend && pnpm dev

# 终端 3 — Celery Worker
celery -A scheduler.celery_app worker -l info -P threads

# 终端 4 — Celery Beat
celery -A scheduler.celery_app beat -l info

# 终端 5 (可选) — Flower 监控 (http://localhost:5555)
celery -A scheduler.celery_app flower --port=5555
```

#### 方式 C：生产模式

```bash
cd frontend && pnpm build && cd ..
python -m delivery.server
# 生产环境下仍需独立启动 Celery Worker 和 Beat
```

浏览器访问 **http://localhost:8005**

### 4. CLI 调试工具

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
| 📰 新闻展示 | 浏览抓取的新闻，按来源/语言筛选，点击查看全文 |
| 📋 新闻简报 | 查看 AI 生成的新闻简报，支持一键生成 |
| 💬 智能问答 | ReAct Agent 流式问答，推理过程可视化 |
| 🔍 在线搜索 | NewsAPI 全球新闻搜索 + 热门头条 |
| 📤 Webhook | 推送渠道管理、测试、自动推送 |
| ⚙️ 功能设置 | RSS/爬虫源管理、调度参数配置 |
| 🔧 API 配置 | LLM/Embedding/Rerank/搜索引擎配置 |

## 项目结构

```
Logos/
├── core/            # 横切关注点（配置、Protocol、异常、日志）
├── models/          # 领域模型层（纯数据定义）
├── infrastructure/  # 基础设施层（可替换实现）
├── services/        # 应用服务层（业务编排）
├── agent/           # Agent 智能体层（ReAct + 工具系统）
├── delivery/        # 表现层
│   ├── api/         #   FastAPI REST API (9 个路由模块)
│   ├── server.py    #   FastAPI 服务入口
│   └── cli.py       #   CLI 调试工具
├── scheduler/       # 调度层 (Celery + Redis)
├── frontend/        # Vue 3 前端源码
├── docs/            # 项目文档
├── tests/           # 测试
├── data/            # 运行时数据（自动创建，已 gitignore）
└── output/          # 日报 + 研究报告输出
```

## 技术栈

- **后端**: Python 3.11+ / FastAPI / Uvicorn
- **前端**: Vue 3 + Vite 6 + Vue Router + Axios
- **AI**: OpenAI / Gemini / Claude 多后端 + Embedding + 可选 Rerank
- **存储**: PostgreSQL 16 + pgvector (文章+父chunk+子chunk向量+全文索引)
- **检索**: 向量+关键词 RRF 混合检索 + jieba 中文分词
- **任务**: Celery + Redis (分布式异步 + Beat 定时)
- **日志**: structlog (结构化 JSON)
- **容器**: Docker Compose (PostgreSQL/pgvector + Redis)
- **包管理**: pnpm（前端）/ pip（后端）

## 文档

- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构全景
- [AGENTS.md](AGENTS.md) — AI 编码助手上下文
- [docs/](docs/) — 详细文档目录
