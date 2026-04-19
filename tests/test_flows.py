import io
import json
import time

import pytest
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app.agent import services as agent_services
from app.agent.services import AgentServiceError
from app.models import AgentChatJob, AgentConversationMessage, AgentConversationThread, AnalysisSession, User


def _auth_headers(client, user_id: int) -> dict[str, str]:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "test-csrf-token"
    return {"X-CSRF-Token": "test-csrf-token"}


def _chat_payload(message: str, conversation_id: str = "conv-test", **extra) -> dict[str, object]:
    return {"message": message, "conversationId": conversation_id, **extra}


@pytest.fixture(autouse=True)
def _reset_agent_runtime():
    agent_services.reset_runtime_for_tests()
    yield
    agent_services.reset_runtime_for_tests()


def test_registration_flow(client, app, db_session):
    response = client.post(
        "/auth/register/send-code",
        json={
            "email": "newuser@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 200

    code = app.extensions["email_outbox"][-1]["code"]
    response = client.post(
        "/auth/register/verify-code",
        json={"email": "newuser@example.com", "code": code},
    )
    assert response.status_code == 200

    db_session.expire_all()
    user = db_session.execute(select(User).where(User.email == "newuser@example.com")).scalar_one_or_none()
    assert user is not None


def test_password_reset_flow(client, app, db_session):
    user = User(email="reset@example.com", password_hash=generate_password_hash("oldpassword"))
    db_session.add(user)
    db_session.commit()

    response = client.post("/auth/forgot-password/send-code", json={"email": "reset@example.com"})
    assert response.status_code == 200

    code = app.extensions["email_outbox"][-1]["code"]
    response = client.post(
        "/auth/forgot-password/verify-code",
        json={
            "email": "reset@example.com",
            "code": code,
            "new_password": "newpassword123",
            "confirm_password": "newpassword123",
        },
    )
    assert response.status_code == 200

    db_session.expire_all()
    updated = db_session.execute(select(User).where(User.email == "reset@example.com")).scalar_one()
    assert check_password_hash(updated.password_hash, "newpassword123")


def test_login_logout_session(client, db_session):
    user = User(email="login@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    response = client.post("/auth/login", json={"email": "login@example.com", "password": "password123"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["csrfToken"]
    assert payload["user"]["id"] == user.id

    with client.session_transaction() as sess:
        assert sess.get("user_id") == user.id
        csrf_token = sess.get("csrf_token")

    me_response = client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.get_json()["user"]["id"] == user.id

    missing_csrf = client.post("/auth/logout")
    assert missing_csrf.status_code == 403

    response = client.post("/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get("user_id") is None

def test_auth_session_endpoint(client, db_session):
    user = User(email="session@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    response = client.get("/auth/session")
    assert response.status_code == 401

    with client.session_transaction() as sess:
        sess["user_id"] = user.id

    response = client.get("/auth/session")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["userId"] == user.id


def test_get_profile_requires_auth(client):
    response = client.get("/api/user/profile")
    assert response.status_code == 401


def test_get_and_update_profile(client, db_session):
    user = User(
        email="profile@example.com",
        nickname="Profile User",
        password_hash=generate_password_hash("password123"),
    )
    db_session.add(user)
    db_session.commit()

    headers = _auth_headers(client, user.id)

    response = client.get("/api/user/profile")
    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["email"] == "profile@example.com"
    assert data["data"]["nickname"] == "Profile User"

    response = client.put(
        "/api/user/profile",
        data={
            "nickname": "新昵称",
            "old_password": "password123",
            "new_password": "newPass123!",
        },
        headers=headers,
    )
    assert response.status_code == 200

    db_session.expire_all()
    updated = db_session.execute(select(User).where(User.email == "profile@example.com")).scalar_one()
    assert updated.nickname == "新昵称"
    assert check_password_hash(updated.password_hash, "newPass123!")


def test_update_profile_rejects_wrong_old_password(client, db_session):
    user = User(email="wrong-old@example.com", nickname="Tester", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    headers = _auth_headers(client, user.id)

    response = client.put(
        "/api/user/profile",
        data={
            "nickname": "Tester",
            "old_password": "bad-old",
            "new_password": "newPass123!",
        },
        headers=headers,
    )
    assert response.status_code == 400


def test_patch_preferences_partial_update(client, db_session):
    user = User(email="prefs@example.com", nickname="Prefs", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    headers = _auth_headers(client, user.id)

    response = client.patch(
        "/api/user/preferences",
        json={"theme": "dark", "notifications": {"emailPush": True}},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["preferences"]["theme"] == "dark"
    assert payload["data"]["preferences"]["notifications"]["emailPush"] is True
    assert payload["data"]["preferences"]["notifications"]["agentRun"] is True


def test_patch_preferences_rejects_invalid_value(client, db_session):
    user = User(email="prefs2@example.com", nickname="Prefs2", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    headers = _auth_headers(client, user.id)

    response = client.patch("/api/user/preferences", json={"theme": "neon"}, headers=headers)
    assert response.status_code == 400


def test_workspace_role_selection_and_context(client, db_session):
    user = User(email="role@example.com", nickname="Role", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    headers = _auth_headers(client, user.id)

    response = client.get("/api/workspace/context")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["selectedRole"] is None

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["selectedRole"] == "investor"
    assert "投资者决策助手" in payload["data"]["systemPrompt"]


def test_workspace_context_includes_trace_visualization_flags(client, app, db_session):
    user = User(email="trace-context@example.com", nickname="TraceContext", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    headers = _auth_headers(client, user.id)
    app.config["AGENT_TRACE_VISUALIZATION_ENABLED"] = True
    app.config["AGENT_TRACE_DEBUG_DETAILS_ENABLED"] = True

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    context_response = client.get("/api/workspace/context")
    assert context_response.status_code == 200
    payload = context_response.get_json()["data"]
    assert payload["agentTraceVisualizationEnabled"] is True
    assert payload["agentTraceDebugDetailsEnabled"] is True
    assert payload["chatStreamingEnabled"] is True


def test_workspace_chat_requires_role(client, db_session, monkeypatch):
    user = User(email="chat@example.com", nickname="Chat", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    headers = _auth_headers(client, user.id)

    response = client.post("/api/workspace/chat", json=_chat_payload("请分析风险"), headers=headers)
    assert response.status_code == 400

    response = client.patch("/api/workspace/context", json={"role": "regulator"}, headers=headers)
    assert response.status_code == 200

    monkeypatch.setattr(
        "app.workspace.routes.generate_reply_payload",
        lambda **kwargs: {
            "reply": "agent generated response",
            "citations": [],
            "noEvidence": False,
            "graph": {},
            "graphMeta": {},
        },
    )
    response = client.post("/api/workspace/chat", json=_chat_payload("请分析风险"), headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["role"] == "regulator"
    assert payload["data"]["reply"] == "agent generated response"


@pytest.mark.parametrize("role", ["investor", "enterprise_manager", "regulator"])
def test_workspace_chat_reuses_conversation_history(client, db_session, monkeypatch, role):
    user = User(email=f"memory-{role}@example.com", nickname="Memory", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": role}, headers=headers)
    assert response.status_code == 200

    captured: list[dict[str, object]] = []

    def _fake_generate_reply_payload(**kwargs):
        captured.append(kwargs)
        if len(captured) == 1:
            return {
                "reply": "请补充要分析的公司名称。",
                "citations": [],
                "noEvidence": False,
                "intent": "clarify",
                "graph": {},
                "graphMeta": {},
            }
        return {
            "reply": "已结合上一轮补充信息继续回答。",
            "citations": [],
            "noEvidence": False,
            "intent": "answer",
            "graph": {},
            "graphMeta": {},
        }

    monkeypatch.setattr("app.workspace.routes.generate_reply_payload", _fake_generate_reply_payload)

    first_response = client.post("/api/workspace/chat", json=_chat_payload("请分析风险", "conv-a"), headers=headers)
    assert first_response.status_code == 200
    assert captured[0]["conversation_history"] == []

    db_session.expire_all()
    thread = db_session.execute(select(AgentConversationThread)).scalar_one()
    assert thread.role == role
    assert thread.conversation_id == "conv-a"
    messages = db_session.execute(select(AgentConversationMessage).where(AgentConversationMessage.thread_id == thread.id)).scalars().all()
    assert len(messages) == 2

    second_response = client.post("/api/workspace/chat", json=_chat_payload("另一个新问题", "conv-b"), headers=headers)
    assert second_response.status_code == 200
    assert captured[1]["conversation_history"] == []

    third_response = client.post("/api/workspace/chat", json=_chat_payload("腾讯", "conv-a"), headers=headers)
    assert third_response.status_code == 200

    assert len(captured) == 3
    second_history = captured[2]["conversation_history"]
    assert isinstance(second_history, list)
    assert str(captured[2]["conversation_context"]).startswith("最近对话：")
    assert any(item.get("role") == "assistant" and "请补充要分析的公司名称" in item.get("content", "") for item in second_history if isinstance(item, dict))
    assert any(item.get("role") == "user" and "请分析风险" in item.get("content", "") for item in second_history if isinstance(item, dict))
    assert not any(item.get("role") == "user" and "另一个新问题" in item.get("content", "") for item in second_history if isinstance(item, dict))

    db_session.commit()
    db_session.expire_all()
    threads = db_session.execute(select(AgentConversationThread)).scalars().all()
    assert {item.conversation_id for item in threads} == {"conv-a", "conv-b"}
    message_counts = {
        item.conversation_id: len(
            db_session.execute(
                select(AgentConversationMessage).where(AgentConversationMessage.thread_id == item.id)
            )
            .scalars()
            .all()
        )
        for item in threads
    }
    assert message_counts == {"conv-a": 4, "conv-b": 2}


def test_workspace_chat_includes_grouped_sources(client, db_session, monkeypatch):
    user = User(email="chat-sources@example.com", nickname="ChatSources", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    monkeypatch.setattr(
        "app.workspace.routes.generate_reply_payload",
        lambda **kwargs: {
            "reply": "agent generated response",
            "citations": [{"source": "annual-report.pdf", "chunk_id": "chunk-1", "page": 3, "section": "风险"}],
            "sources": [
                {
                    "id": "rag:annual-report.pdf",
                    "kind": "rag",
                    "title": "annual-report.pdf",
                    "source": "annual-report.pdf",
                    "pages": [3],
                    "sections": ["风险"],
                    "chunkIds": ["chunk-1"],
                    "citationCount": 1,
                },
                {
                    "id": "web:https://example.com/boe",
                    "kind": "web",
                    "title": "京东方公司概况",
                    "source": "https://example.com/boe",
                    "url": "https://example.com/boe",
                    "domain": "example.com",
                },
            ],
            "noEvidence": False,
        },
    )

    response = client.post("/api/workspace/chat", json=_chat_payload("请总结"), headers=headers)
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["sources"][0]["title"] == "annual-report.pdf"
    assert payload["sources"][1]["url"] == "https://example.com/boe"


def test_generate_reply_payload_routes_knowledge_graph_through_search_subagent(app, monkeypatch):
    class _FakeResponse:
        def __init__(self, content: str):
            self.content = content

    class _FakeChatOpenAI:
        def __init__(self, *args, **kwargs):
            pass

        def invoke(self, messages):
            return _FakeResponse("主 agent 总结了知识图谱结果")

    app.config["AGENT_KNOWLEDGE_GRAPH_ENABLED"] = True
    app.config["RAG_ENABLED"] = False
    app.config["AGENT_WEBSEARCH_ENABLED"] = False
    app.config["AGENT_MCP_ENABLED"] = False
    app.config["AI_PROVIDER"] = "openai"
    app.config["AI_MODEL"] = "test-model"
    app.config["AI_API_KEY"] = "test-key"
    app.config["AI_TIMEOUT_SECONDS"] = 10
    app.config["AI_BASE_URL"] = ""
    monkeypatch.setattr(agent_services, "ChatOpenAI", _FakeChatOpenAI)

    def _fake_search_node(state):
        return {
            "search_completed": True,
            "search_result": {
                "status": "done",
                "strategy": "private_only",
                "summary": "知识图谱结果",
                "sufficient": True,
                "follow_up_question": "",
                "evidence": [
                    {
                        "source_type": "knowledge_graph",
                        "source": "knowledge_graph",
                        "title": "Knowledge Graph",
                        "snippet": "京东方和若干主体存在股权关系。",
                        "score": 1.0,
                        "metadata": {"contextSize": 1},
                    }
                ],
                "web_result": {},
            },
            "graph_data": {
                "nodes": [{"id": "boe", "label": "京东方", "type": "company"}],
                "edges": [],
            },
            "graph_meta": {"source": "knowledge_graph", "contextSize": 1},
            "rag_chunks": [],
            "rag_debug": {},
            "debug": {"search": {"status": "done"}},
        }

    monkeypatch.setattr("app.agent.graph.nodes.search_subagent_node", _fake_search_node)
    monkeypatch.setattr("app.agent.graph.builder.search_subagent_node", _fake_search_node)
    agent_services.reset_runtime_for_tests()

    with app.app_context():
        payload = agent_services.generate_reply_payload(
            role="investor",
            system_prompt="system",
            user_message="",
            user_id=7,
            workspace_id="ws-kg",
            entity="京东方",
            intent="股权关系",
            agent_trace_enabled=True,
            agent_trace_debug_details_enabled=True,
        )

    assert payload["reply"] == "主 agent 总结了知识图谱结果"
    assert payload["graph"]["nodes"][0]["label"] == "京东方"
    assert payload["graphMeta"]["source"] == "knowledge_graph"
    assert [step["id"] for step in payload["trace"]["steps"]] == ["planner", "search_subagent", "compose_answer", "citations"]


def test_generate_reply_payload_runs_robotics_through_analysis_orchestration(app, monkeypatch):
    captured = {"system_content": ""}

    class _FakeResponse:
        def __init__(self, content: str):
            self.content = content

    class _FakeChatOpenAI:
        def __init__(self, *args, **kwargs):
            pass

        def invoke(self, messages):
            captured["system_content"] = str(messages[0].content)
            return _FakeResponse("主 agent 汇总了分析模块结果")

    app.config["AGENT_KNOWLEDGE_GRAPH_ENABLED"] = False
    app.config["RAG_ENABLED"] = False
    app.config["AGENT_WEBSEARCH_ENABLED"] = False
    app.config["AGENT_MCP_ENABLED"] = False
    app.config["AI_PROVIDER"] = "openai"
    app.config["AI_MODEL"] = "test-model"
    app.config["AI_API_KEY"] = "test-key"
    app.config["AI_TIMEOUT_SECONDS"] = 10
    app.config["AI_BASE_URL"] = ""
    monkeypatch.setattr(agent_services, "ChatOpenAI", _FakeChatOpenAI)

    def _fake_run_robotics(payload):
        assert payload["enterpriseName"] == "石头科技"
        assert payload["timeRange"] == "近30天"
        assert payload["focus"] == "订单与政策"
        return {
            "status": "done",
            "runId": "rrisk_parent_001",
            "result": {
                "summary": {
                    "opportunity": "政策支持和订单增长构成主要机会。",
                    "risk": "竞争节奏和采购兑现存在波动。",
                }
            },
            "documentHandoff": {
                "schemaVersion": "robotics_document_handoff.v1",
                "title": "石头科技风险机会简报",
            },
            "limitations": ["政策样本窗口有限"],
        }

    monkeypatch.setattr("app.agent.graph.analysis_modules.run_robotics_risk_subagent", _fake_run_robotics)
    agent_services.reset_runtime_for_tests()

    with app.app_context():
        payload = agent_services.generate_reply_payload(
            role="investor",
            system_prompt="system",
            user_message="请开始机器人风险机会分析",
            user_id=7,
            workspace_id="ws-analysis",
            enabled_analysis_modules=["robotics_risk"],
            analysis_shared_inputs={
                "enterpriseName": "石头科技",
                "timeRange": "近30天",
                "reportGoal": "形成机器人行业风险机会简报",
            },
            analysis_module_inputs={"robotics_risk": {"focus": "订单与政策"}},
            agent_trace_enabled=True,
            agent_trace_debug_details_enabled=True,
        )

    assert payload["reply"] == "主 agent 汇总了分析模块结果"
    assert payload["analysisResults"]["robotics_risk"]["runId"] == "rrisk_parent_001"
    assert payload["analysisHandoffBundle"]["enabledModules"] == ["robotics_risk"]
    assert payload["analysisHandoffBundle"]["documentHandoffs"]["robotics_risk"]["title"] == "石头科技风险机会简报"
    assert "分析模块编排结果" in captured["system_content"]
    assert [step["id"] for step in payload["trace"]["steps"]] == [
        "planner",
        "analysis_intake",
        "analysis_modules",
        "compose_answer",
        "citations",
    ]


def test_workspace_chat_passes_entity_and_intent_hints(client, db_session, monkeypatch):
    user = User(email="chat-kg@example.com", nickname="ChatKg", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    captured_kwargs: dict[str, object] = {}

    def _fake_generate_reply_payload(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "reply": "graph answer",
            "citations": [],
            "sources": [],
            "noEvidence": False,
            "graph": {
                "nodes": [{"id": "boe", "label": "京东方", "type": "company"}],
                "edges": [],
            },
            "graphMeta": {"source": "knowledge_graph", "contextSize": 1},
        }

    monkeypatch.setattr("app.workspace.routes.generate_reply_payload", _fake_generate_reply_payload)

    response = client.post(
        "/api/workspace/chat",
        json=_chat_payload("请查知识图谱", entity="京东方", intent="股权关系"),
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert captured_kwargs["entity"] == "京东方"
    assert captured_kwargs["intent"] == "股权关系"
    assert payload["graph"]["nodes"][0]["label"] == "京东方"
    assert payload["graphMeta"]["contextSize"] == 1


def test_workspace_chat_passes_analysis_module_payloads(client, db_session, monkeypatch):
    user = User(email="chat-analysis@example.com", nickname="ChatAnalysis", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    captured_kwargs: dict[str, object] = {}

    def _fake_generate_reply_payload(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "reply": "analysis answer",
            "citations": [],
            "sources": [],
            "noEvidence": False,
            "analysisResults": {
                "robotics_risk": {
                    "moduleId": "robotics_risk",
                    "status": "done",
                    "runId": "rrisk_001",
                    "summary": "机器人政策和订单信号已汇总。",
                }
            },
            "analysisHandoffBundle": {
                "enabledModules": ["robotics_risk"],
                "sharedInputSummary": {"enterpriseName": "石头科技"},
            },
            "graph": {},
            "graphMeta": {},
        }

    monkeypatch.setattr("app.workspace.routes.generate_reply_payload", _fake_generate_reply_payload)

    response = client.post(
        "/api/workspace/chat",
        json=_chat_payload(
            "请开始机器人行业风险机会分析",
            enabledAnalysisModules=["robotics_risk"],
            analysisSharedInputs={
                "enterpriseName": "石头科技",
                "timeRange": "近30天",
                "reportGoal": "形成风险机会简报",
            },
            analysisModuleInputs={"robotics_risk": {"focus": "订单与政策"}},
        ),
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert captured_kwargs["enabled_analysis_modules"] == ["robotics_risk"]
    assert captured_kwargs["analysis_shared_inputs"]["enterpriseName"] == "石头科技"
    assert captured_kwargs["analysis_module_inputs"]["robotics_risk"]["focus"] == "订单与政策"
    assert payload["analysisHandoffBundle"]["enabledModules"] == ["robotics_risk"]
    assert payload["analysisResults"]["robotics_risk"]["runId"] == "rrisk_001"


def test_workspace_chat_restores_persisted_analysis_session_between_turns(client, db_session, monkeypatch):
    user = User(email="chat-analysis-session@example.com", nickname="ChatAnalysisSession", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    captured_calls: list[dict[str, object]] = []

    def _fake_generate_reply_payload(**kwargs):
        captured_calls.append(kwargs)
        restored_session = kwargs.get("analysis_session_state")
        if isinstance(restored_session, dict) and restored_session.get("slotValues"):
            return {
                "reply": "second analysis answer",
                "citations": [],
                "sources": [],
                "noEvidence": False,
                "analysisSession": restored_session,
                "graph": {},
                "graphMeta": {},
            }
        return {
            "reply": "first analysis answer",
            "citations": [],
            "sources": [],
            "noEvidence": False,
            "analysisSession": {
                "status": "collecting",
                "revision": 1,
                "enabledModules": ["robotics_risk"],
                "slotValues": {"enterprise_name": "石头科技"},
                "slotStates": {
                    "enterprise_name": {
                        "status": "resolved",
                        "updatedRevision": 1,
                        "value": "石头科技",
                    }
                },
                "missingSlots": ["time_range"],
                "questionPlan": [
                    {
                        "groupId": "time_range",
                        "slotIds": ["time_range"],
                        "requiredSlotIds": ["time_range"],
                        "labels": ["时间范围"],
                        "question": "请补充时间范围。",
                    }
                ],
                "moduleStates": {},
                "moduleResults": {},
                "compatibility": {
                    "legacySharedInputs": {"enterpriseName": "石头科技"},
                    "legacyModuleInputs": {},
                },
                "handoffBundle": {},
            },
            "graph": {},
            "graphMeta": {},
        }

    monkeypatch.setattr("app.workspace.routes.generate_reply_payload", _fake_generate_reply_payload)

    first = client.post(
        "/api/workspace/chat",
        json=_chat_payload(
            "开始做机器人行业分析",
            "analysis-session-conv",
            enabledAnalysisModules=["robotics_risk"],
        ),
        headers=headers,
    )
    assert first.status_code == 200
    first_payload = first.get_json()["data"]
    assert first_payload["analysisSession"]["sessionId"].startswith("asess_")
    assert first_payload["analysisSession"]["slotValues"]["enterprise_name"] == "石头科技"

    second = client.post(
        "/api/workspace/chat",
        json=_chat_payload("继续", "analysis-session-conv"),
        headers=headers,
    )
    assert second.status_code == 200
    second_payload = second.get_json()["data"]
    assert captured_calls[1]["analysis_session_state"]["sessionId"] == first_payload["analysisSession"]["sessionId"]
    assert captured_calls[1]["analysis_session_state"]["slotValues"]["enterprise_name"] == "石头科技"
    assert second_payload["analysisSession"]["sessionId"] == first_payload["analysisSession"]["sessionId"]

    db_session.expire_all()
    rows = db_session.execute(select(AnalysisSession).where(AnalysisSession.user_id == user.id)).scalars().all()
    assert len(rows) == 1
    assert rows[0].session_id == first_payload["analysisSession"]["sessionId"]


def test_workspace_chat_stream_emits_deltas_and_final_metadata(client, app, db_session, monkeypatch):
    user = User(email="chat-stream@example.com", nickname="ChatStream", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    app.config["AGENT_TRACE_VISUALIZATION_ENABLED"] = True
    monkeypatch.setattr(
        "app.workspace.routes.generate_reply_payload",
        lambda **kwargs: {
            "reply": "这是一个流式回复。",
            "citations": [{"source": "annual-report.pdf", "chunk_id": "chunk-1", "page": 3, "section": "风险"}],
            "sources": [
                {
                    "id": "rag:annual-report.pdf",
                    "kind": "rag",
                    "title": "annual-report.pdf",
                    "source": "annual-report.pdf",
                    "pages": [3],
                    "sections": ["风险"],
                    "chunkIds": ["chunk-1"],
                    "citationCount": 1,
                }
            ],
            "noEvidence": False,
            "trace": {"steps": [{"id": "planner", "status": "done"}]},
            "graph": {
                "nodes": [{"id": "node-1", "label": "京东方", "type": "company"}],
                "edges": [],
            },
            "graphMeta": {"source": "knowledge_graph", "contextSize": 1},
        },
    )

    response = client.post(
        "/api/workspace/chat/stream",
        json=_chat_payload("请总结", "conv-stream-meta"),
        headers=headers,
        buffered=True,
    )
    assert response.status_code == 200

    events = [json.loads(line) for line in response.get_data(as_text=True).splitlines() if line.strip()]
    assert events[0]["type"] == "started"
    assert any(event["type"] == "delta" for event in events)
    meta = next(event for event in events if event["type"] == "meta")
    assert meta["sources"][0]["title"] == "annual-report.pdf"
    assert meta["trace"]["steps"][0]["id"] == "planner"
    assert meta["graph"]["nodes"][0]["id"] == "node-1"
    assert meta["graphMeta"]["source"] == "knowledge_graph"
    assert events[-1]["type"] == "done"


def test_workspace_chat_stream_scopes_memory_by_conversation_id(client, db_session, monkeypatch):
    user = User(email="chat-stream-memory@example.com", nickname="StreamMemory", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    captured: list[dict[str, object]] = []

    def _fake_generate_reply_payload(**kwargs):
        captured.append(kwargs)
        return {
            "reply": f"stream reply {len(captured)}",
            "citations": [],
            "sources": [],
            "noEvidence": False,
            "intent": "answer",
            "graph": {},
            "graphMeta": {},
        }

    monkeypatch.setattr("app.workspace.routes.generate_reply_payload", _fake_generate_reply_payload)

    first = client.post(
        "/api/workspace/chat/stream",
        json=_chat_payload("stream A first", "stream-conv-a"),
        headers=headers,
        buffered=True,
    )
    assert first.status_code == 200
    assert captured[0]["conversation_history"] == []

    second = client.post(
        "/api/workspace/chat/stream",
        json=_chat_payload("stream B first", "stream-conv-b"),
        headers=headers,
        buffered=True,
    )
    assert second.status_code == 200
    assert captured[1]["conversation_history"] == []

    third = client.post(
        "/api/workspace/chat/stream",
        json=_chat_payload("stream A second", "stream-conv-a"),
        headers=headers,
        buffered=True,
    )
    assert third.status_code == 200

    third_history = captured[2]["conversation_history"]
    assert isinstance(third_history, list)
    assert any(item.get("role") == "user" and "stream A first" in item.get("content", "") for item in third_history if isinstance(item, dict))
    assert not any(item.get("role") == "user" and "stream B first" in item.get("content", "") for item in third_history if isinstance(item, dict))

    db_session.expire_all()
    threads = db_session.execute(select(AgentConversationThread)).scalars().all()
    assert {item.conversation_id for item in threads} == {"stream-conv-a", "stream-conv-b"}


def test_workspace_chat_job_completes_and_saves_scoped_memory(client, app, db_session, monkeypatch):
    user = User(email="chat-job@example.com", nickname="ChatJob", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200
    app.config["AGENT_CHAT_JOBS_SYNC_EXECUTION"] = True

    captured: list[dict[str, object]] = []

    def _fake_generate_reply_payload(**kwargs):
        captured.append(kwargs)
        return {
            "reply": "job reply",
            "citations": [],
            "sources": [],
            "noEvidence": False,
            "intent": "answer",
            "graph": {},
            "graphMeta": {},
        }

    monkeypatch.setattr("app.agent.jobs.generate_reply_payload", _fake_generate_reply_payload)

    create_response = client.post(
        "/api/workspace/chat/jobs",
        json=_chat_payload("job question", "job-conv-a", workspaceId="ws-job"),
        headers=headers,
    )
    assert create_response.status_code == 202
    job_id = create_response.get_json()["data"]["jobId"]

    job_response = client.get(f"/api/workspace/chat/jobs/{job_id}?workspaceId=ws-job", headers=headers)
    assert job_response.status_code == 200
    job_payload = job_response.get_json()["data"]
    assert job_payload["status"] == "succeeded"
    assert job_payload["result"]["reply"] == "job reply"
    assert job_payload["conversationId"] == "job-conv-a"
    assert captured[0]["conversation_history"] == []

    db_session.expire_all()
    messages = db_session.execute(select(AgentConversationMessage).order_by(AgentConversationMessage.id)).scalars().all()
    assert [(item.role, item.content) for item in messages] == [
        ("user", "job question"),
        ("assistant", "job reply"),
    ]
    thread = db_session.execute(select(AgentConversationThread)).scalar_one()
    assert thread.conversation_id == "job-conv-a"


def test_workspace_chat_job_failure_records_job_without_memory_turn(client, app, db_session, monkeypatch):
    user = User(email="chat-job-fail@example.com", nickname="ChatJobFail", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200
    app.config["AGENT_CHAT_JOBS_SYNC_EXECUTION"] = True

    def _raise_agent_error(**kwargs):
        raise AgentServiceError("configured failure")

    monkeypatch.setattr("app.agent.jobs.generate_reply_payload", _raise_agent_error)

    create_response = client.post(
        "/api/workspace/chat/jobs",
        json=_chat_payload("job fail", "job-conv-fail", workspaceId="ws-job"),
        headers=headers,
    )
    assert create_response.status_code == 202
    job_id = create_response.get_json()["data"]["jobId"]

    job_response = client.get(f"/api/workspace/chat/jobs/{job_id}?workspaceId=ws-job", headers=headers)
    assert job_response.status_code == 200
    job_payload = job_response.get_json()["data"]
    assert job_payload["status"] == "failed"
    assert job_payload["error"] == "configured failure"

    db_session.expire_all()
    assert db_session.execute(select(AgentConversationMessage)).scalars().all() == []


def test_workspace_chat_job_conflict_is_conversation_scoped(client, app, db_session, monkeypatch):
    user = User(email="chat-job-conflict@example.com", nickname="ChatJobConflict", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200
    monkeypatch.setattr("app.workspace.routes.submit_agent_chat_job", lambda app_obj, job_id: None)

    active = AgentChatJob(
        user_id=user.id,
        workspace_id="ws-job",
        role="investor",
        conversation_id="job-conv-active",
        message="still running",
        status="running",
    )
    db_session.add(active)
    db_session.commit()

    conflict = client.post(
        "/api/workspace/chat/jobs",
        json=_chat_payload("second", "job-conv-active", workspaceId="ws-job"),
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["data"]["job"]["jobId"] == active.id

    other = client.post(
        "/api/workspace/chat/jobs",
        json=_chat_payload("other conversation", "job-conv-other", workspaceId="ws-job"),
        headers=headers,
    )
    assert other.status_code == 202
    assert other.get_json()["data"]["conversationId"] == "job-conv-other"


def test_workspace_chat_job_authorization_and_listing_scope(client, db_session):
    owner = User(email="chat-job-owner@example.com", nickname="Owner", password_hash=generate_password_hash("password123"))
    intruder = User(email="chat-job-intruder@example.com", nickname="Intruder", password_hash=generate_password_hash("password123"))
    db_session.add_all([owner, intruder])
    db_session.commit()

    job = AgentChatJob(
        user_id=owner.id,
        workspace_id="ws-owner",
        role="investor",
        conversation_id="owner-conv",
        message="private job",
        status="succeeded",
        result_json={"reply": "private", "citations": [], "sources": [], "noEvidence": False},
    )
    db_session.add(job)
    db_session.commit()

    owner_headers = _auth_headers(client, owner.id)
    owner_get = client.get(f"/api/workspace/chat/jobs/{job.id}?workspaceId=ws-owner", headers=owner_headers)
    assert owner_get.status_code == 200

    intruder_headers = _auth_headers(client, intruder.id)
    intruder_get = client.get(f"/api/workspace/chat/jobs/{job.id}?workspaceId=ws-owner", headers=intruder_headers)
    assert intruder_get.status_code == 404

    intruder_list = client.get(
        "/api/workspace/chat/jobs?workspaceId=ws-owner&conversationId=owner-conv",
        headers=intruder_headers,
    )
    assert intruder_list.status_code == 200
    assert intruder_list.get_json()["data"]["jobs"] == []


def test_grouped_sources_deduplicate_documents_and_preserve_web_links():
    citations = [
        {"source": "annual-report.pdf", "chunk_id": "chunk-1", "page": 3, "section": "风险"},
        {"source": "annual-report.pdf", "chunk_id": "chunk-2", "page": 4, "section": "经营"},
    ]
    output = {
        "search_result": {
            "evidence": [
                {
                    "source_type": "web",
                    "source": "https://Example.com/boe#fragment",
                    "title": "京东方公司概况",
                    "metadata": {"url": "https://Example.com/boe#fragment"},
                },
                {
                    "source_type": "web",
                    "source": "https://example.com/boe",
                    "title": "",
                    "metadata": {"url": "https://example.com/boe"},
                },
            ]
        }
    }

    sources = agent_services._build_grouped_sources(output, citations)
    assert len(sources) == 2
    assert sources[0]["title"] == "annual-report.pdf"
    assert sources[0]["pages"] == [3, 4]
    assert sources[1]["kind"] == "web"
    assert sources[1]["title"] == "京东方公司概况"
    assert sources[1]["url"] == "https://example.com/boe"


def test_workspace_chat_omits_trace_when_visualization_disabled(client, app, db_session, monkeypatch):
    user = User(email="trace-disabled@example.com", nickname="TraceDisabled", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    app.config["AGENT_TRACE_VISUALIZATION_ENABLED"] = False
    monkeypatch.setattr(
        "app.workspace.routes.generate_reply_payload",
        lambda **kwargs: {
            "reply": "agent generated response",
            "citations": [],
            "noEvidence": False,
            "trace": {"steps": [{"id": "planner"}]},
        },
    )

    response = client.post("/api/workspace/chat", json=_chat_payload("请分析风险"), headers=headers)
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert "trace" not in payload


def test_workspace_chat_includes_trace_when_visualization_enabled(client, app, db_session, monkeypatch):
    user = User(email="trace-enabled@example.com", nickname="TraceEnabled", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    app.config["AGENT_TRACE_VISUALIZATION_ENABLED"] = True
    monkeypatch.setattr(
        "app.workspace.routes.generate_reply_payload",
        lambda **kwargs: {
            "reply": "agent generated response",
            "citations": [],
            "noEvidence": False,
            "trace": {"steps": [{"id": "planner", "status": "done"}]},
        },
    )

    response = client.post("/api/workspace/chat", json=_chat_payload("请分析风险"), headers=headers)
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["trace"]["steps"][0]["id"] == "planner"


def test_workspace_chat_with_configured_agent_provider(client, app, db_session, monkeypatch):
    class _FakeChatOpenAI:
        def __init__(self, *args, **kwargs):
            pass

        def invoke(self, messages):
            class _Response:
                content = "agent provider reply"

            return _Response()

    user = User(email="chat-provider@example.com", nickname="ChatProvider", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    app.config["AI_PROVIDER"] = "openai"
    app.config["AI_MODEL"] = "test-model"
    app.config["AI_API_KEY"] = "test-key"
    app.config["AI_TIMEOUT_SECONDS"] = 10
    app.config["AI_BASE_URL"] = ""
    monkeypatch.setattr(agent_services, "ChatOpenAI", _FakeChatOpenAI)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    response = client.post("/api/workspace/chat", json=_chat_payload("hello"), headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["role"] == "investor"
    assert "systemPrompt" in payload["data"]
    assert payload["data"]["reply"] == "agent provider reply"
    assert "citations" in payload["data"]


def test_workspace_chat_supports_role_specific_agent_models(client, app, db_session, monkeypatch):
    created_models: list[str] = []

    class _FakeChatOpenAI:
        def __init__(self, *args, **kwargs):
            created_models.append(str(kwargs.get("model", "")))

        def invoke(self, messages):
            class _Response:
                content = "agent provider reply"

            return _Response()

    user = User(email="chat-role-models@example.com", nickname="ChatRoleModels", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    app.config["AI_PROVIDER"] = "openai"
    app.config["AI_MODEL"] = "fallback-model"
    app.config["AI_API_KEY"] = "fallback-key"
    app.config["AI_TIMEOUT_SECONDS"] = 10
    app.config["AI_BASE_URL"] = ""
    app.config["AGENT_MAIN_AI_MODEL"] = "main-model"
    app.config["AGENT_MAIN_AI_API_KEY"] = "main-key"
    app.config["AGENT_SEARCH_AI_MODEL"] = "search-model"
    app.config["AGENT_SEARCH_AI_API_KEY"] = "search-key"
    app.config["AGENT_MCP_AI_MODEL"] = "mcp-model"
    app.config["AGENT_MCP_AI_API_KEY"] = "mcp-key"
    monkeypatch.setattr(agent_services, "ChatOpenAI", _FakeChatOpenAI)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    response = client.post("/api/workspace/chat", json=_chat_payload("hello"), headers=headers)
    assert response.status_code == 200
    assert created_models == ["main-model", "search-model", "mcp-model"]


def test_workspace_chat_includes_semantic_segment_context(client, app, db_session, monkeypatch):
    captured = {"system_content": ""}

    class _FakeChatOpenAI:
        def __init__(self, *args, **kwargs):
            pass

        def invoke(self, messages):
            captured["system_content"] = str(messages[0].content)

            class _Response:
                content = "agent provider reply with context"

            return _Response()

    user = User(
        email="chat-segment-context@example.com",
        nickname="ChatSegmentContext",
        password_hash=generate_password_hash("password123"),
    )
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    app.config["RAG_ENABLED"] = True
    app.config["RAG_RETRIEVAL_SCORE_THRESHOLD"] = -10.0
    app.config["RAG_AUTO_INDEX_ON_UPLOAD"] = False
    app.config["AI_PROVIDER"] = "openai"
    app.config["AI_MODEL"] = "test-model"
    app.config["AI_API_KEY"] = "test-key"
    app.config["AI_TIMEOUT_SECONDS"] = 10
    app.config["AI_BASE_URL"] = ""
    monkeypatch.setattr(agent_services, "ChatOpenAI", _FakeChatOpenAI)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    upload_response = client.post(
        "/api/rag/upload",
        data={
            "workspaceId": "ws-agent-segment",
            "chunking": '{"strategy":"paragraph"}',
            "file": (
                io.BytesIO("第一句用于检索。第二句用于提供段落上下文。".encode("utf-8")),
                "agent-segment.txt",
            ),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 200
    document_id = upload_response.get_json()["data"]["id"]

    index_response = client.post(
        "/api/rag/index",
        json={"workspaceId": "ws-agent-segment", "documentId": document_id},
        headers=headers,
    )
    assert index_response.status_code == 200
    job_id = index_response.get_json()["data"]["jobId"]

    final_status = ""
    for _ in range(20):
        job_response = client.get(f"/api/rag/jobs/{job_id}?workspaceId=ws-agent-segment", headers=headers)
        assert job_response.status_code == 200
        final_status = job_response.get_json()["data"]["status"]
        if final_status in {"done", "failed"}:
            break
        time.sleep(0.1)
    assert final_status == "done"

    chat_response = client.post(
        "/api/workspace/chat",
        json=_chat_payload("根据文档回答第一句是什么", "conv-segment", workspaceId="ws-agent-segment"),
        headers=headers,
    )
    assert chat_response.status_code == 200
    assert "命中句所在语义段上下文：" in captured["system_content"]
    assert "segment_id=" in captured["system_content"]
    assert "第一句用于检索。第二句用于提供段落上下文。" in captured["system_content"]


def test_workspace_chat_allows_non_openai_provider_config(client, app, db_session, monkeypatch):
    class _FakeChatOpenAI:
        def __init__(self, *args, **kwargs):
            pass

        def invoke(self, messages):
            class _Response:
                content = "agent provider agnostic reply"

            return _Response()

    user = User(email="chat-provider-agnostic@example.com", nickname="ChatProviderAgnostic", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    app.config["AI_PROVIDER"] = "qwen-compatible"
    app.config["AI_MODEL"] = "test-model"
    app.config["AI_API_KEY"] = "test-key"
    app.config["AI_TIMEOUT_SECONDS"] = 10
    app.config["AI_BASE_URL"] = ""
    monkeypatch.setattr(agent_services, "ChatOpenAI", _FakeChatOpenAI)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    response = client.post("/api/workspace/chat", json=_chat_payload("hello"), headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["reply"] == "agent provider agnostic reply"


def test_workspace_chat_returns_502_when_agent_fails(client, db_session, monkeypatch):
    user = User(email="chat3@example.com", nickname="Chat3", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    def _raise_agent_error(**kwargs):
        raise AgentServiceError("runtime failed")

    monkeypatch.setattr("app.workspace.routes.generate_reply_payload", _raise_agent_error)
    response = client.post("/api/workspace/chat", json=_chat_payload("hello"), headers=headers)
    assert response.status_code == 502
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"] == "agent service unavailable"


def test_workspace_chat_returns_502_when_agent_config_missing(client, app, db_session):
    user = User(email="chat4@example.com", nickname="Chat4", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)
    app.config["AI_PROVIDER"] = "openai"
    app.config["AI_MODEL"] = ""
    app.config["AI_API_KEY"] = ""
    app.config["AI_TIMEOUT_SECONDS"] = 10
    app.config["AI_BASE_URL"] = ""

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    response = client.post("/api/workspace/chat", json=_chat_payload("hello"), headers=headers)
    assert response.status_code == 502
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"] == "agent service unavailable"


def test_workspace_chat_search_subagent_with_websearch(client, app, db_session, monkeypatch):
    class _FakeResponse:
        def __init__(self, content: str):
            self.content = content

    class _FakeChatOpenAI:
        def __init__(self, *args, **kwargs):
            pass

        def invoke(self, messages):
            return _FakeResponse("search-subagent reply")

    user = User(email="chat-auto-tool@example.com", nickname="ChatAutoTool", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    app.config["AI_PROVIDER"] = "openai"
    app.config["AI_MODEL"] = "test-model"
    app.config["AI_API_KEY"] = "test-key"
    app.config["AI_TIMEOUT_SECONDS"] = 10
    app.config["AI_BASE_URL"] = ""
    app.config["RAG_ENABLED"] = False
    app.config["AGENT_WEBSEARCH_ENABLED"] = True
    app.config["AGENT_TRACE_VISUALIZATION_ENABLED"] = True
    app.config["AGENT_TRACE_DEBUG_DETAILS_ENABLED"] = False
    app.config["TAVILY_API_KEY"] = "test-tavily-key"
    monkeypatch.setattr(agent_services, "ChatOpenAI", _FakeChatOpenAI)
    called = {"count": 0}

    def _fake_urlopen(request, timeout=0):
        called["count"] += 1
        class _DummyResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "answer": "news summary",
                        "results": [{"title": "a", "url": "https://example.com", "content": "x", "score": 0.9}],
                    }
                ).encode("utf-8")

        return _DummyResponse()

    monkeypatch.setattr("app.agent.tools.websearch.urlopen", _fake_urlopen)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    response = client.post("/api/workspace/chat", json=_chat_payload("帮我搜索一下最新AI监管新闻"), headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["reply"] == "search-subagent reply"
    steps = payload["data"]["trace"]["steps"]
    assert [step["id"] for step in steps] == ["planner", "search_subagent", "compose_answer", "citations"]
    assert all("details" not in step for step in steps)
    search_step = steps[1]
    assert [child["id"] for child in search_step["children"]] == ["web_lookup", "merge_results"]
    assert called["count"] == 1


def test_workspace_chat_mcp_subagent_with_mcp(client, app, db_session, monkeypatch):
    class _FakeResponse:
        def __init__(self, content: str):
            self.content = content

    class _FakeChatOpenAI:
        def __init__(self, *args, **kwargs):
            pass

        def invoke(self, messages):
            return _FakeResponse("mcp-subagent reply")

    user = User(email="chat-auto-mcp@example.com", nickname="ChatAutoMCP", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    app.config["AI_PROVIDER"] = "openai"
    app.config["AI_MODEL"] = "test-model"
    app.config["AI_API_KEY"] = "test-key"
    app.config["AI_TIMEOUT_SECONDS"] = 10
    app.config["AI_BASE_URL"] = ""
    app.config["AGENT_MCP_ENABLED"] = True
    app.config["AGENT_TRACE_VISUALIZATION_ENABLED"] = True
    app.config["AGENT_TRACE_DEBUG_DETAILS_ENABLED"] = True
    app.config["AGENT_MCP_SERVERS_JSON"] = '{"local":{"endpoint":"http://127.0.0.1:8080/mcp"}}'
    monkeypatch.setattr(agent_services, "ChatOpenAI", _FakeChatOpenAI)
    called = {"count": 0}

    def _fake_mcp_urlopen(request, timeout=0):
        called["count"] += 1
        class _DummyResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({"jsonrpc": "2.0", "id": "list-tools", "result": {"tools": []}}).encode("utf-8")

        return _DummyResponse()

    monkeypatch.setattr("app.agent.tools.mcp.urlopen", _fake_mcp_urlopen)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    response = client.post("/api/workspace/chat", json=_chat_payload("列出mcp工具"), headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["reply"] == "mcp-subagent reply"
    steps = payload["data"]["trace"]["steps"]
    assert [step["id"] for step in steps] == ["planner", "mcp_subagent", "compose_answer", "citations"]
    assert "details" in steps[0]
    assert "details" in steps[1]
    assert steps[1]["details"]["artifactKeys"] == ["tools"]
    assert called["count"] == 1


def test_non_chat_endpoint_still_available_without_agent_config(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_me_requires_login(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_cors_preflight_allows_csrf_header(client):
    response = client.options(
        "/api/user/preferences",
        headers={
            "Origin": "http://localhost:4273",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "X-CSRF-Token,Content-Type",
        },
    )
    assert response.status_code == 200
    allow_origin = response.headers.get("Access-Control-Allow-Origin")
    assert allow_origin == "http://localhost:4273"
    allow_headers = response.headers.get("Access-Control-Allow-Headers", "")
    assert "X-CSRF-Token" in allow_headers


def test_cors_preflight_rejects_unlisted_origin(client):
    response = client.options(
        "/api/user/preferences",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "X-CSRF-Token,Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") is None


def test_register_send_code_invalid_email(client):
    response = client.post(
        "/auth/register/send-code",
        json={
            "email": "invalid-email",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 400


def test_register_send_code_rejects_password_mismatch(client):
    response = client.post(
        "/auth/register/send-code",
        json={
            "email": "mismatch@example.com",
            "password": "password123",
            "confirm_password": "password321",
        },
    )
    assert response.status_code == 400


def test_register_verify_code_rejects_invalid_format(client):
    response = client.post(
        "/auth/register/verify-code",
        json={"email": "newuser@example.com", "code": "12ab56"},
    )
    assert response.status_code == 400


def test_forgot_password_verify_code_rejects_short_password(client):
    response = client.post(
        "/auth/forgot-password/verify-code",
        json={
            "email": "reset@example.com",
            "code": "123456",
            "new_password": "123",
            "confirm_password": "123",
        },
    )
    assert response.status_code == 400


def test_update_profile_requires_csrf_when_logged_in(client, db_session):
    user = User(email="csrf@example.com", nickname="CSRF", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id

    response = client.put("/api/user/profile", data={"nickname": "NewName"})
    assert response.status_code == 403


def test_patch_preferences_rejects_invalid_notification_type(client, db_session):
    user = User(email="prefs3@example.com", nickname="Prefs3", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch(
        "/api/user/preferences",
        json={"notifications": {"agentRun": "yes"}},
        headers=headers,
    )
    assert response.status_code == 400


def test_workspace_context_rejects_invalid_role(client, db_session):
    user = User(email="role2@example.com", nickname="Role2", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "unknown"}, headers=headers)
    assert response.status_code == 400


def test_workspace_chat_requires_non_empty_message(client, db_session):
    user = User(email="chat2@example.com", nickname="Chat2", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    response = client.post("/api/workspace/chat", json={"message": "   "}, headers=headers)
    assert response.status_code == 400


@pytest.mark.parametrize("path", ["/api/workspace/chat", "/api/workspace/chat/stream"])
@pytest.mark.parametrize("payload", [{"message": "hello"}, {"message": "hello", "conversationId": "   "}])
def test_workspace_chat_requires_conversation_id(client, db_session, monkeypatch, path, payload):
    user = User(email=f"conversation-required-{path.rsplit('/', 1)[-1]}-{len(payload)}@example.com", nickname="ConvRequired", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "investor"}, headers=headers)
    assert response.status_code == 200

    def _unexpected_agent_call(**kwargs):
        raise AssertionError("Agent runtime should not be invoked without conversationId")

    monkeypatch.setattr("app.workspace.routes.generate_reply_payload", _unexpected_agent_call)

    response = client.post(path, json=payload, headers=headers, buffered=True)
    assert response.status_code == 400
    assert response.get_json()["error"] == "conversationId is required"


def test_workspace_role_selection_persists_in_db(client, db_session):
    user = User(email="role-persist@example.com", nickname="RolePersist", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.patch("/api/workspace/context", json={"role": "enterprise_manager"}, headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["selectedRole"] == "enterprise_manager"

    db_session.expire_all()
    refreshed = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
    assert isinstance(refreshed.preferences, dict)
    workspace = refreshed.preferences.get("workspace")
    assert isinstance(workspace, dict)
    assert workspace.get("role") == "enterprise_manager"
