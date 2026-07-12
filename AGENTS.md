# AGENTS.md — AI 编码助手上下文

本文件为 AI 编码助手提供 InsightForge 项目的快速上下文入口。

---

## 项目简介

InsightForge 是一个**AI 驱动的竞品分析助手**（Python 3.11+ 后端 + Vue 3 前端），聚焦 AI 编程工具赛道（Cursor、TRAE、Windsurf），核心功能：
- 情报采集 Pipeline：RSS/网页爬取 → Markdown → SourceDocument 入库 → 父子分块 + 向量化 → 结构化事实抽取 → fact 级竞品关联
- 竞品管理：竞品档案 CRUD + 产品线管理 + 情报自动关联 + 多竞品对比
- ReAct Agent 分析：自主推理 + 工具调用（情报检索、竞品查询、对比分析、报告生成、Web 搜索）
- 分析报告：AI 生成结构化竞品分析报告，含溯源引用和审计链路
- 深度研究：多步研究任务，自动保存报告
- Webhook 推送：飞书/钉钉/企业微信/Telegram/ntfy
- RAGAs 评估：三维度自动化评估（检索质量 / 端到端问答 / Agent 工具调用）

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Vite 6 + Vue Router + Axios |
| 后端 | FastAPI + Uvicorn |
| 存储 | PostgreSQL 16 (文档元数据+父chunk+全文索引+point状态+竞品+报告) + Qdrant (子chunk向量+正文payload) |
| 任务 | Celery + Redis (Beat定时 + Worker异步) |
| LLM | openai / google-genai / anthropic SDK (4种后端) |
| 检索 | 向量+关键词 RRF 混合检索 + 可选 Rerank |
| 搜索 | DuckDuckGo + Tavily + NewsAPI (多引擎并发) |
| 评估 | RAGAs + LLM-as-Judge (三维度 RAG 质量评估) |
| 日志 | structlog (结构化JSON) |
| 容器 | Docker Compose (PostgreSQL + Redis + Qdrant) |

## 架构约定

1. **Protocol 优先**：`core/protocols.py` 定义基础设施接口（含 `DocumentStoreProtocol`、`VectorIndexProtocol`、`CompetitorStoreProtocol`、`ReportStoreProtocol`），`infrastructure/` 实现，`services/` 通过 Protocol 调用
2. **工厂模式**：`core/factory.py` 创建基础设施 + Service 层实例，`ConfigManager` 单例缓存 + 热重载
3. **严格分层**：Delivery → Agent → Services → Infrastructure，单向依赖
4. **Models 纯数据**：`models/` 目录下全部是 dataclass，无 I/O 依赖

## 关键文件

| 文件 | 作用 |
|---|---|
| `core/protocols.py` | Protocol 接口定义 |
| `core/factory.py` | 基础设施与 Service 工厂函数 |
| `core/config.py` | AppConfig (pydantic-settings) |
| `core/config_manager.py` | ConfigManager 热重载单例 |
| `delivery/server.py` | FastAPI 入口，组件初始化 |
| `agent/react/agent.py` | ReActAgent 核心循环 |
| `agent/tools/registry.py` | ToolRegistry 线程安全单例 |
| `services/pipeline_service.py` | Pipeline 编排（文档入库、分块向量化、事实抽取、fact 关联） |
| `services/intel_service.py` | 结构化事实抽取、fact CRUD、证据绑定 |
| `services/insight_service.py` | claim 创建、查询、证据规则校验 |
| `services/competitor_service.py` | 竞品管理 + fact 聚合/归因 |
| `services/service_registry.py` | Agent 工具可解析的 service 白名单 |
| `models/competitor.py` | 竞品 + 产品线域模型 |
| `models/report.py` | 分析报告域模型 |
| `infrastructure/competitor_store.py` | 竞品数据存储实现 |
| `infrastructure/report_store.py` | 报告数据存储实现 |
| `infrastructure/intel_store.py` | 结构化事实、fact 关联、证据引用存储 |
| `infrastructure/insight_store.py` | 分析 claim 存储 |
| `evals/runner.py` | RAGAs 评估编排器 |

## Agent 工具清单 (14 个)

| 工具 | 用途 |
|---|---|
| `search_evidence` | 带过滤下推的原文 evidence 检索 |
| `query_intel_facts` | 查询结构化 facts |
| `get_intel_fact` | 获取 fact 详情与 evidence refs |
| `create_intel_fact` | 创建 draft fact |
| `update_intel_fact` | 更新非 active fact |
| `link_fact_to_competitor` | 维护 fact 级竞品归因 |
| `link_fact_to_product` | 维护 fact 级产品归因 |
| `create_insight_claim` | 创建 draft claim |
| `query_insight_claims` | 查询分析 claims |
| `web_search` | 多引擎搜索 (DDG+Tavily+NewsAPI) |
| `list_competitors` | 列出竞品 |
| `get_competitor_profile` | 竞品档案、产品线与 fact 聚合 |
| `compare_competitors` | 基于 facts/events 横向对比 |
| `generate_analysis_report` | 生成竞品分析报告 |

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
python -m delivery.cli ask "Cursor 和 Windsurf 有什么区别？"
```

## 文档导航

| 文档 | 内容 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架构全景 |
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

## Agent skills

### Issue tracker

Issues are tracked as local Markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The default five canonical triage labels are used. See `docs/agents/triage-labels.md`.

### Domain docs

This repository uses a single-context domain documentation layout. See `docs/agents/domain.md`.
