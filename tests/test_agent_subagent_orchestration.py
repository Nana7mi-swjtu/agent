from __future__ import annotations

from app.agent.graph.analysis_modules import AnalysisFieldDefinition, AnalysisModuleContract
from app.agent.graph.nodes import (
    analysis_intake_node,
    analysis_modules_node,
    mcp_subagent_node,
    plan_route_node,
    search_subagent_node,
)


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


def test_plan_route_prefers_analysis_intake_when_modules_enabled():
    result = plan_route_node(
        {
            "user_message": "请开始做报告",
            "enabled_analysis_modules": ["robotics_risk"],
            "debug": {},
        }
    )
    assert result["intent"] == "analysis"
    assert result["needs_search"] is False
    assert result["needs_mcp"] is False
    assert result["analysis_completed"] is False


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


def test_analysis_intake_deduplicates_shared_fields_before_module_specific(monkeypatch):
    shared_fields = (
        AnalysisFieldDefinition("enterpriseName", "企业名称"),
        AnalysisFieldDefinition("timeRange", "时间范围"),
        AnalysisFieldDefinition("reportGoal", "报告目标"),
    )
    registry = {
        "robotics_risk": AnalysisModuleContract(
            module_id="robotics_risk",
            display_name="机器人风险机会洞察",
            shared_fields=shared_fields,
            module_fields=(AnalysisFieldDefinition("focus", "机器人关注重点"),),
            build_input=lambda shared, module, context: {},
            run=lambda payload: {},
        ),
        "enterprise_operations": AnalysisModuleContract(
            module_id="enterprise_operations",
            display_name="企业运营分析",
            shared_fields=shared_fields,
            module_fields=(AnalysisFieldDefinition("metrics", "经营指标"),),
            build_input=lambda shared, module, context: {},
            run=lambda payload: {},
        ),
    }
    monkeypatch.setattr("app.agent.graph.nodes.get_analysis_module_registry", lambda: registry)

    result = analysis_intake_node(
        {
            "enabled_analysis_modules": ["robotics_risk", "enterprise_operations"],
            "analysis_shared_inputs": {},
            "analysis_module_inputs": {},
            "debug": {},
        }
    )

    assert result["needs_clarification"] is True
    assert "企业名称" in result["clarification_question"]
    assert "时间范围" in result["clarification_question"]
    assert "报告目标" in result["clarification_question"]
    assert "机器人关注重点" not in result["clarification_question"]
    assert "经营指标" not in result["clarification_question"]
    assert result["missing_fields"] == [
        "analysis.shared.enterpriseName",
        "analysis.shared.timeRange",
        "analysis.shared.reportGoal",
    ]


def test_analysis_intake_ignores_disabled_module_specific_fields(monkeypatch):
    shared_fields = (
        AnalysisFieldDefinition("enterpriseName", "企业名称"),
        AnalysisFieldDefinition("timeRange", "时间范围"),
        AnalysisFieldDefinition("reportGoal", "报告目标"),
    )
    registry = {
        "robotics_risk": AnalysisModuleContract(
            module_id="robotics_risk",
            display_name="机器人风险机会洞察",
            shared_fields=shared_fields,
            module_fields=(AnalysisFieldDefinition("focus", "关注重点"),),
            build_input=lambda shared, module, context: {},
            run=lambda payload: {},
        ),
        "enterprise_operations": AnalysisModuleContract(
            module_id="enterprise_operations",
            display_name="企业运营分析",
            shared_fields=shared_fields,
            module_fields=(AnalysisFieldDefinition("metrics", "经营指标"),),
            build_input=lambda shared, module, context: {},
            run=lambda payload: {},
        ),
    }
    monkeypatch.setattr("app.agent.graph.nodes.get_analysis_module_registry", lambda: registry)

    result = analysis_intake_node(
        {
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_shared_inputs": {
                "enterpriseName": "石头科技",
                "timeRange": "近30天",
                "reportGoal": "识别机器人行业风险与机会",
            },
            "analysis_module_inputs": {},
            "debug": {},
        }
    )

    assert result["needs_clarification"] is True
    assert "关注重点" in result["clarification_question"]
    assert "经营指标" not in result["clarification_question"]
    assert result["missing_fields"] == ["analysis.robotics_risk.focus"]


def test_analysis_modules_node_builds_aggregate_bundle(monkeypatch):
    contract = AnalysisModuleContract(
        module_id="robotics_risk",
        display_name="机器人风险机会洞察",
        shared_fields=(
            AnalysisFieldDefinition("enterpriseName", "企业名称"),
            AnalysisFieldDefinition("timeRange", "时间范围"),
            AnalysisFieldDefinition("reportGoal", "报告目标"),
        ),
        module_fields=(AnalysisFieldDefinition("focus", "关注重点"),),
        build_input=lambda shared, module, context: {
            "enterpriseName": shared["enterpriseName"],
            "focus": module["focus"],
            "conversationContext": context["conversationContext"],
        },
        run=lambda payload: {
            "status": "done",
            "runId": "run-robotics-001",
            "result": {
                "summary": {
                    "opportunity": "政策和订单侧存在增长信号。",
                    "risk": "竞争和招投标节奏存在波动。",
                }
            },
            "documentHandoff": {"title": "石头科技风险机会简报"},
            "limitations": ["公告样本有限"],
        },
    )
    monkeypatch.setattr("app.agent.graph.nodes.get_analysis_module_registry", lambda: {"robotics_risk": contract})

    result = analysis_modules_node(
        {
            "user_message": "请开始分析",
            "conversation_context": "最近对话：用户希望关注订单机会。",
            "enabled_analysis_modules": ["robotics_risk"],
            "analysis_shared_inputs": {
                "enterpriseName": "石头科技",
                "timeRange": "近30天",
                "reportGoal": "形成风险机会简报",
            },
            "analysis_module_inputs": {"robotics_risk": {"focus": "订单与政策"}},
            "debug": {},
        }
    )

    assert result["analysis_completed"] is True
    assert result["analysis_results"]["robotics_risk"]["runId"] == "run-robotics-001"
    bundle = result["analysis_handoff_bundle"]
    assert bundle["enabledModules"] == ["robotics_risk"]
    assert bundle["sharedInputSummary"]["enterpriseName"] == "石头科技"
    assert bundle["moduleRunIds"]["robotics_risk"] == "run-robotics-001"
    assert bundle["documentHandoffs"]["robotics_risk"]["title"] == "石头科技风险机会简报"
    assert bundle["limitations"] == ["公告样本有限"]


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
