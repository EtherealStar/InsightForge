# AGENTS.md — AI 编码助手上下文

本文件为 AI 编码助手提供 Logos 项目的快速上下文入口。

---

## 项目简介

Logos 是一个**个人 AI 新闻分析助手**（Python 3.11+ 后端 + Vue 3 前端），核心功能：
- 定时 Pipeline：RSS/网页爬取 → Markdown → 去重存储 → AI 摘要 → 父子分块 + 向量化
- ReAct Agent 问答：自主推理 + 工具调用（混合检索、Web 搜索、统计等）
- 深度研究：多步研究任务，自动保存报告
- Webhook 推送：飞书/钉钉/企业微信/Telegram/ntfy

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Vite 6 + Vue Router + Axios |
| 后端 | FastAPI + Uvicorn |
| 存储 | PostgreSQL 16 + pgvector (文章+父chunk+子chunk向量) |
| 任务 | Celery + Redis (Beat定时 + Worker异步) |
| LLM | openai / google-genai / anthropic SDK (4种后端) |
| 检索 | 向量+关键词 RRF 混合检索 + 可选 Rerank |
| 日志 | structlog (结构化JSON) |
| 容器 | Docker Compose (PostgreSQL/pgvector + Redis) |

## 架构约定

1. **Protocol 优先**：`core/protocols.py` 定义 5 个接口，`infrastructure/` 实现，`services/` 通过 Protocol 调用
2. **工厂模式**：`core/factory.py` 创建组件实例，`ConfigManager` 单例缓存 + 热重载
3. **严格分层**：Delivery → Agent → Services → Infrastructure，单向依赖
4. **Models 纯数据**：`models/` 目录下全部是 dataclass，无 I/O 依赖

## 关键文件

| 文件 | 作用 |
|---|---|
| `core/protocols.py` | 5 个 Protocol 接口定义 |
| `core/factory.py` | 8 个工厂函数 |
| `core/config.py` | AppConfig (pydantic-settings) |
| `core/config_manager.py` | ConfigManager 热重载单例 |
| `delivery/server.py` | FastAPI 入口，组件初始化 |
| `agent/react/agent.py` | ReActAgent 核心循环 |
| `agent/tools/registry.py` | ToolRegistry 线程安全单例 |
| `services/pipeline_service.py` | Pipeline 编排 |

## 开发命令

```bash
# 启动基础设施
docker compose up -d

# 一键启动 (Windows)
start_dev.bat

# 或手动启动
python -m delivery.server                                   # 后端 :8005
cd frontend && pnpm dev                                     # 前端 :5173
celery -A scheduler.celery_app worker -l info -P threads    # Worker
celery -A scheduler.celery_app beat -l info                 # Beat

# 测试
pytest tests/

# CLI
python -m delivery.cli pipeline
python -m delivery.cli ask "今天有什么重要新闻？"
```

## 文档导航

| 文档 | 内容 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架构全景（~400行精简版） |
| [docs/DESIGN.md](docs/DESIGN.md) | 设计哲学 |
| [docs/PLANS.md](docs/PLANS.md) | 开发路线图 |
| [docs/design-docs/](docs/design-docs/index.md) | 详细设计（选型论证、Protocol、Agent） |
| [docs/generated/dbdoc/](docs/generated/dbdoc/) | 数据库 Schema (tbls 自动生成) |
| [docs/generated/db-schema.md](docs/generated/db-schema.md) | 数据库业务规则补充 |
| [docs/product-specs/api-reference.md](docs/product-specs/api-reference.md) | API 路由参考 |
| [docs/references/external-deps.md](docs/references/external-deps.md) | 外部依赖配置 |
| [docs/exec-plans/tech-debt-tracker.md](docs/exec-plans/tech-debt-tracker.md) | 技术债务清单 |

## 编码规范

- 新增基础设施组件必须实现对应 Protocol
- 新增工具继承 `BaseTool`，通过 `@register_tool` 或 `register_builtin_tools()` 注册
- 异常继承 `NewsAssistantError` 层次
- 外部调用加 `@with_retry` 装饰器
- 使用 `structlog.get_logger()` 获取 logger
