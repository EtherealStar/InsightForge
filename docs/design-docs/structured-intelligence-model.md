# 结构化情报三层模型

> **状态**：已接受的目标设计，尚未完成实现迁移  
> **决策日期**：2026-07-12  
> **ADR**：[0002-three-layer-structured-intelligence.md](../adr/0002-three-layer-structured-intelligence.md)

本文定义 InsightForge 的 Evidence Reference、Intel Fact 和 Insight Claim 三层结构化情报模型。当前代码、API 和数据库仍包含 `owner_type/owner_id`、JSONB ID 数组、业务 score 和可原地改写对象等旧基线；在迁移完成前，[ARCHITECTURE.md](../../ARCHITECTURE.md) 和生成的数据库文档仍用于描述现状，本文用于约束目标实现。

## 1. 目标与非目标

目标：

- 将原文拆解为可查询、可归因、可溯源的原子事实。
- 让同一现实事实复用多个来源证据，并明确支持、反驳和上下文关系。
- 让分析结论只能通过事实进入正式链路，避免绕过事实层。
- 保留历史事实和结论的原始语义，使报告引用可长期复核。
- 使用离散状态和理由表达可信判断，不用伪精确业务分数。

非目标：

- 不建设完整知识图谱、全局谓词本体或通用实体系统。
- 不把 Intel Fact 建成第二套向量检索主路径。
- 首版不建立 Intel Event；时间线直接由 facts 生成。
- 不在业务库保存模型调用全过程；运行细节属于 trace 和结构化日志。
- 不要求数据库物理上只有三张表；“三层”描述领域概念，不限制关联表。

## 2. 概念模型

顶层架构和产品语言只展示三个核心概念：

```text
Evidence Reference  <->  Intel Fact  <->  Insight Claim
不可变原文锚点           原子现实命题         可争辩分析结论
```

关联关系属于内部持久化细节：

```text
Evidence Reference <- fact_evidence -> Intel Fact
Intel Fact          <- claim_facts  -> Insight Claim
Intel Fact          <- fact_competitors / fact_products -> Competitor / Product
```

这一区分同时保留三层模型的清晰度和 PostgreSQL 的引用完整性。

## 3. 全局不变量

1. Intel Fact 独立于单篇文档，是可单独证实或证伪的原子命题。
2. Evidence Reference 是可复用的原文锚点，不拥有 fact 或 claim。
3. supported Insight Claim 至少由一个 active Intel Fact 支持，且不直接关联 Evidence Reference。
4. active Intel Fact 和 supported Insight Claim 的语义不可原地改写。
5. 更正通过 `supersedes` 关系创建新对象；旧对象保留历史引用。
6. 三层对象及其关系不保存 importance、confidence、relevance 或关联置信度等业务 score。
7. 搜索摘要、裸 URL 和无附件人工输入只是 Evidence Candidate，不能激活 fact。
8. 竞品与产品聚合默认只统计 role 为 `subject` 的事实关系。
9. 运行 trace 可以解释抽取过程，但领域对象脱离 trace 后仍能回答当前状态、责任人和取代关系。

## 4. Intel Fact

### 4.1 语义与粒度

一个 Intel Fact 只表达一个原子命题。事件是多个 facts 的展示分组，趋势、信号、风险判断和机会判断属于 Insight Claim。

可接受：

> Cursor Pro 的月度价格在美国市场调整为 20 USD。

不可接受：

> Cursor 发布了新功能、调整价格，并因此加强了企业市场竞争力。

后一条同时包含多个可观察事实和一个分析判断，必须拆分。

### 4.2 目标字段

