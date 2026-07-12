# API 路由参考

Phase 2 已硬切到结构化情报模型。旧 `/api/news/*`、`/api/briefs/*`、`/api/newsapi/*` 和 `/api/competitors/{id}/intel` 不再注册；采集入口、报告入口和前端页面均使用 `intel/facts/evidence/claims/reports` 语义。

> 本文记录当前已实现路由。ADR-0002 接受的三层目标模型将移除业务 score、claim 直连 evidence、JSON ID 数组和旧分类字段，并新增 fact-evidence / claim-fact 关系语义；目标 API 尚未实施，设计见 [structured-intelligence-model.md](structured-intelligence-model.md)。

## API 路由一览

### 健康检查

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/health` | 免认证健康检查，返回 redacted component readiness |

### 认证

生产环境 API 使用应用级 API Key。请求头优先使用 `Authorization: Bearer <api_key>`，兼容 `X-API-Key`。未认证返回 401，角色不足返回 403。

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/auth/me` | 返回当前 actor、role 和 api_key_id |

### 结构化情报

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/api/intel/pipeline` | 手动触发情报采集 Pipeline，异步返回 `task_id` |
| GET | `/api/intel/facts` | 按类型、维度、状态、来源文档、竞品、产品、日期和关键词查询 facts |
| POST | `/api/intel/facts` | 创建 draft fact；API 不允许直接创建 active fact |
| GET | `/api/intel/facts/{fact_id}` | 获取单条 fact 详情、证据引用和竞品/产品归因 |
| PUT | `/api/intel/facts/{fact_id}` | 更新非 active fact；API 不允许直接激活 |
| PATCH | `/api/intel/facts/{fact_id}/status` | 更新状态，仅允许 `draft/rejected/archived` |
| POST | `/api/intel/facts/{fact_id}/competitors` | 将 fact 关联到竞品 |
| POST | `/api/intel/facts/{fact_id}/products` | 将 fact 关联到产品线 |
| GET | `/api/intel/facts/{fact_id}/evidence` | 获取 fact evidence refs |
| POST | `/api/intel/facts/{fact_id}/evidence` | 追加 fact evidence ref |

### 分析 Claims

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/insights/claims` | 按 claim 类型、维度、状态、竞品和 fact 查询 claims |
| POST | `/api/insights/claims` | 创建 draft claim；`fact_ids` 由 `InsightService` 校验 |
| GET | `/api/insights/claims/{claim_id}` | 获取单条 claim 详情和 evidence refs |
| PUT | `/api/insights/claims/{claim_id}` | 更新非 active claim；API 不允许直接激活 |
| POST | `/api/insights/claims/{claim_id}/validate` | 按 Phase 2 evidence 规则校验 claim |

### 竞品管理

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/competitors` | 列出竞品（默认 `active` 状态） |
| POST | `/api/competitors` | 创建竞品档案 |
| GET | `/api/competitors/{competitor_id}` | 获取竞品详情、产品线和 fact 统计 |
| PUT | `/api/competitors/{competitor_id}` | 更新竞品档案 |
| DELETE | `/api/competitors/{competitor_id}` | 删除竞品 |
| GET | `/api/competitors/{competitor_id}/products` | 获取竞品产品线 |
| POST | `/api/competitors/{competitor_id}/products` | 添加竞品产品线 |
| DELETE | `/api/competitors/products/{product_id}` | 删除产品线 |
| GET | `/api/competitors/{competitor_id}/facts` | 获取竞品结构化 facts 和聚合 |
| GET | `/api/competitors/{competitor_id}/timeline` | 获取竞品事件时间线 |
| POST | `/api/competitors/compare/facts` | 调用 `CompetitorService.compare_competitor_facts()` 进行 fact 对比 |
| POST | `/api/competitors/auto-link` | 自动将已有 facts 关联到匹配竞品 |

### 分析报告

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/reports` | 获取结构化分析报告列表（支持 `report_type`、`status`、分页；返回 `review_status`、`quality_score`、`quality_summary`） |
| POST | `/api/reports/generate` | 通过 `ReportService.generate_analysis_report()` 生成草稿、绑定 evidence、运行质量门禁并返回结构化状态 |
| GET | `/api/reports/{report_id}` | 获取报告详情、正文、来源引用、report claims、report evidence、质量摘要、审批发布时间和审计摘要 |
| GET | `/api/reports/{report_id}/quality` | 获取报告质量审查列表和结构化 issues |
| POST | `/api/reports/{report_id}/quality/review` | 重新运行报告质量门禁并追加 quality review |
| GET | `/api/reports/{report_id}/audit` | 获取报告完整审计链路 |
| POST | `/api/reports/{report_id}/approve` | admin 审批通过 `waiting_review + passed` 报告 |
| POST | `/api/reports/{report_id}/reject` | admin 退回 `waiting_review` 报告到修订状态 |
| POST | `/api/reports/{report_id}/publish` | admin 发布 `approved + passed` 报告 |
| DELETE | `/api/reports/{report_id}` | 删除结构化分析报告 |

