# InsightForge Competitive Intelligence

InsightForge 将分散的公开信息整理为可追溯的竞品事实与分析结论。本上下文统一采集、去重、来源治理和证据验证所使用的领域语言。

## 来源治理

**Information Source（信息来源）**:
发布或承载内容的组织、个人、媒体或平台身份，通常以规范化域名识别。
_Avoid_: Feed、Crawler Site、URL

**Source Profile（来源档案）**:
对一个 Information Source 的受治理描述，包含来源类型、归属方、Source Tier、状态及评级依据。
_Avoid_: 抓取配置、来源分数

**Source Tier（来源等级）**:
来源主体的离散可信等级：A、B、C、D 或 unknown；等级描述来源基础属性，不直接表示某条事实已经被验证。
_Avoid_: source_reliability、可信度分数、置信度

**Evidence Role（证据角色）**:
某条证据相对于特定 Intel Fact 的语境角色：primary、independent、interested_claim、community_report、aggregator 或 unknown。
_Avoid_: 来源等级、证据类型

## 文档与去重

**Source Occurrence（来源实例）**:
一篇内容在某个 Information Source 上的一次具体发布或抓取观测，拥有自己的 URL、发布时间、内容指纹和来源等级快照。
_Avoid_: 副本、重复文档、Source Document

**Document Cluster（文档簇）**:
由完全重复或高度重合的 Source Occurrence 组成的内容族；同一事件的独立报道不属于同一文档簇。
_Avoid_: 事件簇、主题簇

**Canonical Article（主文章）**:
Document Cluster 当前保留完整正文并进入知识处理流程的 Source Occurrence；更优来源可以晋升为新的主文章。
_Avoid_: 原文、第一篇文章、永久主文档

**Document Version（文档版本）**:
Document Cluster 在某一时刻生效的主文章内容版本；新版本完成派生数据构建后才取代旧版本。
_Avoid_: 抓取版本、Source Occurrence

**Duplicate Candidate（重复候选）**:
被内容指纹召回、但尚未确认应归入同一 Document Cluster 的 Source Occurrence 关系。
_Avoid_: 重复文档、已合并文档

## 事实与证据

**Intel Fact（情报事实）**:
独立于单篇文档的规范化竞品事实或事件，可由多个 Evidence Reference 支持、反驳或限定。
_Avoid_: 文档事实、文章摘要、Claim

**Evidence Reference（证据引用）**:
Intel Fact 或分析结论到具体 Document Version、Source Occurrence 和原文片段的可审计引用。
_Avoid_: 链接、来源列表

**Verification Status（验证状态）**:
Intel Fact 的证据验证结果：unverified、self_reported、corroborated 或 disputed；它与编辑工作流状态相互独立。
_Avoid_: Fact Status、来源等级、置信度分数
