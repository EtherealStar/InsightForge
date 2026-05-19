# News/Brief 到 Intel/Report 命名迁移清单

> **状态**：Phase 0 基线清单
> **建立日期**：2026-05-23
> **范围**：只定义命名迁移策略，不在 Phase 0 修改数据库、API 路径或代码行为。

---

## 1. 迁移目标

InsightForge 已从新闻助手演进为竞品情报工作台，但代码和接口仍保留 `news`、`brief` 等历史命名。Phase 0 的目标是先统一文档和领域语言，明确兼容边界，为后续结构化情报 Schema 和报告质量门禁做准备。

目标术语：

| 旧命名 | 目标命名 | 说明 |
|---|---|---|
| News | Intel / Intel Article | 面向竞品分析的情报来源；新 RAG 权威层由 `source_documents` 承载，`articles` 只保留新闻列表和旧 UI/API 入口 |
| News Source | Source / Source Profile | 来源配置，后续可扩展来源可靠度、抓取策略、限速 |
| Brief | Report / Market Brief | 简报是报告的一种轻量输出，后续与结构化 `AnalysisReport` 对齐 |
| Summary | Intel Summary / Extraction | 摘要阶段后续升级为结构化情报抽取 |
| Pipeline | Intel Pipeline | 采集、标准化、去重、摘要、竞品关联、分块、向量化 |

---

## 2. 当前兼容边界

Phase 0 不重命名现有 API 路径、表名、类名和前端文件名，以避免破坏现有调用方。

| 层 | 当前保留 | Phase 0 处理 |
|---|---|---|
| API | `/api/news`、`/api/briefs` | 文档标注为情报/报告语义，继续兼容旧路径 |
| 数据库 | `source_documents`、`document_parent_chunks`、`document_vector_points` | 明确 PostgreSQL 保存文档和父块权威内容，Qdrant 保存子块向量和 payload |
| 前端 | `NewsView.vue`、`BriefView.vue` | 页面文案按情报/报告理解，组件名暂不改 |
| 领域模型 | `ArticleEntity`、`DailyBrief` | 后续新增 `IntelItem`、`InsightClaim` 后再逐步迁移 |
| 异常层次 | `NewsAssistantError` | 暂保留，后续统一异常基类时单独处理 |

---

## 3. 后续迁移建议

### Phase 1 前

- 文档统一使用“情报文章”描述 `articles`，避免新增“新闻助手”表述。
- 新增功能优先使用 `intel`、`report`、`source` 术语。
- 新增 API 如无兼容包袱，优先采用 `/api/intel/*`、`/api/reports/*`。

### Phase 2 结构化情报 Schema

- 新增 `IntelItem` 作为结构化情报实体，优先引用 `source_documents` 和 `document_parent_chunks` 作为证据来源。
- 将 `intel_competitors`、`intel_products` 定义为 `IntelItem` 或 `Article` 到竞品主数据的关联索引。
- 将摘要 Prompt/规则版本显式记录为 extraction version。

### Phase 3+ 报告体系

- 将文件型 brief 输出收敛为 `AnalysisReport` 的一种 `report_type`。
- 报告内容引用统一走 `SourceRef` / `EvidenceRef`。
- 前端可保留“分析报告”入口，但内部区分市场简报、竞品对比、专题研究等类型。

---

## 4. 不在 Phase 0 执行的事项

- 不新增 `IntelItem`、`EvidenceRef`、`InsightClaim` 模型。
- 不新增数据库迁移。
- 不重命名现有路由、Python 模块、Vue 组件或测试文件。
- 不修改 Pipeline、Agent、Celery 任务行为。
- 不引入 Redis 状态层、任务历史或质量门禁。
