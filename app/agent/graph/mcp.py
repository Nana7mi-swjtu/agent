from __future__ import annotations

import json
from typing import Any, TypedDict

from flask import current_app
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from ..tools import AgentToolContext, get_agent_tools


class MCPState(TypedDict):
    llm: Any
    request: str
    user_id: int
    workspace_id: str
    selected_server: str
    selected_tool: str
    tool_args: dict[str, Any]
    execution_result: dict[str, Any]
    status: str
    summary: str
    follow_up_question: str
    artifacts: dict[str, Any]


class MCPPlanOutput(BaseModel):
    selected_server: str = Field(default="")
    selected_tool: str = Field(default="")
    needs_clarification: bool = Field(default=False)
    follow_up_question: str = Field(default="")


def _configured_servers() -> list[str]:
    raw = str(current_app.config.get("AGENT_MCP_SERVERS_JSON", "")).strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    return [str(name).strip() for name, value in payload.items() if isinstance(name, str) and name.strip() and isinstance(value, dict)]


def _plan_mcp_request_node(state: MCPState):
    request = str(state.get("request", "")).strip()
    lowered = request.lower()
    servers = _configured_servers()
    selected_server = ""
    for name in servers:
        if name.lower() in lowered:
            selected_server = name
            break
    if not selected_server and len(servers) == 1:
        selected_server = servers[0]

    selected_tool = ""
    needs_clarification = False
    follow_up_question = ""
    if "list" in lowered and "tool" in lowered or "列出" in request and "工具" in request:
        selected_tool = "mcp_list_tools"
        if not selected_server:
            needs_clarification = True
            follow_up_question = "请指定要查询的 MCP server 名称。"

    llm = state.get("llm")
    if hasattr(llm, "with_structured_output"):
        try:
            structured_llm = llm.with_structured_output(MCPPlanOutput)
            response = structured_llm.invoke(
                [
                    {
                        "role": "system",
                        "content": (
                            "You plan MCP requests. Prefer supported high-level actions only. "
                            "Currently the supported action is mcp_list_tools."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"request={request}\nconfigured_servers={','.join(servers)}\n",
                    },
                ]
            )
            candidate_tool = str(response.selected_tool).strip()
            if candidate_tool == "mcp_list_tools":
                selected_tool = candidate_tool
            candidate_server = str(response.selected_server).strip()
            if candidate_server:
                selected_server = candidate_server
            if bool(response.needs_clarification):
                needs_clarification = True
            if str(response.follow_up_question).strip():
                follow_up_question = str(response.follow_up_question).strip()
        except Exception:
            pass

    if selected_tool == "mcp_list_tools":
        if not selected_server:
            return {
                "status": "need_input",
                "summary": "",
                "follow_up_question": follow_up_question or "请指定要查询的 MCP server 名称。",
                "selected_server": "",
                "selected_tool": "",
                "tool_args": {},
                "artifacts": {},
            }
        return {
            "status": "ready",
            "selected_server": selected_server,
            "selected_tool": selected_tool,
            "tool_args": {"server": selected_server},
            "summary": "",
            "follow_up_question": "",
            "artifacts": {},
        }

    return {
        "status": "need_input",
        "summary": "",
        "follow_up_question": follow_up_question or "当前 MCP 子代理仅支持列出远程工具，请明确说明 server 或具体动作。",
        "selected_server": selected_server,
        "selected_tool": "",
        "tool_args": {},
        "artifacts": {},
    }


def _route_after_plan(state: MCPState) -> str:
    if state.get("status") == "ready":
        return "execute_tool"
    return END


def _execute_tool_node(state: MCPState):
    tool_context = AgentToolContext(user_id=state["user_id"], workspace_id=state["workspace_id"], rag_debug_enabled=False)
    tools = get_agent_tools(context=tool_context, categories=("mcp",))
    tool_by_name = {item.name: item for item in tools}
    selected_tool = str(state.get("selected_tool", "")).strip()
    tool_spec = tool_by_name.get(selected_tool)
    if tool_spec is None:
        return {
            "execution_result": {"ok": False, "error": f"unsupported mcp action: {selected_tool}"},
            "status": "failed",
            "summary": "MCP capability is unavailable.",
            "artifacts": {},
        }

    tool_args = state.get("tool_args", {})
    if not isinstance(tool_args, dict):
        tool_args = {}
    result = tool_spec.invoke(**tool_args)
    if not isinstance(result, dict):
        result = {"ok": True, "result": result}

    if result.get("ok", False):
        response = result.get("response", {})
        tool_list = []
        if isinstance(response, dict):
            payload = response.get("result", {})
            if isinstance(payload, dict):
                raw_tools = payload.get("tools", [])
                if isinstance(raw_tools, list):
                    tool_list = [item for item in raw_tools if isinstance(item, dict)]
        return {
            "execution_result": result,
            "status": "done",
            "summary": f"MCP server '{state.get('selected_server', '')}' returned {len(tool_list)} tool(s).",
            "artifacts": {"tools": tool_list},
        }

    error_text = str(result.get("error", "mcp execution failed")).strip() or "mcp execution failed"
    return {
        "execution_result": result,
        "status": "failed",
        "summary": error_text,
        "artifacts": {},
    }


def build_mcp_graph():
    builder = StateGraph(MCPState)
    builder.add_node("plan_mcp_request", _plan_mcp_request_node)
    builder.add_node("execute_tool", _execute_tool_node)
    builder.add_edge(START, "plan_mcp_request")
    builder.add_conditional_edges(
        "plan_mcp_request",
        _route_after_plan,
        {
            "execute_tool": "execute_tool",
            END: END,
        },
    )
    builder.add_edge("execute_tool", END)
    return builder.compile()
