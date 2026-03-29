from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

from .base import AgentToolSpec
from .context import AgentToolContext


def _load_servers() -> dict[str, dict[str, Any]]:
    raw = str(current_app.config.get("AGENT_MCP_SERVERS_JSON", "")).strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for name, value in payload.items():
        if isinstance(name, str) and isinstance(value, dict):
            normalized[name] = value
    return normalized


def _mcp_server_config(server: str) -> dict[str, Any] | None:
    servers = _load_servers()
    config = servers.get(server)
    if not isinstance(config, dict):
        return None
    endpoint = str(config.get("endpoint", "")).strip()
    if not endpoint:
        return None
    return {"endpoint": endpoint}


def _post_json(url: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    encoded = json.dumps(payload).encode("utf-8")
    request = Request(url, data=encoded, method="POST")
    request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        return {"ok": False, "error": f"mcp http error: {exc.code}"}
    except URLError as exc:
        return {"ok": False, "error": f"mcp request failed: {exc.reason}"}
    try:
        return {"ok": True, "data": json.loads(body)}
    except json.JSONDecodeError:
        return {"ok": False, "error": "mcp returned invalid json"}


def _mcp_list_tools_invoke(*, server: str) -> dict[str, Any]:
    if not bool(current_app.config.get("AGENT_MCP_ENABLED", False)):
        return {"ok": False, "error": "mcp is disabled"}
    config = _mcp_server_config(server)
    if config is None:
        return {"ok": False, "error": f"mcp server '{server}' is not configured"}
    timeout_seconds = int(current_app.config.get("AGENT_MCP_TIMEOUT_SECONDS", 20))
    response = _post_json(
        config["endpoint"],
        {"jsonrpc": "2.0", "id": "list-tools", "method": "tools/list", "params": {}},
        timeout_seconds=timeout_seconds,
    )
    if not response.get("ok", False):
        return response
    payload = response.get("data")
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid mcp response payload"}
    return {"ok": True, "server": server, "response": payload}


def _mcp_call_tool_invoke(*, server: str, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if not bool(current_app.config.get("AGENT_MCP_ENABLED", False)):
        return {"ok": False, "error": "mcp is disabled"}
    config = _mcp_server_config(server)
    if config is None:
        return {"ok": False, "error": f"mcp server '{server}' is not configured"}
    timeout_seconds = int(current_app.config.get("AGENT_MCP_TIMEOUT_SECONDS", 20))
    response = _post_json(
        config["endpoint"],
        {
            "jsonrpc": "2.0",
            "id": "call-tool",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments if isinstance(arguments, dict) else {},
            },
        },
        timeout_seconds=timeout_seconds,
    )
    if not response.get("ok", False):
        return response
    payload = response.get("data")
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid mcp response payload"}
    return {"ok": True, "server": server, "tool": tool_name, "response": payload}


def create_mcp_tools(_: AgentToolContext) -> list[AgentToolSpec]:
    if not bool(current_app.config.get("AGENT_MCP_ENABLED", False)):
        return []
    return [
        AgentToolSpec(
            name="mcp_list_tools",
            description="List tools exposed by a configured MCP server.",
            invoke=_mcp_list_tools_invoke,
            args_schema={
                "type": "object",
                "properties": {"server": {"type": "string", "description": "MCP server name."}},
                "required": ["server"],
                "additionalProperties": False,
            },
            category="mcp",
        ),
        AgentToolSpec(
            name="mcp_call_tool",
            description="Call a named tool on a configured MCP server.",
            invoke=_mcp_call_tool_invoke,
            args_schema={
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "MCP server name."},
                    "tool_name": {"type": "string", "description": "Remote MCP tool name."},
                    "arguments": {"type": "object", "description": "Arguments for the remote tool."},
                },
                "required": ["server", "tool_name"],
                "additionalProperties": False,
            },
            category="mcp",
        ),
    ]

