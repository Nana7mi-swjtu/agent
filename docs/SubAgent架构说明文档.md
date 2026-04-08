# Agent / SubAgent 开发接入文档

本文档面向后续参与本项目开发的同学，目标是把当前 Agent 运行链路、目录职责、接口合同、扩展方式说明清楚，避免新增能力时把代码放错层，或者绕开现有框架直接耦合到底层实现。

当前文档覆盖：

- Main Agent 与各 SubAgent 的职责边界
- HTTP 接口到运行图的调用链路
- Tool、MCP、SubAgent 分别应该放在哪里
- 如何新增一个 Tool
- 如何新增一个 MCP 能力
- 如何新增一个 SubAgent 并接入现有框架
- 新增能力时需要同步修改的文件清单

## 1. 一句话原则

先看三条原则：

1. Main Agent 只做规划、汇总、回答，不直接写底层检索和远程协议细节。
2. Tool 是能力适配层，负责把底层实现包装成稳定的本地调用接口。
3. SubAgent 是编排层，负责围绕某一类任务组织 Tool、做策略判断、结果归一化，再把稳定结构返回给 Main Agent。

如果一个能力同时满足“有独立状态、有独立路由、有多步执行、有自己的结果合同”，它通常应该是 SubAgent。

如果一个能力只是“调用某个底层服务并返回结果”，它通常应该是 Tool。

如果一个能力是“远程 MCP server 的协议调用”，底层协议封装应该放在 MCP Tool，业务编排放在 MCP SubAgent。

## 2. 当前整体架构

当前工作台聊天链路不是单节点聊天，而是父图编排多个节点：

```text
POST /api/workspace/chat
  -> workspace/routes.py
  -> agent/services.py: generate_reply_payload()
  -> app/agent/graph/builder.py 构建的主图
     -> plan_route
     -> search_subagent（按需）
        -> search_plan
        -> rag_lookup（按需）
        -> web_lookup（按需）
        -> merge_results
     -> mcp_subagent（按需）
        -> plan_mcp_request
        -> execute_tool
     -> compose_answer
     -> answer_with_citations
```

当前已存在的主模块：

- `app/workspace/routes.py`
- `app/agent/services.py`
- `app/agent/graph/state.py`
- `app/agent/graph/builder.py`
- `app/agent/graph/nodes.py`
- `app/agent/graph/search.py`
- `app/agent/graph/mcp.py`
- `app/agent/tools/base.py`
- `app/agent/tools/context.py`
- `app/agent/tools/tools.py`
- `app/agent/tools/rag.py`
- `app/agent/tools/websearch.py`
- `app/agent/tools/mcp.py`

## 3. 目录职责

### 3.1 `app/workspace/routes.py`

HTTP 接口入口，负责：

- 鉴权
- 读取用户角色与工作区
- 读取可视化开关
- 调用 `generate_reply_payload()`
- 把 Agent 输出包装成 `/api/workspace/chat` 返回值

这里不要放业务编排逻辑，不要在这里直接调用 RAG、Web 搜索或 MCP。

### 3.2 `app/agent/services.py`

运行时装配层，负责：

- 创建 `main_llm` / `search_llm` / `mcp_llm`
- 初始化主图
- 组装主状态 `AgentState`
- 调用 graph
- 输出最终 `reply / citations / debug / trace`

这里也负责 trace 结构生成。如果你新增了一个新的 SubAgent，通常需要同步更新这里的 trace 组装逻辑。

### 3.3 `app/agent/graph/`

编排层，负责：

- 定义状态结构
- 定义主图和子图
- 定义节点之间的路由
- 把各 SubAgent 输出归一化并并入主状态

建议把“多步流程”和“面向 Agent 的业务决策”放在这里，而不是放在 routes 或 tools。

当前文件分工：

- `state.py`: 主状态 `AgentState`
- `builder.py`: 主图注册与连接
- `nodes.py`: 主图节点逻辑，包含 Planner、SubAgent 包装、Compose、Citations
- `search.py`: Search SubAgent 子图
- `mcp.py`: MCP SubAgent 子图

### 3.4 `app/agent/tools/`

能力适配层，负责把底层能力包装成统一 Tool。

Tool 的职责是：

- 隐藏底层调用细节
- 做参数校验和最基础的错误归一化
- 返回稳定、可预期的 Python 字典
- 通过 `AgentToolSpec` 暴露给 SubAgent 使用

Tool 不负责复杂多步编排，不负责主流程路由，不负责最终回答生成。

## 4. 当前状态合同

### 4.1 主状态 `AgentState`

主图围绕 `AgentState` 运行，里面包含：

