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

    with client.session_transaction() as sess:
        assert sess.get("user_id") == user.id

    response = client.post("/auth/logout")
    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get("user_id") is None
