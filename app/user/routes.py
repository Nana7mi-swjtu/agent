from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, request, session
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from ..db import session_scope
from ..models import User


user_bp = Blueprint("user", __name__)

NICKNAME_RE = re.compile(r"^[\w\u4e00-\u9fff\-\s]{2,32}$")
DEFAULT_AVATARS = [
    "https://api.dicebear.com/9.x/fun-emoji/svg?seed=cat-lover",
    "https://api.dicebear.com/9.x/adventurer/svg?seed=neko-girl",
    "https://api.dicebear.com/9.x/adventurer/svg?seed=anime-boy",
    "https://api.dicebear.com/9.x/bottts/svg?seed=kitten-bot",
]
DEFAULT_PREFERENCES = {
    "theme": "light",
    "language": "zh-CN",
    "notifications": {
        "agentRun": True,
        "emailPush": False,
    },
}
ALLOWED_THEMES = {"light", "dark"}
ALLOWED_LANGUAGES = {"zh-CN", "en-US"}


def _json_error(message: str, status_code: int, **extras):
    payload = {"ok": False, "error": message}
    payload.update(extras)
    return payload, status_code


def _current_user_id() -> int | None:
    user_id = session.get("user_id")
    if isinstance(user_id, int):
        return user_id
    return None


def _password_strength(password: str) -> str:
    score = 0
    if len(password) >= 8:
        score += 1
    if re.search(r"[A-Z]", password):
        score += 1
    if re.search(r"[a-z]", password):
        score += 1
    if re.search(r"\d", password):
        score += 1
    if re.search(r"[^A-Za-z0-9]", password):
        score += 1

    if score <= 2:
        return "weak"
    if score <= 4:
        return "medium"
    return "strong"


def _normalized_preferences(raw: dict | None) -> dict:
    merged = {
        "theme": DEFAULT_PREFERENCES["theme"],
        "language": DEFAULT_PREFERENCES["language"],
        "notifications": {
            "agentRun": DEFAULT_PREFERENCES["notifications"]["agentRun"],
            "emailPush": DEFAULT_PREFERENCES["notifications"]["emailPush"],
        },
    }

    if not isinstance(raw, dict):
        return merged

    theme = raw.get("theme")
    if theme in ALLOWED_THEMES:
        merged["theme"] = theme

    language = raw.get("language")
    if language in ALLOWED_LANGUAGES:
        merged["language"] = language

    notifications = raw.get("notifications")
    if isinstance(notifications, dict):
        if isinstance(notifications.get("agentRun"), bool):
            merged["notifications"]["agentRun"] = notifications["agentRun"]
        if isinstance(notifications.get("emailPush"), bool):
            merged["notifications"]["emailPush"] = notifications["emailPush"]

    return merged


def _validate_preferences_patch(patch: dict) -> str | None:
    if not isinstance(patch, dict) or not patch:
        return "invalid preferences payload"

    invalid_keys = set(patch.keys()) - {"theme", "language", "notifications"}
    if invalid_keys:
        return f"unsupported preference keys: {', '.join(sorted(invalid_keys))}"

    if "theme" in patch and patch["theme"] not in ALLOWED_THEMES:
        return "theme must be light or dark"

    if "language" in patch and patch["language"] not in ALLOWED_LANGUAGES:
        return "language must be zh-CN or en-US"

    if "notifications" in patch:
        notifications = patch["notifications"]
        if not isinstance(notifications, dict):
            return "notifications must be an object"

        invalid_notice_keys = set(notifications.keys()) - {"agentRun", "emailPush"}
        if invalid_notice_keys:
            return "notifications only supports agentRun and emailPush"

        for key, value in notifications.items():
            if not isinstance(value, bool):
                return f"notifications.{key} must be boolean"

    return None


def _validate_nickname(nickname: str) -> str | None:
    if not nickname:
        return "nickname is required"

    max_len = current_app.config["NICKNAME_MAX_LENGTH"]
    if len(nickname) > max_len:
        return f"nickname must be <= {max_len} characters"

    if not NICKNAME_RE.match(nickname):
        return "nickname contains invalid characters"

    return None