| 字段 | 语义 |
|---|---|
| `id` | 稳定身份；不从 URL、文本哈希或文档 ID 派生 |
| `fact_type` | 唯一粗粒度分类 |
| `fact_text` | 完整、可独立判断真假的自然语言命题 |
| `normalized_data` | 高价值类型的可选结构化 payload |
| `occurred_at` | 一次性事件在现实世界中的发生时间 |
| `valid_from` / `valid_to` | 持续性事实的可选有效期 |
| `time_precision` | day、month、quarter 或 unknown；禁止虚构精确日期 |
| `candidate_key` | 仅用于事实候选召回，不是唯一身份 |
| `lifecycle_status` | draft、active、superseded、retracted 或 rejected |
| `verification_status` | single_source、self_reported、corroborated 或 disputed |
| `status_reason` | rejected、retracted、disputed 等状态的可解释理由 |
| `supersedes_fact_id` | 新事实对旧事实的显式更正关系 |
| `created_by` | 创建该领域对象的用户或 Agent 身份 |
| `created_at` / `updated_at` | 领域对象的持久化时间 |

`verification_status` 在 draft 阶段可以为空；active 后由证据关系确定性派生，不接受抽取模型直接填写。

### 4.3 唯一事实分类

| fact_type | 覆盖范围 |
|---|---|
| `product` | 功能、版本、技术能力、可用性 |
| `commercial` | 定价、套餐、促销、销售策略 |
| `corporate` | 融资、并购、组织、人事、招聘 |
| `ecosystem` | 合作伙伴、集成、开发者生态 |
| `customer_market` | 客户案例、采用情况、市场进入 |
| `risk` | 安全、法律、合规、服务事故 |
| `general` | 暂时无法归入以上类别 |

删除 `fact_kind` 和 `dimension`。更细的 `feature_release`、`funding`、`hiring`、`security` 等只作为可选 `subtype` 或标签，不参与事实身份。

### 4.4 渐进式结构化

不要求所有 facts 拆成受控 `subject/predicate/object`。事实身份的语义主体通过竞品/产品关系表达，命题主体保留在 `fact_text`；只有高价值、强查询场景使用版本化 `normalized_data`。

示例：

```json
{
  "schema": "commercial.pricing.v1",
  "amount": 20,
  "currency": "USD",
  "billing_period": "month",
  "market": "US"
}
```

普通功能事实无需构造全局受控谓词或复杂类型化对象。

### 4.5 生命周期

- draft 可修改事实语义。
- active 后冻结 `fact_text`、`fact_type`、时间语义、`normalized_data` 和主体关系。
- 新证据可以改变 `verification_status`，但不能改变事实命题。
- 更正创建新 fact，并通过 `supersedes_fact_id` 指向旧 fact。
- `disputed` 表示存在实质反证但尚未裁决；`retracted` 表示断言已被撤回或确认错误。
- active fact 不物理删除。

## 5. Evidence Reference

### 5.1 权威锚点

Evidence Reference 必须绑定不可变 Document Version 和逐字原文位置。目标字段为：

| 字段 | 语义 |
|---|---|
| `id` | 稳定证据身份 |
| `document_version_id` | 被引用的不可变正文版本 |
| `source_occurrence_id` | 具体发布来源、URL 和来源身份 |
| `quoted_text` | 逐字原文，不是模型摘要 |
| `quote_hash` | 校验引用未被改变 |
| `locator` | 字符偏移或等价的结构化定位信息 |
| `parent_chunk_id` | 可选检索加速字段，不是权威定位 |
| `created_at` | 证据锚点创建时间 |

URL 失效、页面更新或重新分块都不得破坏已有 Evidence Reference。被 fact、claim 链路或报告引用的 Document Version 默认不得物理删除；法规要求删除时保留引用失效状态和原因。

### 5.2 Evidence Candidate

以下对象不能直接成为 Evidence Reference：

- 搜索引擎摘要；
- 未抓取正文的 URL；
- 无附件、无快照的人工陈述；
- 无法在 Document Version 中定位的模型生成 snippet。

它们可以驱动后续抓取或人工补充，但不能激活 fact，也不能作为报告 citation。

### 5.3 Fact Evidence

`fact_evidence` 表达 Evidence Reference 相对于 Intel Fact 的关系：