`POST /api/reports/generate` 成功时返回 `report_id`、`status`、`review_status`、`quality_score`、`quality_summary`、`blocking_issues_count`、`content` 和 `issues`。默认不会发布报告：质量失败进入 `revision_required/failed`，质量通过进入 `waiting_review/passed`，Judge 不可用但规则通过时进入 `waiting_review/needs_human`。`auto_publish=true` 不能绕过服务端质量门禁，且只有服务端 `REPORT_QUALITY_AUTO_PUBLISH=true` 时才可能生效。

报告状态机由 `ReportService` 维护，Delivery 层不得直接写状态：

```text
draft -> quality_reviewing -> revision_required/waiting_review -> approved -> published
                         \-> rejected
published -> archived
```

无证据关键结论、无效 citation、Judge JSON 解析失败或低于阈值的报告不得进入 `approved` 或 `published`。

### 异步任务

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/tasks` | 获取任务历史列表，支持 `task_type`、`status`、`date_from/date_to`、`actor`、`limit/offset` |
| GET | `/api/tasks/{task_id}` | 轮询查询异步任务状态、PostgreSQL run/stages/events 和 Celery 状态 |

`POST /api/intel/pipeline` 返回的 `task_id` 同时是 `task_runs.id` 和 Celery task id。前端 `/tasks?task_id=...` 使用 `GET /api/tasks/{task_id}` 展示阶段和事件；Dashboard 优先使用 `GET /api/tasks` 展示最近任务，接口不可用时回退本地最近 task id。

### Agent 问答

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/query/sessions` | 获取普通问答会话列表 |
| GET | `/api/query/sessions/{session_id}` | 获取普通问答会话详情 |
| POST | `/api/query` | ReAct Agent 非流式问答 |
| POST | `/api/query/stream` | ReAct Agent SSE 流式问答 |

前端调用 `POST /api/query/stream` 和 `POST /api/research/sessions/{session_id}/execute/stream` 时必须和 Axios 请求一样携带 `Authorization: Bearer <api_key>`；后端同样按 analyst 权限校验。

### 记忆、研究、推送和配置

| 方法 | 路径 | 功能 |
|---|---|---|
| `/api/memory/*` | 记忆管理 | 核心记忆、持久记忆和 MEMORY 索引 |
| `/api/research/*` | 深度研究 | Plan Execute 会话和研究报告文件 |
| `/api/webhook/*` | Webhook 推送 | 渠道管理、测试、推送最新分析报告 |
| `/api/config/*` | 配置管理 | LLM、Embedding、Rerank、Web Search、结构化抽取、Judge、安全和质量配置；`GET /api/config/audit` 返回配置审计 |
| `/api/settings/*` | 功能设置 | RSS 源、爬虫源和采集调度 |

## 权限摘要

| 角色 | 可用范围 |
|---|---|
| `viewer` | 只读 facts、claims、competitors、reports、tasks、report quality/audit、Webhook/Settings 列表 |
| `analyst` | viewer + 报告生成/质检、Pipeline、draft facts/claims 写入、Agent/Research、竞品写入 |
| `admin` | analyst + 配置修改/审计、Webhook 管理/推送、报告审批/发布/删除、删除竞品/产品 |

敏感写操作必须在后端 dependency 校验角色；前端隐藏按钮只作为交互优化。配置读取和审计响应不得返回 secret 原文。

## 前端页面映射

| 路由 | 视图组件 | 功能 |
|---|---|---|
| `/dashboard` | `DashboardView.vue` | 工作台总览、KPI、待处理报告、最新 facts、最近本地任务和健康状态 |
| `/competitors` | `CompetitorView.vue` | 竞品档案、产品线、facts/timeline 和自动关联 |
| `/intel` | `IntelView.vue` | facts 浏览、筛选和 Pipeline 触发 |
| `/reports` | `ReportView.vue` | 分析报告列表、查看和生成 |
| `/tasks` | `TaskView.vue` | 任务历史、阶段进度、事件日志和失败诊断 |
| `/query` | `QueryView.vue` | ReAct Agent 问答 |
| `/memory` | `MemoryView.vue` | 核心记忆与持久记忆管理 |
| `/webhook` | `WebhookView.vue` | 推送渠道管理、测试和报告推送 |
| `/settings` | `SettingsView.vue` | RSS 源、爬虫源和采集调度 |
| `/config` | `ConfigView.vue` | LLM/Embedding/Rerank/Web Search/结构化抽取配置 |

## 开发模式通信

Vite 开发服务器只代理 `/api/*` 到 FastAPI。SPA 默认从 `/` 重定向到 `/dashboard`，页面路由使用 `/dashboard`、`/intel`、`/reports` 等路径；生产模式下构建产物位于 `delivery/static/`，由 FastAPI 托管。

## 前端 Query 参数

| 页面 | Query 参数 |
|---|---|
| `/reports` | `report_type`、`status`、`review_status`、`min_quality`、`updated_from`、`report_id` |
| `/intel` | `competitor_id`、`product_id`、`fact_type`、`dimension`、`status`、`keyword`、`date_from/date_to` |
| `/tasks` | `task_id`、`task_type`、`status`、`date_from/date_to` |