- 运行时对象：`main_llm`、`search_llm`、`mcp_llm`
- 用户输入：`role`、`system_prompt`、`user_message`、`user_id`、`workspace_id`
- 路由状态：`intent`、`needs_search`、`needs_mcp`、`needs_clarification`
- 子图请求与结果：`search_request`、`search_result`、`mcp_request`、`mcp_result`
- RAG 相关：`rag_chunks`、`rag_citations`、`rag_no_evidence`、`rag_debug`
- 调试与输出：`debug`、`reply`

设计要求：

- 只有“主图跨节点需要共享的数据”才应该进入 `AgentState`
- 临时中间变量应留在子图自己的 state 内，不要污染主状态

### 4.2 Search SubAgent 输出合同

Search SubAgent 返回给主图的核心结构是：

- `search_result.status`
- `search_result.strategy`
- `search_result.summary`
- `search_result.sufficient`
- `search_result.follow_up_question`
- `search_result.evidence[]`
- `search_result.web_result`
- `rag_chunks`
- `rag_debug`

Main Agent 依赖的是“归一化后的证据”，而不是 RAG 或 Web 原始响应。

### 4.3 MCP SubAgent 输出合同

MCP SubAgent 返回给主图的核心结构是：

- `mcp_result.status`
- `mcp_result.summary`
- `mcp_result.follow_up_question`
- `mcp_result.artifacts`
- `mcp_result.execution_result`

Main Agent 依赖的是“稳定的结构化结果”，而不是 JSON-RPC 原始报文。

## 5. 当前 Tool 接口

所有 Tool 都通过 `AgentToolSpec` 暴露，结构如下：

```python
@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    description: str
    invoke: Callable[..., Any]
    args_schema: dict[str, Any]
    category: str
```

Tool 上下文通过 `AgentToolContext` 注入：

```python
@dataclass(frozen=True)
class AgentToolContext:
    user_id: int
    workspace_id: str
    rag_debug_enabled: bool = False
```

当前已使用的 category：

- `knowledge`: 私有知识能力，例如 `rag_search`
- `web`: 公网搜索能力，例如 `web_search`
- `mcp`: MCP 协议包装能力，例如 `mcp_list_tools`、`mcp_call_tool`

约定：

1. Tool 名称保持稳定，不要轻易改名。
2. `invoke()` 尽量返回 dict。
3. 成功失败建议统一为 `{"ok": True/False, ...}`。
4. Tool 内可以访问配置，但不要直接改主状态。
5. Tool 要屏蔽底层 provider 差异，SubAgent 不应知道底层协议细节。

## 6. Tool 应该放在哪里

### 6.1 放在 `app/agent/tools/` 的情况

以下情况应该写成 Tool：

- 调用本地业务服务，例如 RAG 搜索
- 调用外部 API，例如 Tavily Web 搜索
- 调用远程 MCP server 的 JSON-RPC 接口
- 任何可以被 SubAgent 复用的“单步能力”

推荐命名方式：

- `rag.py`: 与私有知识检索相关
- `websearch.py`: 与公网搜索相关
- `mcp.py`: 与 MCP 协议适配相关
- 新能力按主题拆文件，不要把所有 Tool 都堆到一个文件

### 6.2 不应该放在 Tool 的情况

以下逻辑不要直接放到 Tool：

- “是否要调用某个 Tool”的决策
- 多个 Tool 的串联策略
- 子流程的澄清逻辑
- 结果汇总为 evidence 或 artifacts 的业务归一化

这些应该放在 SubAgent 图里。

## 7. MCP 应该放在哪里

MCP 相关代码分两层：

### 7.1 协议适配层：`app/agent/tools/mcp.py`

这里负责：

- 读取 `AGENT_MCP_SERVERS_JSON`
- 解析 server 配置
- 发起 `tools/list`、`tools/call`
- 处理 HTTP/JSON 错误
- 返回统一 Tool 输出

换句话说，这里解决“怎么和远程 MCP server 说话”。

### 7.2 业务编排层：`app/agent/graph/mcp.py`

这里负责：

- 根据用户请求选 server
- 决定要执行哪个 MCP Tool
- 必要时向用户追问
- 将执行结果整理成 `mcp_result`

换句话说，这里解决“什么时候调 MCP、调哪个 server、结果怎么回主图”。

### 7.3 MCP 新能力的推荐放置方式

如果你要新增一个 MCP 能力：

1. 先确认它是“远程 server 上已有 tool”，还是“本地项目需要新增一个 MCP 适配动作”。
2. 如果只是封装一个新的远程调用模式，优先在 `app/agent/tools/mcp.py` 新增或扩展 Tool。
3. 如果需要面向用户请求做额外规划、澄清、多步执行，再在 `app/agent/graph/mcp.py` 增加编排逻辑。

