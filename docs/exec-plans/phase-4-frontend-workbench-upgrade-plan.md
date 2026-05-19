# 第四阶段前端工作台升级重构计划

> **状态**：规划文档  
> **撰写日期**：2026-05-25  
> **依据文档**：`docs/exec-plans/enterprise-ai-competitor-analysis-plan.md`、`docs/exec-plans/completed/phase-3-enterprise-report-quality-security-plan.md`、`docs/product-specs/ui-design-spec.md`、`docs/design-docs/api-routes.md`、`ARCHITECTURE.md`  
> **阶段定位**：企业级 AI 竞品分析改造的第四阶段。原总计划中的 Phase 4 安全、配置与生产部署增强已经并入第三阶段报告治理闭环，因此本阶段承接原 Phase 5 的前端工作台升级，并按新的阶段编号落地。  
> **核心原则**：前端不是新闻助手皮肤替换，而是企业竞品情报工作台。页面必须围绕结构化事实、证据、任务、报告质量和审批工作流组织；前端代码和页面文案不得使用 emoji，所有图标只能使用 SVG。

---

## 1. 背景

Phase 1 已完成文档权威层、Qdrant 向量索引、Redis 执行期状态和任务历史。Phase 2 已完成 `IntelFact`、`EvidenceRef`、`InsightClaim`、竞品事实聚合、Agent 原子工具和 facts/claims API。Phase 3 已把报告生成推进到可审计、可质检、可审批的企业级产物，并补齐应用级认证、配置审计和生产部署基线。

当前前端已经从旧 `/news`、`/briefs` 迁移到 `/intel`、`/reports` 等竞品分析语义，也已经接入 API Key 登录、角色隐藏、报告质量摘要和配置审计的最小能力。但它仍然存在几类问题：

- 信息架构仍按单页功能堆叠，缺少企业工作台需要的总览、任务追踪、复核队列和证据侧栏。
- 竞品、情报、报告、任务之间的跳转关系弱，用户难以从报告结论回溯到 fact、evidence、source document 和 task。
- 报告质量、审批、审计和任务阶段没有形成统一工作流体验。
- 导航、logo、空状态等位置仍存在 emoji 图标，例如 `frontend/src/router/index.js` 和 `frontend/src/components/NavSidebar.vue`。
- `frontend/src/api/index.ts` 是 TypeScript，但项目没有完整 TypeScript 配置；短期应避免扩大类型改造范围，先把 API 调用封装整理成可维护边界。

第四阶段的目标是让前端成为日常使用入口：用户能从一个高密度工作台中完成采集触发、情报筛选、竞品复核、报告审批、质量追踪和配置检查。

---

## 2. 阶段目标

第四阶段完成后，系统应具备以下前端能力：

1. 首页从默认跳转竞品页升级为 Dashboard，展示竞品数量、本周 facts、待审报告、失败任务、来源健康和关键趋势。
2. Intel 页面从事实列表升级为可复核情报台，支持竞品、产品、类型、维度、状态、时间窗、重要度和关键词筛选。
3. Competitors 页面补齐竞品详情工作台，展示产品线、facts 聚合、事件时间线、维度覆盖和最近变化。
4. Reports 页面补齐报告工作流，支持列表筛选、详情阅读、证据侧栏、质量问题、审计时间线、重新质检、审批和发布。
5. 新增或强化 Tasks 页面，展示任务历史、阶段进度、失败原因、耗时、重试和关联产物。
6. Query / Research 页面与报告工作流连接，Agent 生成的报告能跳转到报告详情和质量结果。
7. Settings / Config / Webhook 页面按角色和环境提供清晰的只读、可编辑和危险操作状态。
8. 建立共享前端组件层，减少各视图重复实现筛选器、状态 badge、证据引用、质量 issue、任务阶段、确认弹窗和空状态。
9. 全前端移除 emoji；所有图标通过内联 SVG、SVG sprite 或本地 `.svg` 组件渲染。
10. 完成基础视觉和响应式验收，保证桌面高密度可扫读，移动端可完成关键查看和审批动作。

