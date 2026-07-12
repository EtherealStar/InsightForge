---
status: accepted
---

# 以三层核心模型承载结构化情报

InsightForge 将 Evidence Reference、Intel Fact 和 Insight Claim 定义为三个核心领域概念：证据是不可变原文锚点，事实是跨来源原子命题，结论只能通过事实间接溯源。数据库可以使用必要的关联表表达多对多关系，但不得把关联表提升为新的领域层，也不得用多态 owner 或 JSON ID 数组牺牲引用完整性；该选择以更多内部关系换取证据复用、真实外键和稳定审计语义。

## Consequences

- Intel Fact 和 supported Insight Claim 激活后不原地改变语义，更正通过显式取代关系完成。
- Insight Claim 不直接关联 Evidence Reference；搜索摘要、裸 URL 和无附件人工输入只是 Evidence Candidate。
- 三层领域及其关系不保存 importance、confidence 或 relevance 等业务评分，可信判断使用可解释状态。
- 顶层架构和产品语言始终展示三个核心概念；关联表只属于持久化实现。