| 字段 | 语义 |
|---|---|
| `fact_id` | Intel Fact 真实外键 |
| `evidence_ref_id` | Evidence Reference 真实外键 |
| `stance` | supports、contradicts 或 contextual |

`stance` 属于关系。Evidence Reference 不再保存多态 `owner_type/owner_id`、`role` 或 `relevance_score`。

### 5.4 验证状态

事实验证不计算综合分数：

- `self_reported`：支持证据主要来自事实主体控制的来源。
- `single_source`：只有一个独立 Document Cluster 提供正式支持证据。
- `corroborated`：至少两个相互独立且合格的 Document Cluster 提供支持证据。
- `disputed`：存在需要裁决的实质反证。

同一 Document Cluster 下的多个 Source Occurrence 只算一个来源。来源归属和独立性来自 Source Profile、Source Occurrence、Document Cluster 与事实主体关系，不在 Evidence Reference 上复制一套 Evidence Role 分类。

## 6. Insight Claim

### 6.1 语义

Insight Claim 是分析者基于 facts 得出的可争辩结论。`trend`、`comparison`、`risk` 和 `opportunity` 可能同时成立，因此它们是可选标签，不是互斥 `claim_type`。

目标字段：

| 字段 | 语义 |
|---|---|
| `id` | 稳定结论身份 |
| `claim_text` | 完整分析结论 |
| `tags` | trend、comparison、risk、opportunity 等可选组织标签 |
| `limitations` | 适用边界、未知项和反例说明 |
| `maturity` | draft、hypothesis、supported、needs_review、disputed 或 superseded |
| `status_reason` | 当前成熟状态的可解释理由 |
| `approved_by` / `approved_at` | supported 结论的人工批准责任 |
| `supersedes_claim_id` | 新结论对旧结论的显式取代关系 |
| `created_by` | 创建结论的用户或 Agent 身份 |
| `created_at` / `updated_at` | 领域对象持久化时间 |

删除单选 `claim_type`、`dimension`、`confidence_score`、竞品/产品 JSON ID 数组和 evidence refs 数组。结论的竞品/产品范围默认从关联 facts 推导；比较目标等分析范围可以作为显式 scope，但不复制事实归因。

### 6.2 Claim Facts

`claim_facts` 使用真实外键连接 claim 与 fact，并保存关系语义：

| 字段 | 语义 |
|---|---|
| `claim_id` | Insight Claim 真实外键 |
| `fact_id` | Intel Fact 真实外键 |
| `stance` | supports、contradicts 或 contextual |

不保存贡献权重或置信度。supported claim 至少需要一个非 disputed 的 active fact 作为 supports，且必须人工批准。Agent 可以自动创建 hypothesis，不能自动批准 supported。

### 6.3 不直接关联 Evidence

首版不建立 `claim_evidence`。Claim 和报告沿 `claim_facts -> fact_evidence -> evidence_refs` 获取原文；需要引用某段措辞时，先形成可观察的原子 fact。这个约束防止事实层逐渐被绕过。

### 6.4 生命周期

- draft 和 hypothesis 可编辑。
- supported 后冻结 `claim_text`、scope 和 `claim_facts`。
- 支撑 fact 进入 disputed、retracted 或 superseded 时，claim 自动进入 needs_review。
- 复核可以恢复 supported、转为 disputed，或创建新 claim 取代旧 claim。
- 历史报告继续引用当时的 claim 和 evidence 快照，并可提示其当前状态已变化。

## 7. 竞品与产品归因

沿用独立关系表以获得真实外键，不引入 `entity_type/entity_id` 多态关系：

- `fact_competitors(fact_id, competitor_id, role, review_status)`
- `fact_products(fact_id, product_id, role, review_status)`

`role` 只使用 subject、counterpart 或 mentioned；`review_status` 只使用 confirmed 或 needs_review。active fact 至少有一个 confirmed subject。常规竞品档案和时间线只聚合 subject，关系分析可以显式包含 counterpart 和 mentioned。