---

## 3. 明确非目标

本阶段不做以下事项：

- 不引入大型前端框架迁移，不从 Vue 3 迁移到 React、Nuxt 或其他技术栈。
- 不一次性改造为完整 TypeScript 项目；`api/index.ts` 可保持现状，类型化组件和 `tsconfig` 后置。
- 不新增复杂可视化库作为 P0 依赖；趋势图可以先用表格、轻量 SVG sparkline 或后端统计数据展示。
- 不把前端按钮隐藏作为权限边界；所有敏感写操作仍以 FastAPI role dependency 为准。
- 不在前端保存、显示或导出明文 API Key、Webhook URL、DSN、provider secret。
- 不提供任意 SQL、任意文件浏览或通用后台管理器。
- 不实现完整多租户 UI；仅在数据模型和筛选区预留 actor/tenant 扩展空间。

---

## 4. 设计原则

### 4.1 工作台优先

前端第一屏应服务日常工作，而不是营销式 landing page。Dashboard 必须直接呈现待处理事项、最新情报、质量风险和任务状态。

### 4.2 证据链可达

任何报告结论、claim、fact、竞品变化都应能向下追溯到 evidence snippet、URL、source document、parent chunk 和生成任务。前端不需要一次展示全部细节，但必须提供清晰的逐层展开路径。

### 4.3 状态清晰

报告状态、质量状态、任务状态、fact 状态、权限状态要使用稳定 badge 和动作规则，避免同一概念在不同页面出现不同文案。

### 4.4 高密度但不拥挤

面向企业分析工作，布局应偏向表格、列表、侧栏、筛选条和详情面板。卡片只用于重复对象或局部摘要，不把页面大段区域包成装饰性卡片。

### 4.5 SVG-only 图标规范

前端禁止使用 emoji 作为图标、状态标识、空状态装饰或按钮内容。允许使用：

| 形式 | 说明 |
|---|---|
| 内联 SVG Vue 组件 | 推荐，用于导航、按钮、状态、空状态 |
| 本地 `.svg` 文件 | 允许，用于 logo、品牌资产和较复杂图形 |
| SVG sprite | 允许，用于统一管理基础图标 |
| CSS data URI SVG | 允许，用于 select 箭头等纯样式图标 |

不允许使用：

| 形式 | 说明 |
|---|---|
| emoji 字符 | 包括导航、按钮、标题、空状态、toast、badge |
| icon font | 避免字体加载和可访问性问题 |
| 远程图标 CDN | 生产环境不可控 |
| PNG/JPG 图标 | 除非是竞品 logo 或用户上传图片；界面图标必须 SVG |

---

## 5. 信息架构

### 5.1 目标路由

| 路由 | 视图组件 | 定位 |
|---|---|---|
| `/dashboard` | `DashboardView.vue` | 运营总览、待办、质量风险、任务状态 |
| `/competitors` | `CompetitorView.vue` | 竞品主数据、产品线、facts 聚合、事件时间线 |
| `/intel` | `IntelView.vue` | 结构化事实浏览、筛选、复核、证据查看 |
| `/reports` | `ReportView.vue` | 报告列表、详情、质量、审批、发布 |
| `/tasks` | `TaskView.vue` | 任务历史、阶段进度、失败诊断、重试入口 |
| `/query` | `QueryView.vue` | ReAct Agent 分析与报告生成入口 |
| `/memory` | `MemoryView.vue` | 记忆管理，后续与研究上下文关联 |
| `/webhook` | `WebhookView.vue` | 推送渠道和报告推送 |
| `/settings` | `SettingsView.vue` | 来源、采集策略和调度设置 |
| `/config` | `ConfigView.vue` | provider、安全、质量和生产配置 |

`/` 应重定向到 `/dashboard`。如果 Dashboard API 尚未完成，可先用前端并发调用已有 reports、competitors、tasks、health API 聚合。

### 5.2 导航结构

导航建议分组：

