# API 路由参考

> **来源**：从 [ARCHITECTURE.md](../../ARCHITECTURE.md) §7 迁出的完整 API 路由表与前端页面映射。

---

## API 路由一览

### 健康检查

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/health` | 健康检查 |

### 新闻管理

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/news` | 分页获取新闻列表（支持来源/语言/关键词筛选） |
| GET | `/api/news/stats` | 数据库统计 |
| GET | `/api/news/sources` | 所有新闻来源 |
| GET | `/api/news/{id}` | 单篇新闻全文 |
| POST | `/api/news/pipeline` | 手动触发 Pipeline (异步返回 task_id) |
| POST | `/api/news/batch-delete` | 批量删除文章（含向量记录） |

### 简报

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/briefs` | 简报文件列表 |
| GET | `/api/briefs/{filename}` | 单份简报内容 |
| POST | `/api/briefs/generate` | 手动生成简报 (异步返回 task_id) |

### 异步任务

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/tasks/{task_id}` | 轮询查询异步任务状态和结果 |

### Agent 问答

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/api/query` | ReAct Agent 非流式问答 |
| POST | `/api/query/stream` | ReAct Agent SSE 流式问答（结构化 AgentEvent JSON，含 token 增量、工具调用状态和 run_id）|

### 深度研究

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/api/research/stream` | SSE 流式深度研究 |
| POST | `/api/research/sessions/plan` | 生成 Plan Execute 研究计划，返回 session_id、plan、todos |
| PUT | `/api/research/sessions/{session_id}/plan` | 保存用户审阅/编辑后的 plan 和 todo list |
| POST | `/api/research/sessions/{session_id}/execute/stream` | 按确认后的 plan/todos SSE 流式执行研究 |
| GET | `/api/research/sessions/{session_id}` | 获取 Plan Execute 会话详情 |
| GET | `/api/research` | 研究报告列表 |
| GET | `/api/research/{filename}` | 单份研究报告内容 |
| DELETE | `/api/research/{filename}` | 删除研究报告 |
| POST | `/api/research/batch-delete` | 批量删除研究报告 |
| POST | `/api/research/batch-export` | 批量导出 (单文件 .md / 多文件 .zip) |
| POST | `/api/research/push/{filename}` | 推送研究报告到 Webhook 渠道 |

### NewsAPI 代理

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/newsapi/everything` | NewsAPI 全文搜索代理 |
| GET | `/api/newsapi/top-headlines` | NewsAPI 热门头条代理 |
| POST | `/api/newsapi/save` | 保存 NewsAPI 文章到本地 |

### Webhook 推送

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/webhook/platforms` | 支持的推送平台列表 |
| GET | `/api/webhook/channels` | 推送渠道列表（URL 脱敏） |
| POST | `/api/webhook/channels` | 添加推送渠道 |
| PUT | `/api/webhook/channels/{id}` | 更新推送渠道 |
| DELETE | `/api/webhook/channels/{id}` | 删除推送渠道 |
| POST | `/api/webhook/channels/{id}/test` | 发送测试消息 |
| POST | `/api/webhook/push` | 推送最新简报到所有启用渠道 |
| POST | `/api/webhook/push/{id}` | 推送到指定渠道 |
| GET | `/api/webhook/auto-push` | 获取自动推送状态 |
| PUT | `/api/webhook/auto-push` | 设置自动推送开关 |

### 配置管理

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/config` | 获取配置（API Key 脱敏） |
| PUT | `/api/config` | 更新 .env 配置 |
| GET | `/api/config/providers` | LLM 提供商列表 |
| POST | `/api/config/models` | 远程获取可用模型列表 |

### 功能设置

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/settings/feeds` | RSS 源列表 |
| POST | `/api/settings/feeds` | 添加 RSS 源 |
| DELETE | `/api/settings/feeds/{id}` | 删除 RSS 源 |
| GET | `/api/settings/schedule` | 获取调度配置 |
| PUT | `/api/settings/schedule` | 更新调度配置 |

---

## 前端页面映射

| 路由 | 视图组件 | 功能 |
|---|---|---|
| `/news` | `NewsView.vue` | 新闻列表浏览、筛选、Pipeline 触发、批量删除 |
| `/briefs` | `BriefView.vue` | 简报列表、查看、手动生成 |
| `/newsapi` | `NewsApiView.vue` | NewsAPI 在线搜索 (everything + top-headlines) |
| `/query` | `QueryView.vue` | ReAct Agent 问答（推理过程可视化 + SSE 流式） |
| `/webhook` | `WebhookView.vue` | 推送渠道管理、测试、手动推送、自动推送开关 |
| `/settings` | `SettingsView.vue` | RSS 源管理 + 爬虫源管理 + 调度参数配置 |
| `/config` | `ConfigView.vue` | LLM/Embedding/Rerank/搜索引擎 API 配置管理 |

---

## 开发模式通信

### `/api/query/stream` SSE 事件

流式问答保持 `data: {...}\n\n` 和 `data: [DONE]` 结束标记。主要事件：

| event_type | 用途 |
|---|---|
| `llm_delta` | 当前 LLM 原始输出片段，用于前端实时显示 |
| `thought` | Agent 显式 `Thought:` 思考摘要 |
| `action_start` | 准备调用工具，包含 `tool_name` 和 `tool_input` |
| `action_result` | 工具返回摘要，包含精简 `tool_result` 元数据 |
| `answer_delta` | 最终回答增量 |
| `answer` | 最终完整回答 |
| `error` | 流式执行错误 |

每个事件包含 `run_id`、`sequence`、`timestamp`，后端 structlog 使用同一 `run_id` 记录更完整的审计信息。

```
浏览器                  Vite Dev Server (:5173)          FastAPI (:8005)
  │                           │                              │
  ├──  GET /news  ──────────▶ │  (SPA 路由，返回 index.html) │
  │                           │                              │
  ├──  GET /api/news  ───────▶│── proxy ────────────────────▶│
  │                           │                              │  PostgreSQL 查询
  │◀──  JSON 响应  ───────────│◀─────────────────────────────│
```

生产模式下，Vue 构建产物放在 `delivery/static/`，由 FastAPI 直接托管 SPA。