## 8. 时间语义

- `occurred_at` 表达一次性现实事件发生时间。
- `valid_from/valid_to` 只用于价格、可用性等持续事实。
- `observed_at` 属于采集与证据观测，不替代事实的现实时间。
- 时间线按 `occurred_at` 或 `valid_from` 排序；缺少现实时间的 fact 只进入发现时间视图。
- `time_precision` 防止模型把月份、季度或未知时间伪造成具体日期。

首版不建立 Intel Event。只有出现事件级订阅、合并拆分、独立属性或报告引用需求后，才重新评估 Event 实体。

## 9. 事实解析与激活

### 9.1 保守事实解析

`candidate_key` 只用于召回候选，例如规范主体、粗 fact type 和时间桶的组合。随后比较 `fact_text`、`normalized_data` 和时间范围，产生三个业务结果：

- same：把新 Evidence Reference 连接到已有 fact；
- different：创建新 fact；
- uncertain：保持为独立 draft 并进入复核。

`candidate_key` 不设全局唯一约束。价格、日期、版本、地区或套餐等关键限定条件冲突时禁止自动合并。错误合并必须能够拆分并恢复原始 evidence 关系。

### 9.2 确定性激活门禁

Fact 满足以下条件后可以自动 active：

1. `fact_text` 是完整原子命题；
2. 至少一个 confirmed subject；
3. 至少一条正式 Evidence Reference；
4. 引用可在对应 Document Version 中校验；
5. 高价值类型的 `normalized_data` 通过对应 schema 校验；
6. 未发现关键限定条件冲突；
7. 事实解析结果不是 uncertain。

未通过时保留 draft 并写入明确 `status_reason`。不使用数值阈值决定领域状态。

## 10. 持久化与运行可观测性

三个核心模型只保存当前领域状态以及脱离 trace 后仍必须存在的信息：

- `created_by`；
- claim 的 `approved_by/approved_at`；
- `supersedes_*_id`；
- `status_reason`；
- Evidence Reference 的不可变来源定位。

模型调用、Prompt 版本、候选列表、规则执行步骤、工具调用、耗时和完整输入输出进入 trace 或结构化日志。不新增通用 `audit_events` 或 `extraction_runs` 业务表。

## 11. 当前实现差异

迁移尚未完成，当前实现存在以下目标差异：

- Intel Fact 仍包含 `fact_kind`、`dimension`、自由文本三元组以及 importance/confidence score。
- 当前 `assertion_key` 是确定性哈希，尚未实现候选召回、语义判定和可复核拆分。
- Evidence Reference 仍使用 `owner_type/owner_id`，并保存 role、stance 和 relevance score。
- Insight Claim 仍使用单选类型、JSONB fact/竞品/产品 ID 数组、confidence score 和直接 evidence。
- active fact 与 claim 仍可通过 upsert 原地改写语义。
- 当前 Protocol、Agent 工具和 API 仍暴露上述旧字段。

实施时应采用新增关系和切换读写路径的迁移顺序。现有结构化 facts/claims 可从保留的 Document Version 和 Evidence Reference 重建，不应通过猜测把旧 JSON ID 或 score 转换成新领域语义。

## 12. 验收标准

- 顶层文档和产品语言只出现 Evidence Reference、Intel Fact、Insight Claim 三个核心层。
- PostgreSQL 对 fact-evidence、claim-fact、fact-competitor 和 fact-product 关系建立真实外键。
- active fact 不存在无正式 evidence、无 confirmed subject 或不可定位 quote 的情况。
- supported claim 不存在直接 evidence 或缺少 supporting active fact 的情况。
- active fact 和 supported claim 的语义字段不能原地更新。
- 三层对象及关系中不存在业务 score。
- 同一 Evidence Reference 可以支持或反驳多个 facts，而不复制原文锚点。
- 报告可以从 claim 逐层回溯到 Document Version 中的逐字引用。
