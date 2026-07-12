---
status: accepted
---

# 使用版本化的确定性清洗流水线

正文清洗从抓取任务中分离为独立、可重放的 Normalize 阶段。来源专用 selector、结构化元数据、`markdownify`、`trafilatura`、纯文本回退等提取策略可以产生多个候选，由版本化的确定性质量评估选择结果；固定字符数不再单独决定文章是否可入库。LLM 只能辅助页面类型判断和异常元数据修复，不得改写作为 Evidence Reference 基础的逐字正文。

## Consequences

- 每次清洗必须记录 normalizer、规则与提取器版本，以及候选检测事实、原因码与最终选择理由；不记录统一候选分数。
- 低质量结果进入静态重试、浏览器渲染或治理队列，不直接进入 Document Cluster 和知识索引。
- 现有 `NewsMarkdownConverter` 的多候选选择与 `semantic_blocks` 只用于提取回放夹具和预期行为；新 Normalize 实现不保留该类的运行时兼容接口，切换后可以直接删除。
- 清洗质量必须通过固定原始页面夹具重放测试，规则升级不得依赖重新访问外部网站。
- Normalized Document 以有序 Content Block 为权威表示；每个 block 保存稳定 ID、逐字文本、类型、标题路径、源 DOM 定位和提取器。Markdown 从 Content Block 派生，用于展示、分块和 LLM，不作为唯一证据锚点。
- 清洗重跑创建新的规范化版本而不原地覆盖；Evidence Reference 引用具体版本和稳定 Content Block。
- 清洗门禁只输出 `accepted`、`retry_render`、`review_required` 或 `rejected` 的 Normalization Outcome 及原因码。领域模型不保存统一数值分数；各检测器的长度、密度或相似度测量只用于诊断和规则解释。
- 现有 `semantic_confidence` 属于待迁移字段，不得继续作为入库接口。
- 去重分三层执行：抓取前使用规范化 URL、来源游标和 HTTP 条件请求；抓取后使用 Raw body SHA-256 复用已有 Normalized Document；清洗后使用 Content Block 规范化正文的 SHA-256、SimHash 和 shingles 作为 Document Cluster 的权威内容判断。Raw body hash 只用于计算复用，不得直接决定内容归簇。