| 分组 | 页面 | 最低角色 |
|---|---|---|
| 工作台 | Dashboard、Intel、Reports、Tasks | viewer |
| 分析 | Competitors、Query、Memory | viewer / analyst |
| 运营 | Webhook、Settings、Config | viewer / admin |

`NavSidebar.vue` 不再保存 emoji 字符串。建议保存 `icon: 'dashboard'` 这类符号名，由 `SvgIcon.vue` 渲染。

---

## 6. 页面重构计划

### 6.1 Dashboard

目标：企业用户进入系统后立即知道今天该处理什么。

P0 内容：

| 区域 | 内容 |
|---|---|
| KPI 条 | active competitors、7 日 facts、待审报告、失败任务、质量失败报告 |
| 待处理队列 | `revision_required`、`waiting_review`、任务失败、source 异常 |
| 最新情报 | 最近 facts/events，显示竞品、类型、维度、重要度、来源 |
| 任务状态 | 最近 task runs，显示阶段、耗时、失败摘要 |
| 快捷动作 | 运行 Pipeline、生成报告、进入 Intel 筛选、查看报告审批 |

P1 内容：

- 按竞品分组的 facts 趋势。
- 来源健康摘要。
- 报告质量通过率。
- LLM/Judge 配置状态摘要。

### 6.2 Intel

目标：从“事实列表”升级为“结构化情报复核台”。

P0 内容：

| 能力 | 说明 |
|---|---|
| 筛选条 | competitor、product、fact_type、dimension、status、date range、keyword |
| facts 表格 | fact_text、竞品、产品、类型、维度、置信度、重要度、状态、来源数量 |
| 详情抽屉 | fact 详情、evidence refs、source URL、parent chunk snippet、关联 claims |
| 复核动作 | draft fact 更新、reject、archive、补充 competitor/product 关联 |
| Pipeline 入口 | 触发后跳转或展开 task 状态 |

P1 内容：

- 时间线视图。
- 批量归因。
- 低置信度复核队列。
- 冲突 evidence 标记。

### 6.3 Competitors

目标：让竞品档案成为事实聚合入口，而不是静态 CRUD。

P0 内容：

| 区域 | 内容 |
|---|---|
| 竞品列表 | 名称、状态、产品线数量、facts 数、最近事实时间 |
| 详情头部 | 竞品描述、官网、核心标签、最近更新时间 |
| 产品线 | 产品 CRUD、产品关联 facts 数 |
| 事实聚合 | 按 dimension、fact_type、status 的统计 |
| 事件时间线 | 最近 events/facts，支持跳转 Intel 详情 |

P1 内容：

- 产品线对比矩阵。
- 多竞品 facts 对比结果展示。
- 维度覆盖缺口提示。

### 6.4 Reports

目标：把报告页升级为审批和质量工作台。

P0 内容：

| 能力 | 说明 |
|---|---|
| 报告列表 | report_type、status、review_status、quality_score、updated_at、created_by |
| 生成面板 | 选择竞品、时间窗、报告类型、focus、是否重用 claims |
| 详情布局 | 左侧报告正文，中间或右侧 evidence/quality/audit 侧栏 |
| 质量问题 | blocker、major、minor 分类，定位 section_key、claim_id、evidence_ref |
| 审批动作 | approve、reject、publish、rerun quality，按角色展示 |
| 引用跳转 | citation label 点击后定位 evidence snippet 和 source URL |

P1 内容：

- 报告版本历史。
- 报告对比。
- Markdown / PDF / Word 导出入口，后端能力确认后再实现。

### 6.5 Tasks

目标：让异步任务从隐藏轮询状态升级为可诊断的任务历史。

P0 内容：

| 能力 | 说明 |
|---|---|
| 任务列表 | task_id、task_type、status、created_at、duration、actor、关联对象 |
| 阶段详情 | task_stages 顺序、状态、耗时、错误摘要 |
| 事件日志 | task_events 摘要，默认折叠长文本 |
| 失败诊断 | error_type、message、retry_count、下一步建议 |
| 关联跳转 | 任务到 facts、reports、source documents |

P1 内容：

