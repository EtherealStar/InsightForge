# 来源治理、近重复检测与证据验证设计

> 状态：目标设计，尚未实现
>
> 决策日期：2026-07-12
>
> 领域语言：[CONTEXT.md](../../CONTEXT.md)
>
> 架构决策：[ADR-0001](../adr/0001-stable-document-clusters-and-source-occurrences.md)

## 1. 背景

当前采集 Pipeline 在 Markdown 转换后直接将每篇文章保存为 `SourceDocument`，其 ID 由 URL 生成；`content_hash` 只被保存，没有参与入库判重。事实抽取仍为“每文档一组 facts”，`source_reliability` 是不可解释的浮点字段，无法表达来源身份、证据语境和跨来源互证。

目标是在 Celery 并发采集链路中建立两项能力：

1. 使用精确哈希、SimHash 和正文 shingle 相似度识别转载或轻改稿，避免重复存储与重复计算。
2. 使用来源档案、离散来源等级、证据角色和验证状态管理信息可信性，并保持完整审计链路。

本文描述目标模型，不表示当前代码已经具备这些能力。

## 2. 设计原则

- **保守去重**：只合并转载、换标题、删减少量段落或轻度编辑的同一篇文章；同一事件的独立报道必须保留。
- **一个正文，多条溯源**：每个 Document Cluster 只保留一个生效主正文，其他 Source Occurrence 长期保留轻量来源元数据。
- **后到优胜**：更可信且内容足够完整的来源可以晋升为 Canonical Article。
- **相关性与可信性分离**：检索相关性、来源等级、抽取可靠性和事实验证状态不得混成一个分数。
- **离散且可解释**：删除 `source_reliability`；所有可信判断必须能回溯到等级、角色、证据和理由。
- **PostgreSQL 权威、Redis 可重建**：缓存故障不得改变最终去重结果或丢失审计数据。
- **精确率优先**：自动合并宁可漏判，不可误合并独立报道。

## 3. 范围与非目标

### 3.1 范围

- RSS、网页爬虫及其他进入长期知识库的文章来源。
- 来源档案和评级历史。
- 文档完全重复、近重复、主来源晋升和同 URL 内容更新。
- 全局 Intel Fact、不可变 Evidence Reference、fact-evidence 立场和 Verification Status。
- Redis 热点索引、PostgreSQL 最终一致性和 Celery 对账/清理任务。
- 来源、重复候选和证据冲突的最小治理界面。

### 3.2 非目标

- SimHash 不用于事件聚类、主题聚类或语义相似报道合并。
- Web Search 临时结果不会绕过来源准入自动进入长期知识库。
- LLM 不参与文档近重复判定。
- 不维护统一的来源可信度或事实可信度浮点总分。
- 不为现有文档和派生数据设计复杂回填；现有文档数据允许清除后按新模型重建。

## 4. 领域模型

### 4.1 Source Profile

`SourceProfile` 是来源治理的权威对象，至少包含：

| 字段 | 含义 |
|---|---|
| `id` | 稳定标识 |
| `domain` | 规范化域名，唯一 |
| `display_name` | 展示名称 |
| `source_kind` | `official`、`editorial_media`、`community`、`aggregator` |
| `tier` | `A`、`B`、`C`、`D`、`unknown` |
| `owner_competitor_id` | 可选，来源归属的竞品 |
| `inherit_to_subdomains` | 是否允许子域继承；必须显式配置 |
| `status` | `active`、`pending_review`、`disabled` |
| `rating_reason` | 当前评级依据 |
| `rated_by` / `rated_at` | 评级审计信息 |

`SourceProfileRevision` 保存每次等级、类型、归属和状态变化，文章入库时保存来源档案快照。后续修改来源档案不得悄然改写历史证据语义。

抓取配置回答“去哪里抓”，Source Profile 回答“这个来源是谁”。RSS feed 和 crawler site 必须绑定 Source Profile 才能进入正式知识 Pipeline。

### 4.2 Source Tier

