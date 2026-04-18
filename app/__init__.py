from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from flask import Flask, g, got_request_exception, request, send_from_directory, session
from flask_cors import CORS
from flask_session import Session
from werkzeug.exceptions import HTTPException

from .config import Config
from .agent.jobs import initialize_agent_chat_jobs
from .db import init_db
from .db_bootstrap import ensure_database_exists
from .auth.routes import auth_bp
from .bankruptcy.routes import bankruptcy_bp
from .rag.routes import rag_bp
from .user.routes import user_bp
from .workspace.routes import workspace_bp
from .logging_utils import ACCESS_LOGGER_NAME, REQUEST_ID_HEADER, bind_log_context, clear_log_context, configure_logging

logger = logging.getLogger(__name__)
access_logger = logging.getLogger(ACCESS_LOGGER_NAME)


def _normalize_cors_origins(raw_origins: object) -> tuple[str, ...]:
    if raw_origins is None:
        return ()
    if isinstance(raw_origins, str):
        return tuple(item.strip() for item in raw_origins.split(",") if item.strip())
    if isinstance(raw_origins, (tuple, list, set)):
        return tuple(str(item).strip() for item in raw_origins if str(item).strip())
    raise ValueError("CORS_ALLOWED_ORIGINS must be a comma-separated string or sequence of origins")


def _request_id() -> str:
    inbound = str(request.headers.get(REQUEST_ID_HEADER, "") or "").strip()
    if inbound and len(inbound) <= 128:
        return inbound
    return str(uuid.uuid4())


def _request_workspace_id() -> str | None:
    raw = request.args.get("workspaceId")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    raw = request.form.get("workspaceId")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if request.mimetype == "application/json":
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            workspace_id = payload.get("workspaceId")
            if isinstance(workspace_id, str) and workspace_id.strip():
                return workspace_id.strip()
    return None


def _current_request_user_id() -> int | None:
    user_id = session.get("user_id")
    if isinstance(user_id, int):
        return user_id
    return None


def _bind_request_log_context() -> None:
    bind_log_context(
        request_id=getattr(g, "request_id", None),
        user_id=_current_request_user_id(),
        workspace_id=_request_workspace_id(),
        remote_addr=(request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip() or None,
        method=request.method,
        path=request.path,
    )


def _emit_access_log(status_code: int, response_bytes: int | None = None) -> None:
    _bind_request_log_context()
    started_at = getattr(g, "request_started_at", None)
    latency_ms = int((time.perf_counter() - started_at) * 1000) if isinstance(started_at, float) else 0
    access_logger.info(
        "HTTP request completed",
        extra={
            "event": "http.request.completed",
            "status_code": int(status_code),
            "latency_ms": latency_ms,
            "response_bytes": response_bytes,
            "user_agent": request.headers.get("User-Agent", ""),
        },
    )
    g.access_logged = True


def create_app(config_overrides: dict | None = None) -> Flask:
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    docs_dir = Path(__file__).resolve().parent.parent / "docs"
    app = Flask(__name__, static_folder=str(frontend_dir), static_url_path="")
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    app.extensions["logging"] = configure_logging(app.config, project_root=Path(__file__).resolve().parent.parent)

    ensure_database_exists(app.config["DATABASE_URL"])

    if app.config.get("SESSION_TYPE") == "filesystem":
        session_dir = app.config.get("SESSION_FILE_DIR")
        if session_dir:
            import os

            os.makedirs(session_dir, exist_ok=True)

    Session(app)
    init_db(app)
    if app.config.get("AGENT_CHAT_JOBS_ENABLED", True):
        initialize_agent_chat_jobs(app)

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

    def _log_unhandled_exception(sender, exception, **extra):
        _bind_request_log_context()
        logger.error(
            "Unhandled request exception",
            exc_info=(type(exception), exception, exception.__traceback__),
            extra={"event": "http.request.unhandled_exception", "status_code": 500},
        )

    got_request_exception.connect(_log_unhandled_exception, app, weak=False)

    @app.before_request
    def bind_request_logging_context():
        g.request_id = _request_id()
        g.request_started_at = time.perf_counter()
        g.access_logged = False
        _bind_request_log_context()

    @app.after_request
    def finalize_request_logging(response):
        response.headers[REQUEST_ID_HEADER] = getattr(g, "request_id", "")
        if not getattr(g, "access_logged", False):
            response_bytes = response.calculate_content_length()
            _emit_access_log(response.status_code, response_bytes)
        return response

    @app.teardown_request
    def clear_request_logging_context(exc):
        try:
            if exc is not None and not getattr(g, "access_logged", False):
                status_code = exc.code if isinstance(exc, HTTPException) else 500
                _emit_access_log(status_code)
        finally:
            clear_log_context()

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
