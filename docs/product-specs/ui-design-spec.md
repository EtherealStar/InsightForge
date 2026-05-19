# InsightForge UI 需求设计文档

> **状态**：需求文档（当前阶段不实施 UI 重新设计，仅记录设计方向）

---

## 1. 设计目标

将原 Logos 新闻助手的 UI 改造为专业的竞品分析仪表盘，核心设计原则：

- **数据密度**：一屏展示尽可能多的竞品洞察信息
- **结构化呈现**：对比矩阵、SWOT 可视化、趋势图表
- **可操作性**：每个数据点都可追溯到原始情报
- **专业感**：类似 Bloomberg Terminal / Notion AI 的高信息密度设计

---

## 2. 页面规划

### 2.1 竞品管理页 (`/competitors`)

**当前状态**：已实现基础卡片网格 + 详情工作台

**当前能力**：
- 竞品档案卡片增加 logo 展示和关键指标（情报数量、最近更新时间）
- 详情面板展示产品线、结构化 facts、事件时间线和维度/类型覆盖摘要
- facts 和 timeline 项可跳转 `/intel` 并带入竞品、类型、维度或日期筛选

**未来设计方向**：
- 产品线对比矩阵（表格形式，横向对比各竞品的产品、定价、功能）
- 竞品关系图谱（可选，展示竞品间的竞争/合作关系）
- 竞品活跃度热力图（按月展示各竞品的情报密度）

### 2.2 情报列表页 (`/news` → `/intel`)

**当前状态**：已升级为 facts 表格 + 详情抽屉

**当前能力**：
- 支持 competitor、product、fact_type、dimension、status、日期、关键词、重要度和置信度筛选
- 表格展示 fact 文本、竞品/产品归因、类型、维度、分数、状态和日期
- 详情抽屉展示 fact 字段、evidence refs、关联 claims，并允许 analyst 更新非 active fact 状态和补充归因
- 手动 Pipeline 提交后跳转 `/tasks?task_id=...` 追踪阶段

### 2.3 分析报告页 (`/briefs` → `/reports`)

**当前状态**：已升级为报告工作流工作台

**当前能力**：
- 报告列表支持 `report_type`、`status`、`review_status`、质量分和更新时间筛选，筛选写入 URL query
- 报告详情使用正文、章节、evidence、quality issues 和 audit 三栏布局
- analyst/admin 可生成报告和重跑质量门禁；admin 可审批、退回、发布和删除
- citation/quality issue 可联动证据或章节定位

**未来设计方向**：
- 报告导出（PDF / Word / Markdown）
- 报告对比视图（并排展示同一竞品不同时期的报告）

### 2.4 智能分析页 (`/query`)

**当前状态**：已更新文案为竞品分析主题

**当前能力**：
- 快捷操作面板保留常用分析任务
- Agent 推理过程以结构化事件列表展示，不使用 emoji 或空图标占位
- `generate_analysis_report` 结果若包含 `report_id`，对话中提供跳转 `/reports?report_id=...`
- 深度研究报告文件与受质量门禁治理的 Reports 明确区分

### 2.5 仪表盘首页 (`/dashboard`)

**当前状态**：Phase 4 Step 3 P0 工作台入口，`/` 默认重定向到 `/dashboard`

**当前能力**：
- 核心指标卡片行：竞品数量、7 日 facts、待处理报告、失败任务、系统健康
- 待处理队列：`waiting_review`、`revision_required`、质量失败或需人工复核的报告
- 最新情报列表：展示结构化 facts、状态、类型和分析维度
- 最近任务降级视图：仅展示当前浏览器触发并保存的 task id；完整 `/api/tasks` 列表后续补齐
- 快捷操作按钮：运行 Pipeline、进入 Intel 筛选、查看报告审批、开始智能分析

### 2.6 API 配置页 (`/config`)

**当前状态**：已接入 admin-only 配置管理和审计

**未来设计方向**：
- 当前最小企业接入：admin only，显示 Judge、安全和质量策略配置
- 当前最小企业接入：生产环境危险配置只读，secret 字段保留脱敏值，不误写回
- 当前最小企业接入：保存后展示 reload 结果，配置审计列表可刷新查看
- 当前最小企业接入：标题和动作统一使用 SVG 图标，secret 字段保留后端脱敏值语义
- 后续增强：连接状态检测（每个 API Key 的可用性实时检测）
- 一键导入/导出配置

### 2.7 应用认证入口

**当前状态**：已实现 API Key 登录入口