def _avatar_upload_dir() -> Path:
    root = Path(current_app.root_path).parent
    avatar_dir = root / current_app.config["AVATAR_UPLOAD_DIR"]
    avatar_dir.mkdir(parents=True, exist_ok=True)
    return avatar_dir


def _get_file_size(file_storage) -> int:
    stream = file_storage.stream
    current = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(current)
    return size


def _save_avatar(file_storage) -> str:
    filename = secure_filename(file_storage.filename or "")
    if "." not in filename:
        raise ValueError("avatar extension is required")

    ext = filename.rsplit(".", 1)[1].lower()
    allowed = current_app.config["ALLOWED_AVATAR_EXTENSIONS"]
    if ext not in allowed:
        raise ValueError("avatar format is not supported")

    size = _get_file_size(file_storage)
    max_bytes = current_app.config["MAX_AVATAR_BYTES"]
    if size > max_bytes:
        raise ValueError(f"avatar must be <= {max_bytes // 1024} KB")

    avatar_name = f"{uuid4().hex}.{ext}"
    file_storage.save(_avatar_upload_dir() / avatar_name)

    base_url = current_app.config["AVATAR_BASE_URL"].rstrip("/")
    return f"{base_url}/{avatar_name}"


@user_bp.get("/profile")
def get_profile():
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    with session_scope() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            return _json_error("user not found", 404)

        return {
            "ok": True,
            "data": {
                "id": user.id,
                "nickname": user.nickname or "",
                "email": user.email,
                "avatarUrl": user.avatar_url or "",
                "preferences": _normalized_preferences(user.preferences),
                "defaultAvatars": DEFAULT_AVATARS,
            },
        }


@user_bp.put("/profile")
def update_profile():
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    data = request.form if request.form else (request.get_json(silent=True) or {})
    nickname = str(data.get("nickname", "")).strip()
    old_password = str(data.get("old_password", "")).strip()
    new_password = str(data.get("new_password", "")).strip()
    avatar_preset = str(data.get("avatar_preset", "")).strip()

    nickname_error = _validate_nickname(nickname)
    if nickname_error:
        return _json_error(nickname_error, 400)

    if (old_password and not new_password) or (new_password and not old_password):
        return _json_error("old and new password must be provided together", 400)

    min_len = current_app.config["MIN_PASSWORD_LENGTH"]
    if new_password and len(new_password) < min_len:
        return _json_error(f"password must be at least {min_len} characters", 400)

    avatar_file = request.files.get("avatar")
    avatar_url = ""

    if avatar_file and avatar_file.filename:
        try:
            avatar_url = _save_avatar(avatar_file)
        except ValueError as exc:
            return _json_error(str(exc), 400)
    elif avatar_preset:
        if avatar_preset not in DEFAULT_AVATARS:
            return _json_error("avatar preset is invalid", 400)
        avatar_url = avatar_preset

    with session_scope() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            return _json_error("user not found", 404)

        if old_password and new_password:
            if not check_password_hash(user.password_hash, old_password):
                return _json_error("old password is incorrect", 400)
            user.password_hash = generate_password_hash(new_password)

        user.nickname = nickname
        if avatar_url:
            user.avatar_url = avatar_url

        return {
            "ok": True,
            "data": {
                "nickname": user.nickname,
                "email": user.email,
                "avatarUrl": user.avatar_url or "",
                "preferences": _normalized_preferences(user.preferences),
                "passwordStrength": _password_strength(new_password) if new_password else None,
            },
        }


@user_bp.patch("/preferences")
def patch_preferences():
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    patch = request.get_json(silent=True)
    validation_error = _validate_preferences_patch(patch)
    if validation_error:
        return _json_error(validation_error, 400)

    with session_scope() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            return _json_error("user not found", 404)

        current_preferences = _normalized_preferences(user.preferences)

        if "theme" in patch:
            current_preferences["theme"] = patch["theme"]
        if "language" in patch:
            current_preferences["language"] = patch["language"]
        if "notifications" in patch:
            current_preferences["notifications"].update(patch["notifications"])

        user.preferences = current_preferences

        return {
            "ok": True,
            "data": {
                "preferences": current_preferences,
            },
        }


