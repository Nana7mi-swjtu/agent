from __future__ import annotations

from pathlib import Path

from flask import Flask
from flask import send_from_directory
from flask_session import Session

from .config import Config
from .db import init_db
from .db_bootstrap import ensure_database_exists
from .auth.routes import auth_bp
from .user.routes import user_bp
from .workspace.routes import workspace_bp


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
    app.register_blueprint(user_bp, url_prefix="/api/user")
    app.register_blueprint(workspace_bp, url_prefix="/api/workspace")

    avatar_url = app.config["AVATAR_BASE_URL"].rstrip("/")

    @app.get(f"{avatar_url}/<path:filename>")
    def uploaded_avatar(filename: str):
        upload_dir = Path(app.root_path).parent / app.config["AVATAR_UPLOAD_DIR"]
        upload_dir.mkdir(parents=True, exist_ok=True)
        return send_from_directory(upload_dir, filename)

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/health")
    def health_check():
        return {"ok": True}

    return app
