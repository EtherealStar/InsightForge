---
status: accepted
---

# 使用稳定文档簇承载可晋升的主文章

采集到的 URL 不再直接充当知识文档身份。系统以稳定的 Document Cluster 标识高度重合的内容族，以 Source Occurrence 记录每个具体发布来源，并仅让当前 Canonical Article 的 Document Version 进入分块、向量化和事实抽取；更高等级且内容足够完整的后到来源可以通过新版本构建和原子切换晋升。该选择牺牲了“URL 即文档”的简单性，换取跨来源去重、来源溯源、无损晋升和多来源证据治理的一致模型。

## Consequences

- PostgreSQL 是文档簇、来源实例、版本和晋升历史的权威存储；Redis 仅保存可重建的热点索引与幂等缓存。
- 重复来源只长期保留轻量元数据，避免重复分块、向量化和事实抽取。
- Intel Fact 不再从属于单篇文档，而由多个可追溯 Evidence Reference 支持。
- 现有 URL 派生 `source_documents.id` 的实现属于待替换基线；当前文档数据允许清除，不要求兼容回填。