不要把 JSON-RPC 调用逻辑直接写进主图节点。

## 8. 如何新增一个 Tool

### 8.1 适用场景

你有一个新能力，例如：

- 内部知识图查询
- 第三方行业数据库查询
- 新的外部搜索源
- 某个远程服务调用

并且这个能力可以被 Agent 视为“一个独立的可调用动作”。

### 8.2 接入步骤

1. 在 `app/agent/tools/` 下新增文件，或者在已有主题文件中扩展。
2. 写一个 `create_xxx_tool(context)` 工厂函数，返回 `AgentToolSpec` 或 `list[AgentToolSpec]`。
3. 在 `invoke()` 里完成参数处理、调用、错误归一化。
4. 在 `app/agent/tools/tools.py` 的 `get_agent_tools()` 中注册该工厂。
5. 在对应 SubAgent 图中通过 `get_agent_tools(context=..., categories=...)` 取用。
6. 在 SubAgent 层把 Tool 原始输出归一化成该子图的稳定结果合同。
7. 为 Tool 和 SubAgent 分别补测试。

### 8.3 最小示例

```python
from .base import AgentToolSpec
from .context import AgentToolContext


def _invoke_company_search(*, query: str) -> dict:
    return {"ok": True, "results": []}


def create_company_search_tool(_: AgentToolContext) -> AgentToolSpec:
    return AgentToolSpec(
        name="company_search",
        description="Search company records from internal service.",
        invoke=_invoke_company_search,
        args_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        category="knowledge",
    )
```

### 8.4 设计建议

- Tool 返回值尽量稳定，不要把 provider 原始字段直接透出到上层。
- 参数名和返回字段名尽量面向业务，而不是面向某个第三方 SDK。
- 多个 Tool 如果属于同一来源，尽量共用一个文件和一组辅助函数。

## 9. 如何新增一个 MCP 能力

以“支持调用远程 MCP tool”为例，建议按以下顺序接入。

### 9.1 扩展 Tool 层

如果当前 `mcp_call_tool` 不够用：

1. 在 `app/agent/tools/mcp.py` 增加新的 invoke 函数。
2. 新增对应 `AgentToolSpec`。
3. 保持返回结构稳定，例如：
   - `ok`
   - `server`
   - `tool`
   - `response`
   - `error`

### 9.2 扩展 MCP SubAgent 规划层

在 `app/agent/graph/mcp.py` 中：

1. 扩展 `MCPState`
2. 扩展 `MCPPlanOutput`
3. 在 `_plan_mcp_request_node()` 中识别新动作
4. 在 `_execute_tool_node()` 中把新动作映射到 Tool
5. 归一化结果到 `summary / artifacts / execution_result`

### 9.3 什么时候该拆成新的 SubAgent

如果 MCP 侧能力已经不再是“列工具 / 调工具”这种通用壳，而是出现：

- 多步规划
- 多次远程调用
- 特定领域的结果归并
- 独立澄清问题

那应该考虑新建一个专用 SubAgent，而不是继续把所有业务逻辑都塞进 `mcp.py`。

## 10. 如何新增一个 SubAgent

这是本文最关键的部分。

### 10.1 适用场景

以下情况适合新建 SubAgent：

- 这个能力有独立任务边界，例如“代码搜索”“数据分析”“图谱查询”
- 它需要自己的状态结构
- 它通常需要多步执行
- 它需要自己的澄清逻辑
- 它的结果需要以稳定合同返回给 Main Agent

### 10.2 推荐文件布局

假设新增一个 `analysis` SubAgent，建议最少涉及：

- `app/agent/graph/analysis.py`
- `app/agent/graph/state.py`
- `app/agent/graph/nodes.py`
- `app/agent/graph/builder.py`
- `app/agent/services.py`
- `tests/` 下对应测试文件

如需新能力，再补：

- `app/agent/tools/analysis.py`
- `app/agent/tools/tools.py`

### 10.3 接入步骤

#### 第一步：定义子图状态

在 `app/agent/graph/analysis.py` 中定义 `AnalysisState`，只放这个子图需要的字段。

```python
class AnalysisState(TypedDict):
    llm: Any
    request: str
    user_id: int
    workspace_id: str
    status: str
    summary: str
    artifacts: dict[str, Any]
```

#### 第二步：实现子图

延续当前风格，把子图拆成“计划 -> 执行 -> 汇总”：

- `_plan_analysis_node()`
- `_execute_analysis_node()`
- `_merge_analysis_node()`
- `build_analysis_graph()`

