import io
import json
import time

import pytest
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app.agent import services as agent_services
from app.agent.services import AgentServiceError
from app.models import AgentConversationMessage, AgentConversationThread, User


def _auth_headers(client, user_id: int) -> dict[str, str]:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "test-csrf-token"
    return {"X-CSRF-Token": "test-csrf-token"}


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

    response = client.post("/api/workspace/chat", json={"message": "请分析风险"}, headers=headers)
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
    response = client.post("/api/workspace/chat", json={"message": "请分析风险"}, headers=headers)
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

    first_response = client.post("/api/workspace/chat", json={"message": "请分析风险"}, headers=headers)
    assert first_response.status_code == 200
    assert captured[0]["conversation_history"] == []

    db_session.expire_all()
    thread = db_session.execute(select(AgentConversationThread)).scalar_one()
    assert thread.role == role
    messages = db_session.execute(select(AgentConversationMessage).where(AgentConversationMessage.thread_id == thread.id)).scalars().all()
    assert len(messages) == 2

    second_response = client.post("/api/workspace/chat", json={"message": "腾讯"}, headers=headers)
    assert second_response.status_code == 200

    assert len(captured) == 2
    second_history = captured[1]["conversation_history"]
    assert isinstance(second_history, list)
    assert str(captured[1]["conversation_context"]).startswith("最近对话：")
    assert any(item.get("role") == "assistant" and "请补充要分析的公司名称" in item.get("content", "") for item in second_history if isinstance(item, dict))
    assert any(item.get("role") == "user" and "请分析风险" in item.get("content", "") for item in second_history if isinstance(item, dict))

    db_session.commit()
    db_session.expire_all()
    thread = db_session.execute(select(AgentConversationThread)).scalar_one()
    messages = db_session.execute(select(AgentConversationMessage).where(AgentConversationMessage.thread_id == thread.id)).scalars().all()
    assert len(messages) == 4


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

    response = client.post("/api/workspace/chat", json={"message": "请总结"}, headers=headers)
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
        json={"message": "请查知识图谱", "entity": "京东方", "intent": "股权关系"},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert captured_kwargs["entity"] == "京东方"
    assert captured_kwargs["intent"] == "股权关系"
    assert payload["graph"]["nodes"][0]["label"] == "京东方"
    assert payload["graphMeta"]["contextSize"] == 1


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

    response = client.post("/api/workspace/chat/stream", json={"message": "请总结"}, headers=headers, buffered=True)
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

    response = client.post("/api/workspace/chat", json={"message": "请分析风险"}, headers=headers)
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

    response = client.post("/api/workspace/chat", json={"message": "请分析风险"}, headers=headers)
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

    response = client.post("/api/workspace/chat", json={"message": "hello"}, headers=headers)
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

    response = client.post("/api/workspace/chat", json={"message": "hello"}, headers=headers)
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
        json={"message": "根据文档回答第一句是什么", "workspaceId": "ws-agent-segment"},
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

    response = client.post("/api/workspace/chat", json={"message": "hello"}, headers=headers)
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
    response = client.post("/api/workspace/chat", json={"message": "hello"}, headers=headers)
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

    response = client.post("/api/workspace/chat", json={"message": "hello"}, headers=headers)
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

    response = client.post("/api/workspace/chat", json={"message": "帮我搜索一下最新AI监管新闻"}, headers=headers)
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

    response = client.post("/api/workspace/chat", json={"message": "列出mcp工具"}, headers=headers)
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
