# SubAgent 架构说明文档

本文档记录当前项目中 Main Agent、Search SubAgent、MCP SubAgent 的职责边界、运行链路、配置项与调试方式，便于后续联调、排障与扩展。

## 1. 当前架构概览

当前工作台聊天不再由单一聊天节点同时负责规划、检索、MCP 调用和最终作答，而是采用父图编排：

```text
用户问题
  -> Planner（主智能体规划）
     -> Search SubAgent（需要证据时）
        -> RAG 检索
        -> Web 搜索
        -> 结果归并
     -> MCP SubAgent（需要远程能力时）
        -> server 选择
        -> 工具列表 / 执行结果归一化
     -> Compose Answer（主智能体汇总）
     -> Citations（引用整理）
```

对应代码位置：

- `app/agent/graph/builder.py`
- `app/agent/graph/nodes.py`
- `app/agent/graph/search.py`
- `app/agent/graph/mcp.py`
- `app/agent/services.py`

## 2. 各 Agent 职责

### 2.1 Main Agent

Main Agent 负责：

- 接收工作台聊天请求
- 规划当前问题是否需要检索、MCP、澄清
- 调用 Search SubAgent / MCP SubAgent
- 汇总子智能体输出，生成最终回答
- 在命中 RAG 证据时整理引用信息

Main Agent 不直接持有底层 RAG / MCP 调用细节，只消费归一化后的结构化结果。

### 2.2 Search SubAgent

Search SubAgent 负责统一证据获取，当前支持两类来源：

- 私有知识：工作区 RAG 检索
- 公共知识：Web 搜索

它内部支持以下策略：

- `private_only`
- `public_only`
- `private_first`
- `hybrid`

返回内容会统一归一化为：

- `status`
- `strategy`
- `summary`
- `sufficient`
- `evidence[]`
- `follow_up_question`

也就是说，Main Agent 不需要关心“这是 RAG 命中的，还是 Web 搜出来的”，只需要根据统一 evidence 继续汇总。

### 2.3 MCP SubAgent

MCP SubAgent 负责：

- 根据用户请求判断是否要走 MCP 能力发现
- 选择合适的 MCP server
- 拉取工具列表或执行当前支持的 MCP 能力
- 把结果归一化为稳定结构

当前阶段它的重点是把“主 Agent 不直接处理 MCP 原始协议”这件事做清楚，而不是把所有 MCP 能力都放进去。

## 3. 运行时配置

### 3.1 通用模型配置

若不区分角色模型，可仅填写：

- `AI_PROVIDER`
- `AI_MODEL`
- `AI_API_KEY`
- `AI_BASE_URL`
- `AI_TIMEOUT_SECONDS`

### 3.2 角色级模型配置

若希望 Main / Search / MCP 使用不同模型，可分别填写：

- `AGENT_MAIN_AI_*`
- `AGENT_SEARCH_AI_*`
- `AGENT_MCP_AI_*`

回退规则：

- 若角色级字段未填，则回退到通用 `AI_*`

适用建议：

- Main Agent：更偏规划与汇总
- Search SubAgent：更偏检索策略与证据组织
- MCP SubAgent：更偏工具理解与执行结果总结

## 4. 与 RAG 的关系

RAG 不再是顶层固定分支，而是被纳入 Search SubAgent 内部。

也就是说，现在的知识问答链路是：

```text
用户提问
  -> Planner 判断 needs_search
  -> Search SubAgent
     -> 按策略执行 RAG / Web / 混合检索
  -> Main Agent 汇总
  -> 引用整理
```

因此：

- RAG 是 Search SubAgent 的一种证据来源
- Web 搜索也是 Search SubAgent 的一种证据来源
- 两者最终都要归一化为统一 evidence 合同

## 5. 可视化与调试

### 5.1 RAG 调试可视化

RAG 调试开关：

- `RAG_DEBUG_VISUALIZATION_ENABLED=true|false`

作用：

- 控制 `/api/rag/debug`
- 控制 `/api/rag/embedding`
- 控制聊天接口中 `debug.rag` 的透传
- 控制前端是否展示 RAG 调试面板

注意：

- 消息级 RAG 调试数据当前位于 `debug.rag` 下，不在 `debug` 顶层

### 5.2 Agent Trace 可视化

新增 Trace 开关：

- `AGENT_TRACE_VISUALIZATION_ENABLED=true|false`
- `AGENT_TRACE_DEBUG_DETAILS_ENABLED=true|false`

作用：

- 控制 `GET /api/workspace/context` 是否返回 Trace 能力位
- 控制 `POST /api/workspace/chat` 是否附带 `trace`
- 控制前端是否展示消息级执行轨迹

Trace 与 Debug 的边界：

- `trace`：稳定、面向前端展示的执行轨迹
- `debug`：更偏底层、面向调试的诊断负载

### 5.3 当前 Trace 步骤

当前已实现的标准步骤包括：

- `planner`
- `search_subagent`
- `mcp_subagent`
- `clarify`
- `compose_answer`
- `citations`

Search SubAgent 下还可能出现子步骤：

- `rag_lookup`
- `web_lookup`
- `merge_results`

## 6. 工作台接口变化

### 6.1 `GET /api/workspace/context`

当前除了角色、工作区、系统 Prompt 外，还会返回：

- `ragDebugVisualizationEnabled`
- `agentTraceVisualizationEnabled`
- `agentTraceDebugDetailsEnabled`

### 6.2 `POST /api/workspace/chat`

当前稳定字段：

- `data.role`
- `data.systemPrompt`
- `data.reply`
- `data.citations`
- `data.noEvidence`

条件字段：

- `data.debug`：当 RAG 调试可视化开启
- `data.trace`：当 Agent Trace 可视化开启

## 7. 典型联调场景

### 7.1 文档问答

```text
根据文档回答……
  -> Planner
  -> Search SubAgent
  -> RAG Lookup
  -> Merge Results
  -> Compose Answer
  -> Citations
```

### 7.2 最新资讯查询

```text
帮我查最新 AI 监管新闻
  -> Planner
  -> Search SubAgent
  -> Web Lookup
  -> Merge Results
  -> Compose Answer
```

### 7.3 MCP 工具发现

```text
列出 MCP 工具
  -> Planner
  -> MCP SubAgent
  -> Compose Answer
```

## 8. 常见排查点

1. 明明走了知识问答，但没有 trace

- 检查 `AGENT_TRACE_VISUALIZATION_ENABLED`
- 检查 `GET /api/workspace/context` 是否返回 `agentTraceVisualizationEnabled=true`

2. 前端看不到 RAG 检索细节

- 检查 `RAG_DEBUG_VISUALIZATION_ENABLED`
- 检查聊天消息中是否有 `debug.rag`

3. Search SubAgent 没有命中证据

- 检查工作区 `workspaceId`
- 检查索引是否完成
- 检查 `RAG_RETRIEVAL_SCORE_THRESHOLD`
- 检查 Search 策略是 `private_first` 还是 `public_only`

4. MCP 没走通

- 检查 `AGENT_MCP_ENABLED`
- 检查 `AGENT_MCP_SERVERS_JSON`
- 检查请求是否能让 Planner 识别为 MCP 类任务

## 9. 后续扩展建议

后续如果要继续扩展 subagent，建议保持下面的边界不变：

- 主 Agent 只做规划、协调、汇总
- 子 Agent 只负责自己领域内的执行与归一化
- 前端只消费 `trace` 展示编排过程，不直接依赖底层实现细节

这样后面无论增加新的 Search 变体、执行类 Agent，还是流式可视化，都不会把现有前后端合同打碎。