子图输出必须稳定，不要把一堆临时字段直接往父图冒。

#### 第三步：在主状态中加字段

在 `app/agent/graph/state.py` 为主图增加必要字段，例如：

- `needs_analysis`
- `analysis_request`
- `analysis_result`
- `analysis_completed`

原则是：只有父图需要跨节点共享的字段才加进去。

#### 第四步：在 `nodes.py` 增加包装节点

参考现有 `search_subagent_node()` 和 `mcp_subagent_node()`：

- 从主状态提取请求
- 调用子图 `invoke()`
- 把结果归一化回写到主状态
- 必要时触发澄清

建议保持这种模式：

```python
def analysis_subagent_node(state: AgentState):
    result = _analysis_graph.invoke({...})
    return {
        "analysis_result": {...},
        "analysis_completed": True,
    }
```

不要让主图直接感知子图内部每一个中间节点。

#### 第五步：修改主路由

在 `nodes.py` 中：

- 扩展 planner 输出
- 增加 `needs_analysis` 判定
- 更新 `route_after_plan()`
- 如果它和 Search、MCP 存在先后关系，更新 `route_after_search()`、`route_after_mcp()` 等后续路由

#### 第六步：注册到主图

在 `app/agent/graph/builder.py`：

1. `builder.add_node("analysis_subagent", analysis_subagent_node)`
2. 在条件分支映射中加上该节点

这一步完成后，主图才真正能走到新的 SubAgent。

#### 第七步：决定 Main Agent 如何消费结果

如果新 SubAgent 的输出会影响最终回答，需要在 `compose_answer_node()` 的系统上下文拼装阶段补充对应内容。

当前 Search 和 MCP 的处理方式是：

- Search: 把 `summary` 和 `evidence` 注入 system prompt
- MCP: 把 `summary` 注入 system prompt

新的 SubAgent 也应采用同样思路，给 Main Agent 提供“稳定摘要”，而不是原始底层输出。

#### 第八步：补 Trace

如果前端需要看到这个 SubAgent 的执行轨迹，需要同步更新 `app/agent/services.py`：

- 增加新的 step 构造函数
- 把它接到 `_build_trace_payload()` 里

否则前端 trace 里不会显示新增节点。

#### 第九步：补测试

至少补三类测试：

1. 主图路由测试
2. 子图自身测试
3. 接口级流程测试

建议参考：

- `tests/test_agent_subagent_orchestration.py`
- `tests/test_agent_tools_modularization.py`
- `tests/test_flows.py`

## 11. 新增 SubAgent 的推荐模板

下面给一个最小模板，便于复制思路：

```python
from __future__ import annotations

from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph


class AnalysisState(TypedDict):
    llm: Any
    request: str
    user_id: int
    workspace_id: str
    status: str
    summary: str
    follow_up_question: str
    artifacts: dict[str, Any]


def _plan_node(state: AnalysisState):
    request = str(state.get("request", "")).strip()
    if not request:
        return {
            "status": "need_input",
            "summary": "",
            "follow_up_question": "请补充分析目标。",
            "artifacts": {},
        }
    return {
        "status": "ready",
        "summary": "",
        "follow_up_question": "",
        "artifacts": {},
    }


def _route_after_plan(state: AnalysisState) -> str:
    if state.get("status") == "ready":
        return "execute"
    return END


def _execute_node(state: AnalysisState):
    return {
        "status": "done",
        "summary": "Analysis finished.",
        "artifacts": {"result": {}},
    }


def build_analysis_graph():
    builder = StateGraph(AnalysisState)
    builder.add_node("plan", _plan_node)
    builder.add_node("execute", _execute_node)
    builder.add_edge(START, "plan")
    builder.add_conditional_edges(
        "plan",
        _route_after_plan,
        {
            "execute": "execute",
            END: END,
        },
    )
    builder.add_edge("execute", END)
    return builder.compile()
```

这个模板的关键不是功能，而是结构：

- 子图先自己解决输入是否足够
- 子图内部完成执行
- 子图返回稳定 summary / artifacts
- 主图只消费结果，不关心内部细节

## 12. 新增能力时的修改清单

### 12.1 新增 Tool

- `app/agent/tools/xxx.py`
- `app/agent/tools/tools.py`
- 对应测试

### 12.2 新增 MCP 动作

- `app/agent/tools/mcp.py`
- `app/agent/graph/mcp.py`
- 对应测试

### 12.3 新增 SubAgent

- `app/agent/graph/xxx.py`
- `app/agent/graph/state.py`
- `app/agent/graph/nodes.py`
- `app/agent/graph/builder.py`
- `app/agent/services.py`
- 可能还包括 `app/agent/tools/xxx.py`
- 对应测试

