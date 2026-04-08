from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, request, send_from_directory, session
from flask_cors import CORS
from flask_session import Session

from .config import Config
from .db import init_db
from .db_bootstrap import ensure_database_exists
from .auth.routes import auth_bp
from .bankruptcy.routes import bankruptcy_bp
from .rag.routes import rag_bp
from .user.routes import user_bp
from .workspace.routes import workspace_bp

logger = logging.getLogger(__name__)


def _normalize_cors_origins(raw_origins: object) -> tuple[str, ...]:
    if raw_origins is None:
        return ()
    if isinstance(raw_origins, str):
        return tuple(item.strip() for item in raw_origins.split(",") if item.strip())
    if isinstance(raw_origins, (tuple, list, set)):
        return tuple(str(item).strip() for item in raw_origins if str(item).strip())
    raise ValueError("CORS_ALLOWED_ORIGINS must be a comma-separated string or sequence of origins")


def create_app(config_overrides: dict | None = None) -> Flask:
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    docs_dir = Path(__file__).resolve().parent.parent / "docs"
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
    app.register_blueprint(user_bp, url_prefix="/api/user")
    app.register_blueprint(workspace_bp, url_prefix="/api/workspace")
    app.register_blueprint(bankruptcy_bp, url_prefix="/api/bankruptcy")
    app.register_blueprint(rag_bp, url_prefix="/api/rag")

    try:
        cors_origins = _normalize_cors_origins(app.config.get("CORS_ALLOWED_ORIGINS", ()))
        app.config["CORS_ALLOWED_ORIGINS"] = cors_origins
    except ValueError as exc:
        logger.error("Invalid CORS config: %s", exc)
        raise
    if app.config.get("CORS_ENABLED", True):
        if app.config.get("CORS_ALLOW_CREDENTIALS", True) and "*" in cors_origins:
            logger.error("Invalid CORS config: wildcard origin is incompatible with credentials mode")
            raise ValueError("CORS_ALLOWED_ORIGINS cannot include '*' when CORS_ALLOW_CREDENTIALS is true")
        if not cors_origins:
            logger.error("Invalid CORS config: allowed origins list is empty while CORS is enabled")
            raise ValueError("CORS_ALLOWED_ORIGINS cannot be empty when CORS is enabled")
        CORS(
            app,
            resources={
                r"/auth/*": {"origins": cors_origins},
                r"/api/*": {"origins": cors_origins},
            },
            supports_credentials=app.config.get("CORS_ALLOW_CREDENTIALS", True),
            methods=list(app.config.get("CORS_ALLOWED_METHODS", ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"))),
            allow_headers=list(app.config.get("CORS_ALLOWED_HEADERS", ("Content-Type", "X-CSRF-Token", "Authorization"))),
            expose_headers=list(app.config.get("CORS_EXPOSE_HEADERS", ())),
            max_age=app.config.get("CORS_MAX_AGE_SECONDS", 600),
        )

    avatar_url = app.config["AVATAR_BASE_URL"].rstrip("/")

    @app.get(f"{avatar_url}/<path:filename>")
    def uploaded_avatar(filename: str):
        upload_dir = Path(app.root_path).parent / app.config["AVATAR_UPLOAD_DIR"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        return send_from_directory(upload_dir, filename)

    @app.get("/docs/<path:filename>")
    def docs_assets(filename: str):
        docs_dir.mkdir(parents=True, exist_ok=True)
        return send_from_directory(docs_dir, filename)

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
