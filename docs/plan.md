# 开发路线图

---

## 当前状态

项目处于 **Demo+** 阶段：前后端分离架构 + ReAct Agent + 深度研究 + Web 搜索 + AI 摘要 + Rerank + 混合检索 RAG + 结构化事实层 API + Webhook 推送。

核心基础设施已完成 Phase 1 全量重构、Scheduler 验证接入、Phase 2 结构化事实层和 Phase 3 报告治理、安全与生产部署闭环验收：PostgreSQL 16 保存权威文档、父块、全文索引、Qdrant point 状态、异步任务历史、结构化事实、证据引用、claim、报告 claim/evidence 关系、质量审查结果、配置审计和 API Key 哈希；Qdrant 保存子块向量和 payload；Redis/Celery 负责异步执行、热状态和锁保护；后端已提供 facts/claims、竞品 facts/timeline、报告质量/审批 API、应用级 RBAC、配置审计和 VPS Docker Compose 生产部署入口。

## 待推进事项

详见 [技术债务追踪器](exec-plans/tech-debt-tracker.md) 获取当前已知问题列表。

### 企业级竞品分析改造

| 文档 | 说明 |
|---|---|
| [enterprise-ai-competitor-analysis-plan.md](exec-plans/enterprise-ai-competitor-analysis-plan.md) | 面向企业级 AI 竞品分析助手的现状分析、Redis 应用场景、目标架构和分阶段升级计划 |
| [phase-2-intel-fact-service-refactor-plan.md](exec-plans/completed/phase-2-intel-fact-service-refactor-plan.md) | Phase 2 结构化情报事实、证据、claim、服务层和 Agent 原子工具重构计划 |
| [phase-3-enterprise-report-quality-security-plan.md](exec-plans/completed/phase-3-enterprise-report-quality-security-plan.md) | Phase 3 企业级报告生成、质量门禁、安全、配置与生产部署增强计划 |
| [phase-4-frontend-workbench-upgrade-plan.md](exec-plans/phase-4-frontend-workbench-upgrade-plan.md) | Phase 4 前端工作台升级重构计划，覆盖 Dashboard、Intel、Reports、Tasks 和 SVG-only 图标规范 |
| [news-brief-to-intel-report-migration.md](exec-plans/news-brief-to-intel-report-migration.md) | Phase 0 命名迁移基线：News/Brief 到 Intel/Report 的兼容边界和后续迁移策略 |
| [source-governance-and-deduplication-implementation-plan.md](exec-plans/source-governance-and-deduplication-implementation-plan.md) | 来源分级、SimHash + shingle 两阶段去重、主来源晋升、全局 fact、多证据验证与治理工作台实施计划 |

### 近期优先

| 事项 | 说明 | 优先级 |
|---|---|---|
| Phase 4 前端工作台体验验收 | Dashboard、Intel、Reports、Tasks、Settings 的浏览器端验收 | P1 |
| 生产环境试点演练 | 使用真实 VPS、真实 API Key 和备份恢复流程做一轮试运行 | P2 |

### 远期规划

| 事项 | 说明 | 优先级 |
|---|---|---|
| Telegram Bot 集成 | 平台机器人检索+回答 | P3 |
| 可编辑提示词 | 世界书化分析模板 | P3 |
| 多 Agent 分析 | 多 Agent 协作生成概要 | P3 |

### 已完成

| 事项 | 说明 |
|---|---|
| Phase 1 基础设施全量重构 | 移除旧 PostgreSQL 向量路径，新增 DocumentStoreProtocol、VectorIndexProtocol、PostgresDocumentStore、QdrantVectorIndex 和新 foundation schema；旧任务监控面板和 Windows 包管理器入口不属于当前运行底座 |
| Phase 2 服务层、事实抽取 Pipeline、Agent 工具与 API 重构 | 新增 `IntelService`、`InsightService`、轻量 `ReportService` 和 `ServiceRegistry`；full pipeline 在分块向量化后执行 `extract_intel_facts` 与 `link_facts`；Agent 内置工具改为 ToolSpec 注册表 + BuiltinToolFactory 创建，active 工具固定为 `search_evidence` 等 14 个 Phase 2 工具，旧 news/article/brief 工具定义已删除；后端提供 `/api/intel/facts`、`/api/insights/claims` 和竞品 facts/timeline API |
| Phase 3 报告治理、安全与生产部署闭环 | 报告生成统一走 `ReportService` + `ReportQualityService`，无证据/无效引用/Judge 失败不得发布；admin 审批发布、viewer/analyst/admin RBAC、配置脱敏审计、生产 Compose、Redis 密码、健康检查和部署文档已纳入整体测试与验收 |
| Scheduler 任务审计接入 | Pipeline 和上传批次摄入写入 `task_runs/task_stages/task_events`，`/api/tasks/{task_id}` 返回 PostgreSQL 历史与 Celery 状态 |
| Pipeline 前端异步轮询 | `/api/intel/pipeline` 返回 `task_id` 后由前端轮询 `/api/tasks/{task_id}` |
| 抓取流程改进 | RSS 源 ThreadPoolExecutor 并发抓取、Celery 任务自动重试、爬虫 per-site `max_pages` 参数化 |
| RAGAs 评估框架 | 三维度评估（检索+问答+Agent），`evals/` 模块 + CLI + 合成测试集生成 |
| VPS Docker Compose 部署 | 应用镜像 + Web/Worker/Beat/Migrate/Caddy 编排，见 `docs/deployment/docker-vps.md` |

---

## 已完成方案归档

以下文档为历史执行计划，记录了项目从原型到当前架构的演进路径：

| 文档 | 说明 |
|---|---|
| [demo-design.md](exec-plans/completed/demo-design.md) | Demo 原型方案（Streamlit + SQLite + ChromaDB，这些旧技术已废弃） |
| [full-design.md](exec-plans/completed/full-design.md) | 完整方案 v2（历史架构规划，仅作演进记录，不作为当前实现依据） |
| [target-architecture.md](exec-plans/completed/target-architecture.md) | 目标架构文档（大部分已实现） |

---

## 原始需求

> 以下内容来自项目初期的 `Development Plan.md`，记录了最初的功能需求设想。

**总流程**：抓取 → 存储 → 分析(可跳过) → 推送

### 抓取需求
- 抓取网页新闻 (Crawlee)  已实现
- 抓取 RSS 新闻  已实现
- 抓取 API 新闻  已实现 (NewsAPI)
- 搜索新闻 (AI 调用)  已实现 (Web Search)

### 存储需求
- 存储抓取后的新闻  已实现
- 根据不同来源分类，有 HTML 的可以保存为 HTML  已实现
- 向量化和 rerank  已实现
- 结构化事实抽取与 API 链路  已实现 (IntelService + StructuredExtractionClient + facts/claims API)
- 旧新闻摘要、旧 Brief、旧 ArticleStore 运行入口已删除；结构化抽取使用 `structured_extraction_*` 配置。
- 记忆系统实现

### 分析需求
- 调用 AI 分析  已实现 (ReAct Agent)
- 接入其他平台机器人 ⏳ 部分实现 (Webhook)
- Deep Search 深度研究与报告  已实现

### 推送需求
- 全平台 webhook 推送  已实现
- ntfy  已实现

### 安全需求
- 远程访问登录界面，密钥
- API KEY隐藏识别
