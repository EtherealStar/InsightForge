# InsightForge — AI 竞品分析助手

一个运行在本地的 AI 竞品分析助手，具备以下核心能力：

1. **情报 Pipeline**：自动从 RSS/网页抓取内容，Markdown 转换、文档入库、父子分块、Qdrant 向量化，并抽取结构化竞品事实与证据。
2. **ReAct Agent 问答**：自然语言提问，Agent 调用混合检索、竞品查询、报告生成和 Web 搜索等工具。
3. **竞品与报告**：管理竞品档案、产品线、关联情报和结构化分析报告；报告生成后会绑定证据、运行质量门禁并进入审批发布流程。
4. **深度研究与推送**：多步研究模式自动保存报告，并可推送到飞书、钉钉、企业微信、Telegram、ntfy。

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

> 脚本会自动启动 Docker Compose 基础设施 + FastAPI 后端 + Celery Worker + Celery Beat + Vue 前端。

浏览器访问 **http://localhost:5173** （前端支持热更新 HMR，默认进入 `/dashboard` 工作台）

#### 方式 B：手动分布启动

```bash
# 启动基础设施 (PostgreSQL + Redis + Qdrant)
docker compose up -d

# 终端 1 — FastAPI 后端 (:8005)
python -m delivery.server

# 终端 2 — Vue 前端 (:5173)
cd frontend && pnpm dev

# 终端 3 — Celery Worker
celery -A scheduler.celery_app worker -l info -P threads

# 终端 4 — Celery Beat
celery -A scheduler.celery_app beat -l info

```

#### 方式 C：生产模式

```bash
cd frontend && pnpm build && cd ..
python -m delivery.server
# 生产环境下仍需独立启动 Celery Worker 和 Beat
```

浏览器访问 **http://localhost:8005**

#### 方式 D：VPS Docker Compose 一键部署

```bash
cp .env.deploy.example .env
# 编辑 .env：填写 CADDY_DOMAIN、BASIC_AUTH_USER、BASIC_AUTH_HASH、POSTGRES_PASSWORD、REDIS_PASSWORD、APP_ENV、AUTH_ENABLED 和各类 API Key
BASIC_AUTH_HASH=dummy docker compose --env-file .env.deploy.example -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml run --rm web python -m delivery.cli auth create-key --name initial-admin --role admin
```

生产编排会启动 PostgreSQL 16、带密码的 Redis、Qdrant、一次性数据库初始化、FastAPI、Celery Worker、Celery Beat 和 Caddy。公网只暴露 Caddy 的 80/443，站点默认启用 Basic Auth；后端 API 还会使用应用级 API Key 做 viewer/analyst/admin 角色授权，配置修改和报告发布会写审计。

详细步骤见 [docs/deployment/docker-vps.md](docs/deployment/docker-vps.md)。

### 4. CLI 调试工具

```bash
python -m delivery.cli pipeline        # 手动执行 Pipeline
python -m delivery.cli ask "Cursor 和 Windsurf 有什么区别？"
python -m delivery.cli auth create-key --name analyst --role analyst
```

## 前端功能

| 页面 | 说明 |
|---|---|
| Dashboard 工作台 | 竞品数量、7 日 facts、待处理报告、最近本地任务和系统健康总览 |
|  竞品管理 | 竞品档案、产品线、关联情报和自动关联 |
|  情报列表 | 浏览结构化 facts、状态、类型、维度和 evidence refs |
|  分析报告 | 查看结构化报告、质量门禁、证据和审计，按角色审批/发布 |
|  智能分析 | ReAct Agent 流式问答，推理过程可视化 |
|  记忆管理 | 核心记忆与持久记忆管理 |
|  Webhook | 推送渠道管理、测试、自动推送 |
|  功能设置 | RSS/爬虫源管理、调度参数配置 |
|  API 配置 | LLM/Embedding/Rerank/Judge/搜索引擎配置和配置审计（admin） |

## 项目结构

```
Logos/
├── core/            # 横切关注点（配置、Protocol、异常、日志）
├── models/          # 领域模型层（纯数据定义）
├── infrastructure/  # 基础设施层（可替换实现）
├── services/        # 应用服务层（业务编排）
├── agent/           # Agent 智能体层（ReAct + 工具系统）
├── delivery/        # 表现层
│   ├── api/         #   FastAPI REST API (11 个路由模块)
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
- **存储**: PostgreSQL 16（文档元数据、父块、全文索引、point 状态）+ Qdrant（子块向量、正文 payload、检索 metadata）
- **检索**: Qdrant 子块语义检索 + PostgreSQL 父块全文搜索 + RRF + jieba 中文分词
- **任务**: Celery + Redis (分布式异步 + Beat 定时)
- **日志**: structlog (结构化 JSON)
- **容器**: Docker Compose (VPS 生产编排 + 本地基础设施)
- **包管理**: pnpm（前端）/ pip（后端）

## 文档

- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构全景
- [docs/deployment/docker-vps.md](docs/deployment/docker-vps.md) — VPS Docker Compose 部署
- [AGENTS.md](AGENTS.md) — AI 编码助手上下文
- [docs/](docs/) — 详细文档目录
