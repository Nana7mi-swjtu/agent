from __future__ import annotations

from pathlib import Path

from flask import Flask, request, session
from flask_session import Session

from .config import Config
from .db import init_db
from .db_bootstrap import ensure_database_exists
from .auth.routes import auth_bp


def create_app(config_overrides: dict | None = None) -> Flask:
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    app = Flask(__name__, static_folder=str(frontend_dir), static_url_path="")
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    ensure_database_exists(app.config["DATABASE_URL"])

    if app.config.get("SESSION_TYPE") == "filesystem":
        session_dir = app.config.get("SESSION_FILE_DIR")
        if session_dir:
            import os

            os.makedirs(session_dir, exist_ok=True)

    Session(app)
    init_db(app)

    if app.config.get("EMAIL_BACKEND") == "memory":
        app.extensions["email_outbox"] = []

    app.register_blueprint(auth_bp, url_prefix="/auth")

    csrf_exempt_paths = {
        "/auth/login",
        "/auth/register/send-code",
        "/auth/register/verify-code",
        "/auth/forgot-password/send-code",
        "/auth/forgot-password/verify-code",
    }

    @app.before_request
    def enforce_csrf_for_authenticated_writes():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None

        if request.path in csrf_exempt_paths:
            return None

        if not session.get("user_id"):
            return None

        csrf_header_name = app.config.get("CSRF_HEADER_NAME", "X-CSRF-Token")
        provided_token = request.headers.get(csrf_header_name)
        session_token = session.get("csrf_token")
        if not session_token or provided_token != session_token:
            return {"ok": False, "error": "csrf token missing or invalid"}, 403

        return None

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/health")
    def health_check():
        return {"ok": True}

    return app
