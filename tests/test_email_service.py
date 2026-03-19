from __future__ import annotations

from flask import Flask

from app.email_service import get_email_sender


class DummySMTP:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.starttls_called = False
        self.login_called = False
        self.sent = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def starttls(self) -> None:
        self.starttls_called = True

    def login(self, username: str, password: str) -> None:
        self.login_called = True

    def send_message(self, msg) -> None:
        self.sent = True



def _smtp_app(security: str) -> Flask:
    app = Flask(__name__)
    app.config.update(
        EMAIL_BACKEND="smtp",
        SMTP_HOST="smtp.example.com",
        SMTP_PORT=587,
        SMTP_USERNAME="user@example.com",
        SMTP_PASSWORD="secret",
        SMTP_FROM="no-reply@example.com",
        SMTP_SECURITY=security,
    )
    return app


def test_smtp_starttls_mode(monkeypatch):
    smtp_instance = DummySMTP("", 0)

    def fake_smtp(host: str, port: int):
        smtp_instance.host = host
        smtp_instance.port = port
        return smtp_instance

    def fake_smtp_ssl(host: str, port: int):
        raise AssertionError("SMTP_SSL should not be used in starttls mode")

    monkeypatch.setattr("app.email_service.smtplib.SMTP", fake_smtp)
    monkeypatch.setattr("app.email_service.smtplib.SMTP_SSL", fake_smtp_ssl)

    app = _smtp_app("starttls")
    with app.app_context():
        sender = get_email_sender()
        sender.send_code("to@example.com", "123456", "reset")

    assert smtp_instance.starttls_called is True
    assert smtp_instance.login_called is True
    assert smtp_instance.sent is True


def test_smtp_ssl_mode(monkeypatch):
    smtp_ssl_instance = DummySMTP("", 0)

    def fake_smtp(host: str, port: int):
        raise AssertionError("SMTP should not be used in ssl mode")

    def fake_smtp_ssl(host: str, port: int):
        smtp_ssl_instance.host = host
        smtp_ssl_instance.port = port
        return smtp_ssl_instance

    monkeypatch.setattr("app.email_service.smtplib.SMTP", fake_smtp)
    monkeypatch.setattr("app.email_service.smtplib.SMTP_SSL", fake_smtp_ssl)

    app = _smtp_app("ssl")
    with app.app_context():
        sender = get_email_sender()
        sender.send_code("to@example.com", "123456", "reset")

    assert smtp_ssl_instance.starttls_called is False
    assert smtp_ssl_instance.login_called is True
    assert smtp_ssl_instance.sent is True


def test_smtp_none_mode(monkeypatch):
    smtp_instance = DummySMTP("", 0)

    def fake_smtp(host: str, port: int):
        smtp_instance.host = host
        smtp_instance.port = port
        return smtp_instance

    monkeypatch.setattr("app.email_service.smtplib.SMTP", fake_smtp)
    monkeypatch.setattr("app.email_service.smtplib.SMTP_SSL", lambda *_: None)

    app = _smtp_app("none")
    with app.app_context():
        sender = get_email_sender()
        sender.send_code("to@example.com", "123456", "reset")

    assert smtp_instance.starttls_called is False
    assert smtp_instance.login_called is True
    assert smtp_instance.sent is True


def test_smtp_rejects_invalid_security():
    app = _smtp_app("invalid")
    with app.app_context():
        try:
            get_email_sender()
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "SMTP_SECURITY must be one of" in str(exc)