### 12.4 如果涉及前端可视化

还要同步检查：

- `GET /api/workspace/context` 返回的能力位
- `POST /api/workspace/chat` 返回的 `trace` / `debug`
- 前端消息渲染是否识别新的 trace step

## 13. 当前配置项

### 13.1 通用模型配置

- `AI_PROVIDER`
- `AI_MODEL`
- `AI_API_KEY`
- `AI_BASE_URL`
- `AI_TIMEOUT_SECONDS`

### 13.2 角色级模型配置

- `AGENT_MAIN_AI_*`
- `AGENT_SEARCH_AI_*`
- `AGENT_MCP_AI_*`

规则：

- 角色级未配置时回退到通用 `AI_*`

### 13.3 能力开关

- `RAG_ENABLED`
- `RAG_DEBUG_VISUALIZATION_ENABLED`
- `AGENT_WEBSEARCH_ENABLED`
- `AGENT_MCP_ENABLED`
- `AGENT_TRACE_VISUALIZATION_ENABLED`
- `AGENT_TRACE_DEBUG_DETAILS_ENABLED`

### 13.4 MCP 配置

- `AGENT_MCP_SERVERS_JSON`
- `AGENT_MCP_TIMEOUT_SECONDS`

### 13.5 Web Search 配置

- `TAVILY_API_KEY`
- `TAVILY_BASE_URL`
- `TAVILY_TIMEOUT_SECONDS`

## 14. 开发约束建议

为了保持架构稳定，新增能力时建议遵守以下约束：

1. 不要在 `workspace/routes.py` 里写任何检索、MCP、分析编排。
2. 不要在 `nodes.py` 里直接写第三方 API 请求。
3. 不要在 Tool 层生成最终自然语言回答。
4. 不要让 Main Agent 直接依赖某个 provider 的原始返回结构。
5. 不要把所有新能力都继续堆进 `search.py` 或 `mcp.py`，任务边界变了就拆新的 SubAgent。
6. 新增可视化步骤时，不要忘记同步 trace 构造。
7. 新增主状态字段前，先确认它是不是必须跨节点共享。

## 15. 典型判断题

### 15.1 “我接了一个新的第三方搜索 API，应该放哪里？”

先放 `app/agent/tools/`，作为 Tool。

如果只是替换或补充 Search SubAgent 的证据源，再在 `search.py` 里增加调用和结果归一化。

### 15.2 “我想把某个 MCP server 的 tool 调起来，应该放哪里？”

协议调用先放 `app/agent/tools/mcp.py`，是否调用、何时调用、如何追问用户，放 `app/agent/graph/mcp.py`。

### 15.3 “我有一个完整的新流程，既要决策也要多步执行。”

新建 SubAgent，不要只写成一个 Tool。

### 15.4 “我只是想让主回答时多带一点中间信息。”

优先在对应 SubAgent 输出稳定 `summary`，再由 `compose_answer_node()` 把它注入给 Main Agent。

## 16. 推荐开发顺序

新增能力时，建议按下面顺序做：

1. 先定义结果合同
2. 再写 Tool
3. 再写 SubAgent 编排
4. 再接入主图
5. 再补 trace
6. 最后补接口级测试和前端展示

如果顺序反过来，通常会出现主状态混乱、字段命名漂移、trace 对不上、前后端调试困难的问题。

## 17. 当前实现的边界说明

截至当前版本：

- Search SubAgent 已支持 `private_only / public_only / private_first / hybrid`
- MCP SubAgent 当前只稳定支持“列出 server 的 tools”
- Main Agent 通过 Planner 决定是否走 Search / MCP / Clarify
- 最终回答和 citations 仍由主图统一收口

这意味着：

- Search 相关扩展优先沿着 `search.py + tools/` 扩展
- MCP 相关扩展优先沿着 `mcp.py + tools/mcp.py` 扩展
- 新领域型流程优先考虑新增独立 SubAgent

## 18. 结论

把代码放对层，比把功能先堆出来更重要。

记住当前项目的分层：

- `routes`: HTTP 入口
- `services`: 运行时装配与 trace
- `graph`: 编排与状态
- `tools`: 能力适配
- `rag/*` 等业务模块: 底层领域实现

新增能力时，优先问自己三个问题：

1. 这是一个 Tool，还是一个 SubAgent？
2. Main Agent 是否真的需要知道它的底层细节？
3. 我返回给上层的结构是不是稳定、可测试、可追踪？

如果这三个问题答清楚，基本就不会把接入方式做偏。