- SSE/Redis Stream 实时事件展示。
- 失败任务重试入口。
- 队列和 worker 健康摘要。

### 6.6 Query / Research

目标：保留 Agent 分析能力，但把产物纳入报告治理。

P0 内容：

- 提供常用分析模板，但模板按钮使用 SVG 图标或纯文本。
- 流式工具调用事件展示为结构化列表。
- `generate_analysis_report` 结果展示 `report_id`、`status`、`review_status`、`quality_score`，并提供跳转 Reports 的动作。
- SSE 请求补齐认证 header，避免登录后流式接口绕过 API Key。

### 6.7 Settings / Config / Webhook

目标：运营配置页面清楚表达权限、环境和风险。

P0 内容：

| 页面 | 改造 |
|---|---|
| Settings | source health、采集策略、调度状态、保存后关联 task |
| Config | secret 脱敏、生产危险配置只读、保存后 reload 结果、审计列表 |
| Webhook | 渠道状态、测试结果、最近推送、admin-only 写操作 |

---

## 7. 共享组件计划

### 7.1 基础组件

| 组件 | 职责 |
|---|---|
| `SvgIcon.vue` | 根据 icon name 渲染本地 SVG，统一尺寸、颜色和 title |
| `StatusBadge.vue` | report/task/fact/review 状态统一展示 |
| `RoleGate.vue` | 根据角色显示或禁用前端动作，不替代后端授权 |
| `ConfirmDialog.vue` | 删除、发布、拒绝等危险动作确认 |
| `EmptyState.vue` | 统一空状态，图标使用 SVG |
| `LoadingState.vue` | spinner、skeleton 和加载文案 |
| `PageToolbar.vue` | 标题、筛选摘要、主动作 |

### 7.2 业务组件

| 组件 | 职责 |
|---|---|
| `CompetitorBadge.vue` | 竞品标签、品牌色、跳转 |
| `IntelTypeBadge.vue` | fact type / dimension 标签 |
| `EvidencePanel.vue` | evidence refs、snippet、URL、source document 定位 |
| `QualityIssueList.vue` | 报告质量问题列表和 severity 过滤 |
| `AuditTimeline.vue` | report/task/config 审计时间线 |
| `TaskStageTimeline.vue` | task stage 可视化 |
| `ReportOutline.vue` | 报告章节导航和 citation 定位 |
| `FilterBar.vue` | 通用筛选表单，支持保存查询参数到 URL |

### 7.3 SVG 图标资产

建议新增：

```text
frontend/src/components/icons/SvgIcon.vue
frontend/src/components/icons/paths.js
```

`paths.js` 保存受控图标路径，例如：

| 名称 | 用途 |
|---|---|
| `dashboard` | Dashboard |
| `competitor` | Competitors |
| `intel` | Intel |
| `report` | Reports |
| `task` | Tasks |
| `search` | Query |
| `memory` | Memory |
| `webhook` | Webhook |
| `settings` | Settings |
| `config` | Config |
| `approve` | 审批 |
| `reject` | 拒绝 |
| `publish` | 发布 |
| `refresh` | 重新质检 / 刷新 |
| `evidence` | 证据 |
| `warning` | 质量问题 |

图标可以手写极简 SVG path，或在确认许可证可用后引入本地化 SVG path。不要通过运行时 CDN 加载。

---

## 8. API 对接计划

### 8.1 已有 API

本阶段优先使用已有 API：

| 页面 | API |
|---|---|
| Dashboard | `/api/competitors`、`/api/reports`、`/api/tasks/{task_id}`、`/api/health`，必要时先做前端聚合 |
| Intel | `/api/intel/facts`、`/api/intel/facts/{id}`、`/api/intel/facts/{id}/evidence`、`/api/intel/pipeline` |
| Competitors | `/api/competitors`、`/api/competitors/{id}`、`/api/competitors/{id}/facts`、`/api/competitors/{id}/timeline` |
| Reports | `/api/reports`、`/api/reports/{id}`、`/api/reports/{id}/quality`、`/api/reports/{id}/audit`、审批/发布 API |
| Config | `/api/config`、`/api/config/audit`、`/api/config/reload`、`/api/config/providers` |
| Webhook | `/api/webhook/*` |

