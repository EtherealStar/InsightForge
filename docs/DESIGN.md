# 设计哲学

Logos 的架构设计围绕以下核心原则构建。详细设计文档见 [design-docs/](design-docs/index.md)。

---

## 核心设计原则

### 1. Protocol 优先

所有基础设施组件通过 `typing.Protocol` 定义接口契约。替换实现时只需修改 `core/factory.py` 的工厂函数，上层 Services 和 Delivery 无需改动。

→ 详见 [Protocol 接口契约](design-docs/protocol-contracts.md)

### 2. 分层架构 + 单向依赖

```
Frontend → Delivery → Agent/Tools → Services → Infrastructure
                                                    ↑
                                              implements Core/Protocols
```

每一层只依赖其下方的层，`Models` 和 `Core` 被所有层引用。

### 3. 工厂函数 + ConfigManager 单例

不使用 DI 框架。`core/factory.py` 提供基础设施和 Service 层工厂函数，`ConfigManager` 缓存组件实例并支持热重载。

→ 详见 [技术决策 ADR-002](design-docs/tech-decisions.md#adr-002-工厂函数而非-di-容器)

### 4. 手动 ReAct 而非 Function Calling

为兼容 4 种 LLM 后端，采用手动 prompt + 输出解析实现 ReAct Agent，牺牲 function calling 的便利性换取跨模型兼容性和推理过程透明度。

→ 详见 [ReAct Agent 设计](design-docs/react-agent.md)

---

## 设计文档导航

- [技术选型论证](design-docs/tech-decisions.md) — 每个选型的完整 trade-off 分析
- [Protocol 接口契约](design-docs/protocol-contracts.md) — 核心接口的详细设计
- [ReAct Agent 设计](design-docs/react-agent.md) — Agent 推理循环与工具系统
- [架构变更历史](design-docs/changelog.md) — 所有重大架构变更记录
- [来源治理与近重复检测](design-docs/source-governance-and-deduplication.md) — 来源分级、SimHash 去重、主来源晋升与证据验证目标设计
