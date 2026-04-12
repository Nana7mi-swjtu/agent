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


def test_plan_route_preserves_public_only_strategy_for_explicit_web_request():
    result = plan_route_node(
        {
            "user_message": "帮我上网搜索一下京东方这个公司的情况",
            "rag_enabled": True,
            "web_enabled": True,
            "mcp_enabled": False,
        }
    )
    assert result["needs_search"] is True
    assert result["needs_clarification"] is False
    assert result["search_request"]["preferred_strategy"] == "public_only"


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


def test_search_subagent_queries_knowledge_graph(app, monkeypatch):
    class _FakeKnowledgeGraphTool:
        name = "knowledge_graph_query"

        def invoke(self, **kwargs):
            assert kwargs["entity"] == "京东方"
            assert kwargs["intent"] == "股权关系"
            return {
                "ok": True,
                "summary": "知识图谱命中了京东方股权关系。",
                "graph": {"nodes": [{"id": "boe", "label": "京东方", "type": "company"}], "edges": []},
                "meta": {"source": "knowledge_graph", "contextSize": 1},
            }

    def _fake_get_agent_tools(**kwargs):
        categories = tuple(kwargs.get("categories", ()))
        if categories == ("knowledge_graph",):
            return [_FakeKnowledgeGraphTool()]
        return []

    app.config["AGENT_KNOWLEDGE_GRAPH_ENABLED"] = True
    monkeypatch.setattr("app.agent.graph.search.get_agent_tools", _fake_get_agent_tools)

    with app.app_context():
        result = search_subagent_node(
            {
                "user_message": "请查知识图谱",
                "user_id": 1,
                "workspace_id": "ws-1",
                "kg_enabled": True,
                "entity": "京东方",
                "graph_intent": "股权关系",
                "rag_enabled": False,
                "rag_debug_enabled": False,
                "search_request": {
                    "query": "请查知识图谱",
                    "preferred_strategy": "private_only",
                    "entity": "京东方",
                    "graph_intent": "股权关系",
                },
                "debug": {},
            }
        )

    assert result["search_completed"] is True
    assert result["graph_data"]["nodes"][0]["label"] == "京东方"
    assert result["graph_meta"]["source"] == "knowledge_graph"
    assert result["search_result"]["status"] == "done"


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
