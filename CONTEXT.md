# InsightForge Competitive Intelligence

InsightForge 将分散的公开信息整理为可追溯的竞品事实与分析结论。本上下文统一采集、去重、来源治理和证据验证所使用的领域语言。

## 采集与处理

**Collection Run（采集运行）**:
针对一组来源在同一调度周期内发起、可独立追踪和汇总的采集批次。
_Avoid_: 全局 Pipeline、批处理任务

**Source Fetch Task（来源抓取任务）**:
面向单个 Source Profile 的一次可重试抓取工作单元，拥有自己的游标、限速、超时和结果状态。
_Avoid_: 爬虫任务、站点线程

**Fetch Candidate（抓取候选）**:
由来源连接器发现、已具备规范化地址和来源上下文但尚未取得响应内容的资源线索。
_Avoid_: Raw Fetch Artifact、Source Occurrence、搜索摘要

**Raw Fetch Artifact（原始抓取产物）**:
抓取阶段保留的原始响应及其请求、来源、时间和响应元数据，尚未经过正文清洗或知识入库。
_Avoid_: Source Document、文章正文

**Retained Fetch Artifact（保留抓取产物）**:
已成为 Document Version 的原始依据或被 Evidence Reference 引用、因而越过短期清理期限保存的抓取产物。
_Avoid_: 全量抓取归档、普通 Raw Fetch Artifact

**Normalized Document（规范化文档）**:
同一 Raw Fetch Artifact 经特定版本清洗规则产生的结构化正文与元数据结果，由有序 Content Block 组成。
_Avoid_: Markdown 文件、Source Document、Raw Fetch Artifact

**Content Block（内容块）**:
Normalized Document 中具有稳定身份、逐字文本、内容类型、标题路径和原始定位的一段内容，是证据定位与 Markdown 渲染的基础。
_Avoid_: Child Chunk、任意字符切片、Markdown 段落

**Normalization Outcome（清洗结果）**:
对一次规范化处理能否进入后续知识流程的离散结论：accepted、retry_render、review_required 或 rejected，并附带可解释原因码。
_Avoid_: semantic_confidence、清洗分数、正文可信度

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
独立于单篇文档、可被单独证实或证伪的规范化原子命题；多个来源可以支持或反驳同一个 Intel Fact。
_Avoid_: 文档事实、文章摘要、Event、Signal、Claim

**Fact Type（事实类型）**:
Intel Fact 的唯一粗粒度分类：product、commercial、corporate、ecosystem、customer_market、risk 或 general；更细的主题只是可选标签。
_Avoid_: Fact Kind、Dimension、细粒度类型枚举

**Evidence Candidate（证据候选）**:
尚未取得可复核正文和精确原文定位的线索，例如搜索摘要、裸 URL 或无附件的人工输入。
_Avoid_: Evidence Reference、Citation

**Evidence Reference（证据引用）**:
指向具体 Document Version、Source Occurrence 和逐字原文位置的不可变证据锚点；它通过 Evidence Stance 与 Intel Fact 建立关系。
_Avoid_: 链接、来源列表、Evidence Candidate、Claim Evidence

**Evidence Stance（证据立场）**:
一条 Evidence Reference 相对于某个 Intel Fact 的作用：supports、contradicts 或 contextual；立场属于两者之间的关系，不属于证据自身。
_Avoid_: Evidence Role、来源等级、相关度分数

**Insight Claim（洞察结论）**:
分析者基于一个或多个 Intel Fact 形成的可争辩结论；它通过事实间接溯源，不直接把原文线索当作结论依据。
_Avoid_: Intel Fact、Signal、Summary

**Verification Status（验证状态）**:
Intel Fact 根据当前证据关系得到的离散结果：single_source、self_reported、corroborated 或 disputed；它与事实生命周期相互独立。
_Avoid_: Lifecycle Status、来源等级、置信度分数

**Lifecycle Status（生命周期状态）**:
Intel Fact 是否可被系统使用以及是否仍然生效的状态，例如 draft、active、superseded、retracted 或 rejected。
_Avoid_: Verification Status、可信度

**Claim Maturity（结论成熟度）**:
Insight Claim 从 draft、hypothesis 到 supported 的成熟状态；事实变化可令其进入 needs_review 或 disputed，旧结论可被新结论 supersede。
_Avoid_: Claim Type、置信度分数

**Supersession（取代关系）**:
新 Intel Fact 或 Insight Claim 对旧对象的显式更正关系；旧对象仍保留原有语义和历史引用。
_Avoid_: 原地覆盖、静默更新