| 等级 | 定义 | 默认处理路径 |
|---|---|---|
| A | 一手官方来源、正式公告或官方文档 | 入库、向量化、事实抽取 |
| B | 有编辑审核的权威或专业媒体 | 入库、向量化、事实抽取 |
| C | 社区、个人博客、论坛或可识别作者的二手内容 | 入库、向量化、事实抽取；检索轻微降权 |
| D | 已审核确认缺乏可靠溯源、低质量聚合或低质量转载的来源 | 隔离；Raw Fetch Artifact body 最多保留 24 小时 |
| unknown | 尚未评级，不等同于 D | `pending_review`；不向量化、不抽取 fact |

C 级来源在混合检索后使用 `0.85` 的可信先验权重，但单个 C 级证据不能令 Intel Fact 成为 `corroborated`。D 和 unknown 文档不进入 Qdrant、全文索引或事实抽取。

### 4.3 Document Cluster 与 Source Occurrence

`SourceDocument` 的目标语义调整为稳定的 Document Cluster，而非某个 URL。建议持久化对象如下：

#### `source_documents`

保存稳定簇身份、当前生效版本、状态及聚合信息，不再由 URL 派生 ID。

#### `source_document_occurrences`

每个具体发布来源一条记录，至少包含：

- `document_id`
- `source_profile_id`
- `url`、`canonical_url`、`title`、`author`
- `published_at`、`first_seen_at`、`last_seen_at`
- `content_hash`、`simhash64`、SimHash 算法版本
- 四个 16 位高精度 band 与八个 8 位灰区 band
- 正文长度、语言和来源等级快照
- `dedup_method`、汉明距离、shingle 相似度和判定状态
- 是否为当前 Canonical Article

URL 具有唯一约束。同一 URL 再次抓取时先比较内容版本，而不是直接覆盖或跳过。

#### `source_document_versions`

保存每次主文章生效所需的正文、指纹、主 occurrence、构建状态和版本号。每个 Document Cluster 只能有一个 active version。

#### `duplicate_candidates`

保存灰区候选关系、算法版本、各相似度信号、自动建议、人工结论和审计信息。人工结论为 `merge` 或 `keep_separate` 后，可作为阈值校准样本。

## 5. 去重算法

### 5.1 处理位置

去重位于 Normalization Outcome 为 accepted 之后、Document Version 入库和任何分块/Embedding/LLM 调用之前。抓取、artifact 与 Content Block 规则见 [来源采集与内容清洗设计](collection-and-normalization.md)：

```text
Source Connector
  -> Fetch Candidate
  -> Raw Fetch Artifact
  -> Normalized Document + Content Blocks
  -> accepted outcome
  -> source admission gate
  -> exact hash + SimHash candidate retrieval
  -> shingle verification
  -> cluster / occurrence decision
  -> active version build
  -> parent-child chunking
  -> Qdrant + PostgreSQL FTS
  -> global fact extraction and evidence binding
```

### 5.2 正规化与特征

- 正文去除 Markdown 格式符、链接目标、重复空白和已知通用模板，但保留实际可见文字。
- 中文使用字符 3-gram；英文使用单词 3-shingle；混合文本组合两类特征。
- 正文 SimHash 是主要指纹；标题相似度单独计算，只作辅助。
- 短文本不自动近重复合并，进入独立文章或人工复核路径。
- 保存 `normalization_version`、`simhash_version` 和 `shingle_version`，支持重算和审计。

### 5.3 两阶段判定

1. `SHA-256` 相同：确定为完全重复。
2. 使用 64 位 SimHash 的 `4 x 16-bit` 高精度索引与 `8 x 8-bit` 灰区索引召回候选。
3. 计算完整汉明距离。
4. 对距离 `0-6` 的候选计算正文 shingle Jaccard/containment、正文长度比例和标题相似度。
5. 高置信候选自动归簇，灰区写入 `duplicate_candidates`，其余创建新簇。

初始汉明距离分段为：

| 距离 | 初始处理 |
|---|---|
| `0-3` | 高概率近重复，仍需通过正文重合和长度条件 |
| `4-6` | 疑似重复，正文重合度明确时自动判断，否则人工复核 |
| `>6` | 默认独立文章 |

