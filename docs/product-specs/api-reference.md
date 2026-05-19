# API 路由参考

API 路由表已迁移到设计文档目录，作为架构基线的一部分维护：

→ [docs/design-docs/api-routes.md](../design-docs/api-routes.md)

## 认证与权限摘要

生产环境 API 使用应用级 API Key。客户端发送 `Authorization: Bearer <api_key>`，也兼容 `X-API-Key`。未提供或无效 key 返回 401，角色不足返回 403。

前端 SSE 请求同样需要携带 `Authorization: Bearer <api_key>`，包括 `POST /api/query/stream` 和 `POST /api/research/sessions/{session_id}/execute/stream`。这些接口不应绕过应用级 API Key 和 analyst 权限。

角色分为 `viewer`、`analyst`、`admin`：viewer 只读，analyst 可生成报告/重跑质检/运行 Pipeline/执行 Agent 和研究，admin 可审批发布报告、修改配置、管理 Webhook 和删除资源。

## 报告质量接口摘要

`POST /api/reports/generate` 现在统一走 `ReportService` 工作流：保存草稿、绑定 report claim/evidence、运行质量门禁并返回结构化结果。响应包含：

| 字段 | 说明 |
|---|---|
| `report_id` | 已保存报告 ID |
| `status` | 报告状态，如 `revision_required`、`waiting_review` |
| `review_status` | 最近一次质量审查状态，如 `failed`、`passed`、`needs_human` |
| `quality_score` | 最近一次质量分，0-1 |
| `quality_summary` | 最近一次质量摘要 |
| `blocking_issues_count` | blocker 级质量问题数量 |
| `content` | Markdown 报告正文 |
| `issues` | 结构化质量问题列表 |

报告详情 `GET /api/reports/{report_id}` 会返回正文、`claims`、`evidence_refs`、`quality_reviews` 和质量摘要；`GET /api/reports/{report_id}/quality` 仅返回质量审查列表；`POST /api/reports/{report_id}/quality/review` 可重新运行质量门禁。

`auto_publish=true` 只在服务端 `REPORT_QUALITY_AUTO_PUBLISH=true` 且质量审查通过时生效；生产默认关闭。质量失败、Judge JSON 解析失败、无证据关键结论或无效 citation 均不能发布。

审批发布接口：

| 方法 | 路径 | 规则 |
|---|---|---|
| POST | `/api/reports/{report_id}/approve` | admin only；仅 `waiting_review + passed` 可审批 |
| POST | `/api/reports/{report_id}/reject` | admin only；仅 `waiting_review` 可退回修订 |
| POST | `/api/reports/{report_id}/publish` | admin only；仅 `approved + passed` 可发布 |

配置审计接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/config/audit` | admin only；返回配置修改和 reload 审计记录 |

## Dashboard 聚合口径

Phase 4 不新增 `/api/dashboard/summary`。`/dashboard` 先由前端聚合既有只读 API：

| 来源 API | Dashboard 用途 |
|---|---|
| `GET /api/competitors` | 竞品数量 |
| `GET /api/reports` | 待审批、需修订和质量失败报告 |
| `GET /api/intel/facts` | 7 日 facts 和最新情报 |
| `GET /api/health` | 系统健康摘要 |
| `GET /api/tasks` | 最近任务历史、失败任务统计 |
| `GET /api/tasks/{task_id}` | 任务阶段和事件详情；任务列表接口不可用时回退本地最近 task id |

`GET /api/tasks` 支持 `task_type`、`status`、`date_from/date_to`、`actor`、`limit/offset`，返回 `items/total/limit/offset`。

## 验收口径

- 报告生成、重新质检和 Pipeline 需要 analyst 或 admin。
- 报告审批、发布、删除、配置修改、配置审计和 Webhook 管理需要 admin。
- viewer 只能读取 facts、claims、competitors、reports、tasks、report quality/audit 和只读配置页面允许的内容。
- 所有 secret/API key 响应均为脱敏值，配置修改审计不保存 secret 原文。

## Phase 3 Step 8 整体验收矩阵

| 场景 | 期望结果 |
|---|---|
| 无证据关键结论、无效 citation、Judge JSON 解析失败或低于阈值 | 报告进入 `revision_required/failed`，不得审批或发布 |
| `POST /api/reports/generate` 质量通过且未开启服务端自动发布 | 报告进入 `waiting_review/passed` |
| analyst 生成报告 | 允许，响应包含 `report_id/status/review_status/quality_score/issues` |
| analyst 发布报告或 viewer 执行写操作 | 返回 403 |
| 未认证访问敏感 API | 返回 401 |
| admin 审批并发布质量通过报告 | 状态按 `waiting_review -> approved -> published` 流转并写入报告审计 |
| `GET /api/config` | 所有 secret 字段脱敏 |
| `PUT /api/config` 或 `POST /api/config/reload` | 写入 `config_audit_log`，审计内容不含 secret 原文 |
| 生产 `/api/health` | 返回 PostgreSQL、Redis、Qdrant、auth、config 的脱敏 readiness；生产禁用认证或 Redis URL 无密码时 unhealthy |
