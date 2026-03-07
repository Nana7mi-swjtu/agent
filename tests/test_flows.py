from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import User


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

    with client.session_transaction() as sess:
        sess["user_id"] = user.id

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

    with client.session_transaction() as sess:
        sess["user_id"] = user.id

    response = client.put(
        "/api/user/profile",
        data={
            "nickname": "Tester",
            "old_password": "bad-old",
            "new_password": "newPass123!",
        },
    )
    assert response.status_code == 400


def test_patch_preferences_partial_update(client, db_session):
    user = User(email="prefs@example.com", nickname="Prefs", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id

    response = client.patch(
        "/api/user/preferences",
        json={"theme": "dark", "notifications": {"emailPush": True}},
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

    with client.session_transaction() as sess:
        sess["user_id"] = user.id

    response = client.patch("/api/user/preferences", json={"theme": "neon"})
    assert response.status_code == 400


def test_workspace_role_selection_and_context(client, db_session):
    user = User(email="role@example.com", nickname="Role", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id

    response = client.get("/api/workspace/context")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["selectedRole"] is None

    response = client.patch("/api/workspace/context", json={"role": "investor"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["selectedRole"] == "investor"
    assert "投资者决策助手" in payload["data"]["systemPrompt"]


def test_workspace_chat_requires_role(client, db_session):
    user = User(email="chat@example.com", nickname="Chat", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id

    response = client.post("/api/workspace/chat", json={"message": "请分析风险"})
    assert response.status_code == 400

    response = client.patch("/api/workspace/context", json={"role": "regulator"})
    assert response.status_code == 200

    response = client.post("/api/workspace/chat", json={"message": "请分析风险"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["role"] == "regulator"
    assert "已收到你的问题" in payload["data"]["reply"]
def test_me_requires_login(client):
    response = client.get("/auth/me")
    assert response.status_code == 401