阈值不是永久常量。正式删除重复正文前必须先用离线人工标注夹具校准；自动合并精确率目标不低于 98%。校准不依赖旧 Crawlee 或生产 shadow 双轨。

### 5.4 全历史候选检索

候选检索不设置严格时间窗口。旧文章数月后被转载仍应归入原簇。`4 x 16-bit` 布局保证汉明距离不超过 3 时至少有一个完整 band 相同；为避免遗漏距离 4-6 且变化分散在四个 band 中的灰区候选，同时维护 `8 x 8-bit` 布局，并要求至少两个 8 位 band 相同后才进入灰区复核。PostgreSQL 为两套布局建立索引，Redis 保存近期和高频 band 的可重建集合；发布时间差只作为判定特征，不作为硬过滤条件。

### 5.5 同 URL 更新

- 哈希相同：仅更新 `last_seen_at`。
- 轻微模板变化：记录观测，不创建版本。
- 实质内容变化：创建 Document Version，完成派生数据构建后原子切换。
- URL 被复用于完全不同内容：创建新 Document Cluster，并记录 `url_reused` 审计事件。
- 价格页、更新日志等可配置 `versioned_content=true`，采用更敏感的变化阈值。

## 6. Canonical Article 选择与晋升

候选必须先通过正文完整性和抽取质量底线，再按以下顺序比较：

1. Source Tier 更高者优先。
2. 同等级下正文信息更完整者优先。
3. 仍相同时发布时间更早者优先。
4. 再相同时保留当前主文章，避免反复晋升。

高等级候选正文不足当前正文长度的 70% 时，不自动晋升，只创建治理候选。阈值需要通过实际样本校准。

晋升采用版本化构建：

1. 创建下一 Document Version，状态为 `building`。
2. 生成带版本标识的 parent chunks、Qdrant points 和 evidence candidates。
3. 完成事实抽取与证据重绑定。
4. 在 PostgreSQL 事务中切换 `active_version`。
5. 检索始终只读取 active version。
6. 异步删除旧 Qdrant points；旧 Document Version 被 Evidence Reference 或报告引用时保留正文，否则按清理策略回收。清理失败不影响当前版本服务。

旧 Source Occurrence 的 URL、指纹、来源快照、判定理由和晋升历史永久保留，旧重复正文无需永久保留。

## 7. Redis 与 PostgreSQL 的职责

### 7.1 Redis

Redis 是高速、可丢失、可重建的前置层：

- 规范化 URL 幂等缓存。
- `content_hash -> document_id` 热点映射。
- `simhash_version + band -> document_ids` 热点候选集合。
- Source Profile 域名缓存。
- Celery 状态、短期协调和退避信息。

Redis 不保存唯一的重复结论、来源评级历史或主版本状态。缓存淘汰只允许造成降速，不得造成数据丢失。

### 7.2 PostgreSQL

PostgreSQL 保存全部权威状态：Source Profile、评级历史、Document Cluster、Source Occurrence、Document Version、Duplicate Candidate、全历史 band 索引、晋升审计、Intel Fact 和 Evidence Reference。

并发去重按 SimHash 候选分区获取有序的 PostgreSQL advisory transaction locks。高精度自动合并路径至少锁定四个 16 位 band；灰区索引用于候选发现和后续对账，不把 Redis 分段锁当作正确性边界。无关文章使用不同 band，不相互阻塞；数据库事务内完成候选复查、归簇、新建簇和 occurrence 写入。

Celery Beat 定期运行重复簇对账任务，修复 Worker 超时、缓存不一致或异常重试造成的漏合并。分布式协调只能降低冲突概率，后台对账提供最终一致性。

## 8. Evidence Reference 与事实验证

### 8.1 全局 Intel Fact

Intel Fact 表示跨来源的规范化原子命题，不从属于单个 `source_document_id`。多个独立 Document Cluster 通过 Evidence Reference 支持或反驳同一个 fact；Event 不是独立事实类型，趋势和信号属于 Insight Claim。

事实解析采用保守的两阶段流程。系统先以规范主体、七类粗 `fact_type` 和时间桶组成的 `candidate_key` 召回候选，再比较 `fact_text`、可选 `normalized_data` 和时间范围，产生：