### 8.2 建议补充 API

如果现有 API 无法支撑 Dashboard 和 Tasks 页面，建议后端补充聚合接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/dashboard/summary` | KPI、待办、失败任务、最新 facts、待审报告 |
| `GET` | `/api/tasks` | 任务历史列表，支持 type/status/date/actor 筛选 |
| `GET` | `/api/tasks/{task_id}/events` | 任务事件列表或分页 |
| `POST` | `/api/tasks/{task_id}/retry` | admin/analyst 重试失败任务 |
| `GET` | `/api/sources/health` | RSS/Web source 健康摘要 |

补充 API 必须遵循现有 role 权限矩阵。

### 8.3 前端 API 封装

`frontend/src/api/index.ts` 继续作为短期统一入口，但第四阶段应做以下整理：

- 给 `queryApi.askStream()` 和 `researchApi.executeStream()` 补齐 `Authorization` header。
- 把 response normalization 放到 API 层，视图组件不要重复判断多种后端字段名。
- 将 report、intel、task 的分页参数和筛选参数保持 URL query 可恢复。
- 保留 TypeScript 文件但不扩大类型改造；如新增 `types.ts`，只定义共享 DTO，不要求全项目迁移。

---

## 9. 状态与权限规则

### 9.1 角色可见性

| 角色 | 前端动作 |
|---|---|
| viewer | 查看 facts、claims、competitors、reports、tasks、quality、audit、webhook/settings 列表 |
| analyst | viewer + 触发 pipeline、生成报告、重新质检、创建或更新 draft facts/claims、运行 Agent |
| admin | analyst + 审批、发布、删除、配置修改、Webhook 管理、API Key 管理 |

前端动作隐藏只是体验优化。所有写操作必须处理 401/403，并显示后端返回的错误。

### 9.2 状态映射

状态 badge 使用统一组件和色彩：

| 类型 | 状态 |
|---|---|
| report | `draft`、`quality_reviewing`、`revision_required`、`waiting_review`、`approved`、`published`、`rejected`、`archived` |
| review | `not_reviewed`、`passed`、`failed`、`needs_human` |
| task | `queued`、`running`、`retrying`、`succeeded`、`failed`、`cancelled`、`waiting_review` |
| fact | `draft`、`active`、`rejected`、`archived` |

---

## 10. 视觉与交互规范

### 10.1 布局

| 视口 | 目标布局 |
|---|---|
| `>= 1440px` | 侧边栏 + 主列表/正文 + 右侧详情面板 |
| `1024-1439px` | 侧边栏 + 主内容，详情用抽屉 |
| `768-1023px` | 折叠侧边栏 + 主内容 |
| `< 768px` | 顶栏 + 单栏，关键动作放入更多菜单 |

### 10.2 表格与列表

- facts、reports、tasks 默认使用表格或密集列表。
- 每行主信息不超过两行，详情放抽屉或侧栏。
- 长 markdown、snippet、error stack 默认折叠。
- 筛选条件应能体现在 URL query 中，刷新后不丢失。

### 10.3 可访问性

- SVG 图标按钮必须有 `aria-label` 或 `title`。
- 状态不能只靠颜色表达，必须有可读文本。
- 键盘焦点样式不能被移除。
- 弹窗和抽屉需要 Escape 关闭、焦点回到触发按钮。

### 10.4 文字约束

- 页面文案使用专业、短句、动作明确的中文。
- 不使用 emoji 字符作为装饰或语义。
- 不使用“魔法”“一键起飞”等泛化营销表达。
- 错误文案包含下一步动作，例如“当前角色无权发布报告，请使用 admin API Key 登录”。

---

## 11. 实施步骤

### Step 1：前端基线清理

产物：

- 移除 `router/index.js`、`NavSidebar.vue`、空状态、按钮和页面标题中的 emoji。
- 新增 `SvgIcon.vue` 和本地图标 path。
- `NavSidebar.vue` 改为 icon name + SVG 渲染。
- `/` 默认重定向调整为 `/dashboard`。

验收：

- `rg` 扫描前端源码不存在 emoji 图标字符。
- 导航、logo、移动端菜单、空状态均正常显示 SVG。

### Step 2：共享组件层

产物：

- `StatusBadge.vue`
- `RoleGate.vue`
- `ConfirmDialog.vue`
- `EvidencePanel.vue`
- `QualityIssueList.vue`
- `TaskStageTimeline.vue`
- `AuditTimeline.vue`

验收：

- Reports、Intel、Tasks 至少复用状态 badge 和证据面板。
- 角色隐藏逻辑集中，不在各页面散落复杂判断。

### Step 3：Dashboard

产物：

- `DashboardView.vue`
- `dashboardApi`，优先前端聚合已有 API；后端聚合 API 可后置。

验收：

- 首页显示 KPI、待处理报告、失败任务、最新情报和快捷动作。
- Dashboard 加载失败时能分别展示 degraded component，不阻断整个页面。

### Step 4：Reports 工作流升级

产物：

- `ReportView.vue` 拆分列表、详情、生成面板、证据侧栏和质量问题区。
- 审批、拒绝、发布、重新质检动作接入。

验收：

- 质量失败报告不能显示为可发布。
- citation label 可定位 evidence。
- admin 可完成 approve -> publish，analyst 只能 generate/review quality。

### Step 5：Intel 与 Competitors 联动

产物：

- `IntelView.vue` 筛选和详情抽屉升级。
- `CompetitorView.vue` 增加 facts 聚合和 timeline 面板。

验收：

- 从竞品详情可跳转到对应 facts 筛选。
- 从 fact 可查看 evidence refs 和关联 claims。
- 触发 pipeline 后能看到任务状态或跳转 Tasks。

### Step 6：Tasks 页面

产物：

- `TaskView.vue`
- `tasksApi.list()`、`tasksApi.getEvents()`，如后端未提供则先记录 API 需求并保留单 task 查询。

验收：

- 可查看最近任务、阶段、耗时、失败原因。
- 从任务可跳转报告或 facts。

### Step 7：配置、推送和 Agent 体验收尾

产物：

- `ConfigView.vue` 强化生产只读、脱敏和审计。
- `WebhookView.vue` 清理 emoji 和 admin-only 动作。
- `QueryView.vue` / Research SSE 补齐认证 header，报告生成结果跳转 Reports。

验收：

- viewer 看不到写操作；直接调用仍由后端拒绝。
- SSE 接口在认证启用时可用。

### Step 8：测试与文档更新

产物：

- 更新 `docs/product-specs/ui-design-spec.md`、`docs/design-docs/api-routes.md` 和本计划执行状态。
- 前端 build 验证。
- 浏览器人工验收记录或截图。

验收：

- `npm run build` 或 `pnpm build` 通过。
- 在桌面和移动视口检查 Dashboard、Reports、Intel、Tasks。
- 前端源码无 emoji 字符，界面图标均为 SVG。

---

## 12. 测试计划

### 12.1 静态检查

- 扫描 `frontend/src` 中的 emoji 字符。
- 扫描 `router/index.js` 和导航配置，确认 icon 字段为 SVG icon name。
- 检查是否引入远程图标 CDN 或 icon font。
- 检查 `fetch` SSE 请求是否带认证 header。

### 12.2 构建检查

- `npm run build` 或 `pnpm build`。
- 生产构建产物由 FastAPI 静态托管时路由刷新可回退到 SPA。

### 12.3 浏览器检查

使用浏览器验证：

| 视口 | 页面 |
|---|---|
| 1440x900 | Dashboard、Reports、Intel、Tasks |
| 1024x768 | Reports 详情与证据侧栏 |
| 390x844 | 移动端导航、报告审批、fact 详情 |

检查项：

- SVG 图标可见且不挤压文本。
- 表格、筛选条、按钮文本不溢出。
- 抽屉、弹窗、toast 不遮挡关键操作。
- 401/403 错误能被用户理解。

### 12.4 权限检查

- 无 API Key：只能看到登录入口。
- viewer：只读页面可用，写操作不可见；手动调用写 API 返回 403。
- analyst：可以触发 pipeline、生成报告、重跑质检；不能审批发布。
- admin：可以审批、发布、配置和 Webhook 管理。

---

## 13. 验收标准

第四阶段完成的硬性标准：

1. `/dashboard` 成为默认首页，并展示工作台级 KPI、待办和任务状态。
2. `/reports` 支持报告详情、质量问题、证据侧栏、审计链路和审批发布动作。
3. `/intel` 支持结构化 facts 筛选、详情、evidence 和竞品/产品归因查看。
4. `/competitors` 支持竞品 facts 聚合和事件时间线。
5. `/tasks` 支持任务历史或至少任务详情、阶段和失败原因查看；若后端列表 API 未完成，文档记录缺口并给出后端补充接口。
6. 前端所有图标均为 SVG；源码和页面不使用 emoji 图标。
7. 角色可见性与后端权限矩阵一致，401/403 有明确反馈。
8. Report、Intel、Task 的核心状态使用统一 badge。
9. SSE 请求在认证开启时仍能正常工作。
10. 前端构建通过，桌面和移动视口无明显布局重叠、文字溢出或空白主视图。

---

## 14. 风险与取舍

| 风险 | 说明 | 处理 |
|---|---|---|
| Dashboard 依赖聚合 API | 后端可能暂未提供 `/api/dashboard/summary` | 先用已有 API 前端聚合，性能不足再补后端 |
| Tasks 列表 API 不完整 | 当前文档只明确 `/api/tasks/{task_id}` | 第四阶段前半程补 `/api/tasks`，否则先实现单任务详情和文档缺口 |
| SVG 图标资产分散 | 页面各自内联会造成重复 | 用 `SvgIcon.vue` + `paths.js` 集中管理 |
| 前端权限误导 | 用户隐藏按钮不等于授权 | 所有写操作继续以后端 401/403 为准 |
| 一次升级页面过多 | Dashboard、Reports、Intel、Tasks 同时改造风险较高 | 先做共享组件和 Reports，再扩展到 Intel/Tasks |
| TypeScript 半迁移 | `api/index.ts` 已存在但项目不是 TS 项目 | 本阶段不扩大 TS 范围，只整理 API 边界 |
| 图表依赖膨胀 | 新增图表库会增加包体和维护成本 | P0 用表格和轻量 SVG，P1 再评估 ECharts/Chart.js |

---

## 15. 推荐优先级

P0：

1. 移除前端 emoji，建立 SVG-only 图标系统。
2. Reports 工作流升级：质量、证据、审计、审批。
3. Dashboard 最小工作台。
4. Intel facts 筛选和证据详情。
5. SSE 认证修复。

P1：

1. Tasks 列表和阶段时间线。
2. Competitors facts 聚合和产品线矩阵。
3. Config / Settings / Webhook 运营体验增强。
4. URL query 持久化筛选条件。

P2：

1. 报告版本对比和导出。
2. 实时任务事件流。
3. 来源健康和采集策略可视化。
4. 更完整的图表库接入。

---

## 16. 最小可行版本

如果第四阶段只做一轮，最小闭环建议：

1. 新增 `SvgIcon.vue`，清理导航、空状态和页面中的 emoji。
2. 新增 Dashboard，展示 KPI、待审报告、失败任务和最新 facts。
3. 重构 Reports 详情，展示 markdown、quality issues、evidence refs、audit timeline，并接入 approve/reject/publish/review quality。
4. 强化 Intel 详情抽屉，能从 fact 查看 evidence 和竞品/产品归因。
5. 补一个 Tasks 入口，至少能通过最近 pipeline/report 任务查看阶段和失败原因。
6. 修复 SSE 认证 header。
7. 完成构建和浏览器检查。

这 7 项完成后，InsightForge 前端会从“可操作的功能页面集合”升级为“围绕竞品情报生产线组织的企业工作台”。
