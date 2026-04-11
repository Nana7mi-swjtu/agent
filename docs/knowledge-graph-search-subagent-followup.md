# 知识图谱接入 Search Subagent 的后续说明

## 状态

本文档记录一次发生在 `adapt-knowledge-graph-to-refact-ui` 这个 OpenSpec 变更之后的实现调整。该调整没有继续回写到当时的 active change 中，而是单独作为仓库文档保留。

## 背景

原先的 active OpenSpec change 主要覆盖了以下内容：

- 合并仓库中的 `knowledge_graph` 目录及相关后端资产
- 扩展后端聊天契约，支持 `graph` 和 `graphMeta`
- 在前端 refactored chat 中渲染消息级知识图谱结果

在这些工作完成之后，运行时行为又做了一次额外调整：知识图谱检索不再通过 `app/agent/services.py` 中的专门旁路直接返回，而是并入现有的 `search_subagent` 执行链路，再由主 agent 基于结构化搜索结果做最终总结。

## 具体变更

### 1. 知识图谱查询改为在 `search_subagent` 内执行

运行时不再从 `app/agent/services.py` 直接短路返回知识图谱结果。现在的流程变为：

- planner 先判断当前请求是否需要证据检索
- `search_subagent` 根据请求触发 `knowledge_graph_query`
- 子代理把知识图谱结果归一化到统一 evidence contract
- 主 agent 基于 search subagent 返回的结构化结果生成最终回复

涉及的后端文件：

- `app/agent/graph/search.py`
- `app/agent/graph/nodes.py`
- `app/agent/graph/state.py`
- `app/agent/services.py`
- `tests/test_agent_subagent_orchestration.py`
- `tests/test_flows.py`

### 2. `graph` 和 `graphMeta` 继续沿用，并通过委托链路回传

新的委托式搜索路径会继续保留并回传：

- 前端用于渲染的图谱节点边数据
- 图查询元数据 `graphMeta`
- 分组后的来源信息，其中会在存在图谱结果时补充 `knowledge_graph` 类型的 source

### 3. 保留空消息 + `entity` / `intent` 的兼容行为

如果调用方没有传 `message`，但传了结构化的 `entity` 和 `intent`，后端会先合成一个有效查询文本，再进入 planner 路由。这样可以兼容之前已经存在的前端/API 调用方式。

## 为什么没有继续写回 OpenSpec

这次调整本质上属于“运行时编排方式优化”，不是最初那次 merge change 的核心范围。它改变的是能力在 parent-agent 工作流中的组合方式：

- 调整前：知识图谱能力可能绕过 planner / search composition
- 调整后：知识图谱能力作为 search subagent 的一种证据来源参与统一编排

这种做法在架构上一致性更好，但它实际上已经开始和以下已有 capability 发生交叉：

- `openspec/specs/search-subagent-evidence-orchestration/spec.md`
- `openspec/specs/agent-subagent-orchestration/spec.md`

因此，这里选择把它记录为一次额外的后续实现说明，而不是强行回填到已经完成并归档的 merge change 中。

## 行为影响

### 用户侧影响

- 知识图谱回答现在会先经过 delegated retrieval，再由主 agent 汇总
- trace 流程表现为 `planner -> search_subagent -> compose_answer -> citations`
- `graph` 和 `graphMeta` 仍然会继续出现在聊天响应和流式终态元数据中

### 工程侧影响

- `app/agent/services.py` 中的一次性知识图谱直连返回逻辑被移除
- search evidence normalization 现在支持 `knowledge_graph` 作为新增 source type
- search trace 中现在可能包含单独的知识图谱检索子步骤

## 后续建议

如果这套“知识图谱作为 search subagent 检索源”的行为会长期保留，那么后续应当单独发起一个新的 OpenSpec change，把下面两类主 specs 正式补齐：

- Search Subagent 如何纳入知识图谱作为证据来源
- 主编排工作流如何消费知识图谱返回的结构化结果