- `same`：新 evidence 连接到已有 fact；
- `different`：创建新 fact；
- `uncertain`：保持独立 draft，等待复核。

`candidate_key` 不是事实身份，不设全局唯一约束。价格、日期、版本、地区或套餐等关键限定条件冲突时禁止自动合并；模型判断、候选和理由进入 trace，规则冲突或输出不完整时降级为 uncertain。

### 8.2 Evidence Reference 与关系立场

Evidence Reference 是指向不可变 Document Version、具体 Source Occurrence 和逐字原文位置的可复用锚点。`parent_chunk_id` 和 URL 只辅助检索与展示；重新分块、页面更新或 URL 失效不得破坏已有引用。

证据相对于 fact 的语义保存在 `fact_evidence` 关系，而不是 Evidence Reference 自身：

| stance | 含义 |
|---|---|
| `supports` | 原文直接支持事实命题 |
| `contradicts` | 原文对事实命题形成实质反证 |
| `contextual` | 原文提供背景，但不能独立证明命题 |

来源是否由事实主体控制、是否属于独立报道、是否只是转载，由 Source Profile、Source Occurrence、Document Cluster 与 fact 主体关系共同判定，不在 Evidence Reference 上复制 `primary/independent/aggregator` 等角色。搜索摘要、裸 URL 和无附件人工输入只是 Evidence Candidate，必须完成正文快照和引用定位后才能成为正式 evidence。

### 8.3 Verification Status

`lifecycle_status` 表达事实是否可被系统使用以及是否仍生效：draft、active、superseded、retracted 或 rejected。`verification_status` 独立表达当前证据验证结果：

| 状态 | 含义 |
|---|---|
| `self_reported` | 主要由事实主体自己的来源陈述 |
| `single_source` | 只有一个独立 Document Cluster 提供正式支持证据 |
| `corroborated` | 至少两个独立且合格的证据来源相互支持 |
| `disputed` | 存在实质冲突证据 |

同一 Document Cluster 中的多个 Source Occurrence 只计为一个证据来源。单个 C 级来源不能得到 `corroborated`。事实通过原子性、主体归因、正式 evidence、引用定位、类型 schema 和冲突检查等确定性门禁后可以自动 active；验证状态由 evidence 关系派生，不接受 LLM 直接填写。

删除 `source_reliability` 以及 fact/evidence/关联关系上的 confidence、importance 和 relevance 业务 score。系统保留 Source Tier、来源归属、Evidence Stance、Verification Status 和解释原因，不计算统一权威总分。完整三层模型见 [structured-intelligence-model.md](structured-intelligence-model.md)。

## 9. 检索策略

现有向量和关键词通道先按相关性召回，再由 RRF 融合。来源等级调整位于 RRF 或可选 reranker 之后：

```text
final_score = relevance_score * trust_weight
```

初始权重：A=`1.00`、B=`0.95`、C=`0.85`。为避免降权候选占满截断窗口，最终需要 `top_k` 条时应先过量召回，例如 `top_k * 3`，应用来源权重后再截断。D、unknown、非 active Document Version 通过过滤条件排除。

该权重仅是检索先验，不等同于事实可信判断。事实是否可以用于报告结论仍由 Evidence Stance、来源独立性、Verification Status 和报告质量门禁决定。

## 10. 服务与 Protocol 边界

遵循 Protocol 优先和单向依赖约定，目标边界如下：

- `SourceProfileStoreProtocol`：来源档案、修订历史、域名解析和快照读取。
- `DocumentDedupStoreProtocol`：候选查找、短事务归簇、occurrence、版本和判定审计。
- `DedupCacheProtocol`：URL、精确哈希、SimHash band 和来源档案缓存；Redis 实现。
- `DocumentDedupService`：纯业务编排，负责正规化、指纹、相似度、主文章选择和决策结果。
- `SourceGovernanceService`：来源准入、评级修改、继承规则和审核队列。
- `DocumentVersionService`：版本构建、原子切换、失败回滚和旧派生数据清理。
- `EvidenceVerificationService`：Evidence Stance 校验、来源独立性判定和 Verification Status 计算。

