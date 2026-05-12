# 开发路线图

---

## 当前状态

项目处于 **Demo+** 阶段：前后端分离架构 + ReAct Agent + 深度研究 + Web 搜索 + AI 摘要 + Rerank + 混合检索 RAG + Webhook 推送。

核心基础设施已全部升级为生产级组件（PostgreSQL + pgvector + Celery + Docker Compose）。

## 待推进事项

详见 [技术债务追踪器](exec-plans/tech-debt-tracker.md) 获取当前已知问题列表。

### 近期优先

| 事项 | 说明 | 优先级 |
|---|---|---|
| Celery 重试补偿机制 | 强化 Pipeline/日报任务容错 | P1 |
| RSS 并发抓取 | ThreadPoolExecutor 并发化 | P1 |
| 多环境 .env 配置 | dev/prod 环境隔离 | P2 |
| 认证/授权中间件 | API 安全保护 | P2 |

### 远期规划

| 事项 | 说明 | 优先级 |
|---|---|---|
| 云端部署 (Railway/VPS) | 任何设备可访问 | P2 |
| Telegram Bot 集成 | 平台机器人检索+回答 | P3 |
| 可编辑提示词 | 世界书化分析模板 | P3 |
| 多 Agent 分析 | 多 Agent 协作生成概要 | P3 |

---

## 已完成方案归档

以下文档为历史执行计划，记录了项目从原型到当前架构的演进路径：

| 文档 | 说明 |
|---|---|
| [demo-design.md](exec-plans/completed/demo-design.md) | Demo 原型方案（Streamlit + SQLite + ChromaDB，这些旧技术已废弃） |
| [full-design.md](exec-plans/completed/full-design.md) | 完整方案 v2（历史 PostgreSQL + Qdrant + Celery 规划） |
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
- AI 打标签  已实现 (SummaryService)
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