**未来设计方向**：
- 当前最小企业接入：首次进入应用时输入应用 API Key，认证成功后前端保存 actor 和 role
- 当前最小企业接入：导航和按钮按 viewer / analyst / admin 角色隐藏不可用操作
- 后续增强：API Key 管理页、过期提醒和多用户审计筛选

### 2.8 任务追踪页 (`/tasks`)

**当前状态**：Phase 4 Step 6 已新增任务历史工作台

**当前能力**：
- 路由 `/tasks`，支持 `task_id`、`task_type`、`status`、日期筛选并写入 URL query
- 任务列表读取 `GET /api/tasks`，详情读取 `GET /api/tasks/{task_id}`
- 展示 run 摘要、阶段进度、事件日志、失败原因、耗时和尝试次数
- Pipeline 提交后从 Intel/Dashboard 跳转任务详情

---

## 3. 设计系统

### 3.0 SVG-only 图标规范

前端页面、导航、按钮、空状态、状态提示和移动端菜单不得使用 emoji 作为图标或装饰。界面图标统一使用本地 SVG 组件或本地 SVG 资产，当前基础组件为 `SvgIcon.vue`，导航和页面动作使用 icon name 映射。

禁止引入远程图标 CDN、icon font 或 PNG/JPG 作为界面图标。竞品 logo 或用户上传图片不受此限制。

### 3.1 配色方案

保持当前深色主题，增加竞品品牌色系：

```css
/* 竞品品牌色 */
--color-cursor:    #00a67e;   /* Cursor 绿色 */
--color-trae:      #6366f1;   /* TRAE 紫色 */
--color-windsurf:  #f59e0b;   /* Windsurf 金色 */

/* 情报类型色 */
--color-intel-feature:   #10b981;  /* 功能更新 */
--color-intel-pricing:   #f59e0b;  /* 定价变更 */
--color-intel-funding:   #8b5cf6;  /* 融资消息 */
--color-intel-product:   #3b82f6;  /* 产品发布 */
--color-intel-general:   #6b7280;  /* 一般信息 */
```

### 3.2 组件复用

| 组件 | 用途 |
|---|---|
| `SvgIcon` | 本地 SVG 图标渲染 |
| `StatusBadge` | report/review/task/fact 状态统一展示 |
| `RoleGate` | 按 viewer/analyst/admin 控制前端显示或禁用 |
| `ConfirmDialog` | 删除、发布、拒绝等确认操作 |
| `EmptyState` | 空状态，图标使用 SVG |
| `LoadingState` | 统一加载状态 |
| `EvidencePanel` | evidence refs、snippet、URL 展示 |
| `QualityIssueList` | blocker/major/minor 质量问题列表 |
| `TaskStageTimeline` | 任务阶段和失败摘要 |
| `AuditTimeline` | report/task/config 审计时间线 |
| `CompetitorBadge` | 竞品标签（带品牌色） |
| `IntelTypeBadge` | 情报类型标签 |
| `ReportCard` | 报告列表项 |
| `SourceRef` | 溯源引用标签（可点击跳转） |
| `TrendChart` | 情报趋势折线图 |
| `ComparisonMatrix` | 竞品对比矩阵表格 |

### 3.3 响应式断点

| 断点 | 布局 |
|---|---|
| ≥1440px | 三栏（侧边栏 + 主内容 + 详情面板） |
| 1024-1439px | 两栏（侧边栏 + 主内容） |
| 768-1023px | 折叠侧边栏 + 主内容 |
| <768px | 移动端单栏 + 底部导航 |

---

## 4. 实施优先级

| 优先级 | 内容 | 依赖 |
|---|---|---|
| P0 | 竞品管理页完善（产品线对比矩阵） | 当前已有基础 |
| P0 | 报告详情页 + 溯源面板 | 后端 API 已就绪 |
| P1 | 仪表盘首页 | 需要统计 API |
| P1 | 情报列表竞品筛选 + 类型标签 | 已有 intel_type |
| P2 | 情报时间线视图 | 需要新组件 |
| P2 | 报告导出功能 | 需要后端支持 |
| P3 | 竞品关系图谱 | 需要可视化库 |
| P3 | 审计链路可视化 | 需要设计迭代 |

---

## 5. 技术选型建议

| 需求 | 推荐 |
|---|---|
| 图表 | ECharts 或 Chart.js |
| 关系图 | D3.js 或 vis-network |
| Markdown 渲染 | 已有 marked.js |
| PDF 导出 | html2pdf.js 或后端 weasyprint |
| 表格 | AG Grid（复杂表格）或原生 table |