不要把上述职责继续堆入 Collection Orchestrator 或扩张现有 `DocumentStoreProtocol` 成为一个包含所有治理行为的宽接口。`ingest` 阶段只消费 accepted Normalized Document，并接收明确的领域结果：`new_cluster`、`duplicate`、`review_required`、`canonical_promoted`、`quarantined` 或 `unchanged`。

## 11. Celery 任务

采集与清洗先按 [来源采集与内容清洗设计](collection-and-normalization.md) 拆分为 `fetch.http`、`fetch.browser`、`normalize`、`ingest`、`enrich` 和 `ocr` 队列。本设计负责的后续任务包括：

- 单文章准入/去重任务：来源门禁、指纹和短事务归簇。
- Document Version 构建任务：分块、Embedding、Qdrant、FTS 和事实抽取。
- 主来源晋升任务：构建新版本并原子切换。
- 重复簇对账任务：发现并合并异常漏网簇。
- artifact 清理任务：删除超过 24 小时且未晋升的 Raw Fetch Artifact body，保留轻量审计元数据。
- Redis 索引重建任务：从 PostgreSQL 重建热点键。

任务必须幂等，使用稳定 idempotency key；重试不得重复创建 occurrence、版本或 Evidence Reference。

## 12. 治理 API 与界面

第一版必须包含可操作的最小治理工作台：

- Source Profile CRUD、评级原因和修订历史。
- unknown 来源的 `pending_review` 队列与批量评级。
- Duplicate Candidate 的标题、来源、正文差异、汉明距离和 shingle 相似度对比。
- `merge`、`keep_separate`、`promote_source` 操作。
- Evidence Stance、来源独立性和 disputed fact 审核。
- 所有人工操作记录操作者、理由、时间及前后值。

批量操作适用于来源评级；文档簇合并与拆分默认逐条确认。治理界面不得把算法阈值或内部字段作为唯一解释，必须展示原文差异和判定理由。

## 13. 可观测性与验收

至少记录以下指标：

- 抓取数、准入数、隔离数、新簇数、完全重复数、近重复数和灰区数。
- 自动合并精确率、人工推翻率、疑似漏判率。
- 每个簇 occurrence 数、主来源晋升次数和构建失败次数。
- Redis 命中率、PostgreSQL 候选查询延迟、band 热点分布和锁等待时间。
- D/unknown 误入 Qdrant 或事实抽取的数量，目标为 0。
- `single_source`、`self_reported`、`corroborated`、`disputed` facts 分布。
- Evidence Stance 冲突率、来源独立性待复核量和 disputed fact 数量。

正式启用自动正文删除前，离线标注夹具与并发演练必须满足；不保留旧 Crawlee 生产链路做 shadow 双轨：

- 自动近重复合并精确率 `>= 98%`。
- 完全重复识别率 `= 100%`。
- 同一事件独立报道误合并率接近 0。
- 并发重复输入不会产生多个权威 Document Cluster，或能被对账任务稳定修复。
- Redis 清空后可从 PostgreSQL 重建，且去重结论不发生变化。
- 主来源晋升失败时旧版本仍可检索。

## 14. 分阶段交付

1. **采集与规范化底座**：按新设计直接替换 Crawlee/全局 Pipeline，提供 accepted Content Block 输入。
2. **基础治理模型**：Source Profile、评级历史、Document Cluster、Source Occurrence、Document Version、Protocol 和 PostgreSQL Store。
3. **离线去重校准**：使用固定标注夹具校准 SHA-256、SimHash 和 shingle 规则，不运行旧/新双轨生产写入。
4. **正式去重**：Redis 前置索引、PostgreSQL 分段锁、重复归簇和 24 小时 artifact 清理。
5. **主来源晋升**：版本化构建、原子切换、失败回滚和后台对账。
6. **可信证据与治理**：全局 Intel Fact、不可变 Evidence Reference、Verification Status、检索调整、治理界面和指标。

每个阶段必须先完成存储与服务层测试，再接入下一个队列。离线标注结论是启用自动近重复归簇的前置条件，但不要求保留旧 Crawlee 或旧 Pipeline 运行路径。
