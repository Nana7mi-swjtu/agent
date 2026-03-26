import pytest
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app.agent import services as agent_services
from app.agent.services import AgentServiceError
from app.models import User


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


def test_workspace_chat_requires_role(client, db_session, monkeypatch):
    user = User(email="chat@example.com", nickname="Chat", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    headers = _auth_headers(client, user.id)

    response = client.post("/api/workspace/chat", json={"message": "请分析风险"}, headers=headers)
    assert response.status_code == 400

    response = client.patch("/api/workspace/context", json={"role": "regulator"}, headers=headers)
    assert response.status_code == 200

    monkeypatch.setattr("app.workspace.routes.generate_reply", lambda **kwargs: "agent generated response")
    response = client.post("/api/workspace/chat", json={"message": "请分析风险"}, headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["role"] == "regulator"
    assert payload["data"]["reply"] == "agent generated response"


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

    monkeypatch.setattr("app.workspace.routes.generate_reply", _raise_agent_error)
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
