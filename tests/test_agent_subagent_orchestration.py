from __future__ import annotations

from app.agent.graph.nodes import mcp_subagent_node, plan_route_node, search_subagent_node


def test_plan_route_requests_clarification_for_vague_search():
    result = plan_route_node(
        {
            "user_message": "搜索",
            "rag_enabled": True,
            "web_enabled": True,
            "mcp_enabled": False,
        }
    )
    assert result["needs_clarification"] is True
    assert "具体主题" in result["clarification_question"]


def test_search_subagent_reports_missing_evidence(app):
    with app.app_context():
        result = search_subagent_node(
            {
                "user_message": "根据文档回答",
                "user_id": 1,
                "workspace_id": "ws-1",
                "rag_enabled": False,
                "rag_debug_enabled": False,
                "search_request": {"query": "根据文档回答", "preferred_strategy": "private_only"},
                "debug": {},
            }
        )
    assert result["search_completed"] is True
    assert result["needs_clarification"] is True
    assert result["rag_no_evidence"] is True


def test_mcp_subagent_requests_server_clarification_when_ambiguous(app):
    app.config["AGENT_MCP_ENABLED"] = True
    app.config["AGENT_MCP_SERVERS_JSON"] = '{"alpha":{"endpoint":"http://127.0.0.1:8080/a"},"beta":{"endpoint":"http://127.0.0.1:8080/b"}}'
    with app.app_context():
        result = mcp_subagent_node(
            {
                "user_message": "列出mcp工具",
                "user_id": 1,
                "workspace_id": "ws-1",
                "mcp_request": {"request": "列出mcp工具"},
                "debug": {},
            }
        )
    assert result["mcp_completed"] is True
    assert result["needs_clarification"] is True
    assert "server" in result["clarification_question"].lower()
