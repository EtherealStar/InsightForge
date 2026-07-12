# 设计文档索引

本目录包含 Logos 项目的详细设计文档，是 [ARCHITECTURE.md](../../ARCHITECTURE.md) 中各章节的深度展开。

---

## 文档清单

| 文档 | 内容 | 来源 |
|---|---|---|
| [tech-decisions.md](tech-decisions.md) | 技术选型完整论证、演进对比、ADR 决策记录 | ARCHITECTURE.md §2 |
| [protocol-contracts.md](protocol-contracts.md) | Protocol 接口详细设计、实现说明、已知差异 | ARCHITECTURE.md §5 |
| [react-agent.md](react-agent.md) | ReAct Agent 循环、工具系统、内置工具、工具链 | ARCHITECTURE.md §13 |
| [changelog.md](changelog.md) | 架构变更历史记录（含 RAGAs 评估框架） | ARCHITECTURE.md 顶部 |
| [api-routes.md](api-routes.md) | API 路由表、前端页面映射、SSE 通信约定 | ARCHITECTURE.md §6 |
| [source-governance-and-deduplication.md](source-governance-and-deduplication.md) | 来源分级、SimHash 近重复检测、主来源晋升与多证据验证目标设计 | 2026-07-12 设计讨论 |
| [collection-and-normalization.md](collection-and-normalization.md) | 来源级扇出采集、Connector/Fetch Engine、artifact 生命周期、Content Block 清洗与 SLO | ADR-0003 / ADR-0004 |
| [structured-intelligence-model.md](structured-intelligence-model.md) | Evidence Reference / Intel Fact / Insight Claim 三层模型、不变量、状态与关系设计 | ADR-0002 / 2026-07-12 grilling |
