from __future__ import annotations

import re

from flask import Blueprint, current_app, request, session
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import session_scope
from ..email_service import get_email_sender
from ..models import User
from .services import issue_code, verify_code


auth_bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _get_payload() -> dict:
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    return request.form.to_dict()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email))


def _json_error(message: str, status_code: int, **extras):
    payload = {"ok": False, "error": message}
    payload.update(extras)
    return payload, status_code


@auth_bp.post("/register/send-code")
def register_send_code():
    data = _get_payload()
    email = _normalize_email(data.get("email", ""))
    password = data.get("password", "")
    confirm = data.get("confirm_password", "")

    if not _is_valid_email(email):
        return _json_error("invalid email", 400)

    min_len = current_app.config["MIN_PASSWORD_LENGTH"]
    if len(password) < min_len:
        return _json_error(f"password must be at least {min_len} characters", 400)
    if password != confirm:
        return _json_error("passwords do not match", 400)

    with session_scope() as db:
        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing:
            return _json_error("email already exists", 400)

        password_hash = generate_password_hash(password)
        code, error, retry_after = issue_code(
            db,
            email=email,
            purpose="register",
            secret=current_app.config["SECRET_KEY"],
            ttl_seconds=current_app.config["CODE_TTL_SECONDS"],
            cooldown_seconds=current_app.config["CODE_RESEND_COOLDOWN_SECONDS"],
            password_hash=password_hash,
        )
        if error == "locked":
            return _json_error("too many attempts, try later", 429, retryAfterSeconds=retry_after)
        if error == "cooldown":
            return _json_error("resend cooldown active", 429, retryAfterSeconds=retry_after)

        get_email_sender().send_code(email, code, "register")

    return {"ok": True, "cooldownSeconds": current_app.config["CODE_RESEND_COOLDOWN_SECONDS"]}


@auth_bp.post("/register/verify-code")
def register_verify_code():
    data = _get_payload()
    email = _normalize_email(data.get("email", ""))
    code = data.get("code", "")

    if not _is_valid_email(email):
        return _json_error("invalid email", 400)
    if not (code.isdigit() and len(code) == 6):
        return _json_error("invalid or expired code", 400)

    with session_scope() as db:
        record, error, retry_after = verify_code(
            db,
            email=email,
            purpose="register",
            code=code,
            secret=current_app.config["SECRET_KEY"],
            ttl_seconds=current_app.config["CODE_TTL_SECONDS"],
            max_attempts=current_app.config["CODE_MAX_ATTEMPTS"],
            lockout_seconds=current_app.config["CODE_LOCKOUT_SECONDS"],
        )
        if error == "locked":
            return _json_error("too many attempts, try later", 429, retryAfterSeconds=retry_after)
        if error == "invalid" or record is None:
            return _json_error("invalid or expired code", 400)

        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing:
            return _json_error("email already exists", 400)
        if not record.password_hash:
            return _json_error("registration data missing", 400)

        user = User(email=email, password_hash=record.password_hash)
        db.add(user)

    return {"ok": True, "redirect": "/login"}


@auth_bp.post("/login")
def login():
    data = _get_payload()
    email = _normalize_email(data.get("email", ""))
    password = data.get("password", "")

    with session_scope() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if not user or not check_password_hash(user.password_hash, password):
            return _json_error("email or password is incorrect", 401)

    session["user_id"] = user.id
    return {"ok": True}


@auth_bp.post("/logout")
def logout():
    session.clear()
    return {"ok": True}


@auth_bp.post("/forgot-password/send-code")
def forgot_password_send_code():
    data = _get_payload()
    email = _normalize_email(data.get("email", ""))

    if not _is_valid_email(email):
        return _json_error("invalid email", 400)

    with session_scope() as db:
        code, error, retry_after = issue_code(
            db,
            email=email,
            purpose="reset",
            secret=current_app.config["SECRET_KEY"],
            ttl_seconds=current_app.config["CODE_TTL_SECONDS"],
            cooldown_seconds=current_app.config["CODE_RESEND_COOLDOWN_SECONDS"],
            password_hash=None,
        )
        if error == "locked":
            return _json_error("too many attempts, try later", 429, retryAfterSeconds=retry_after)
        if error == "cooldown":
            return _json_error("resend cooldown active", 429, retryAfterSeconds=retry_after)

        get_email_sender().send_code(email, code, "reset")

    return {"ok": True, "message": "if the email exists, a code was sent", "cooldownSeconds": current_app.config["CODE_RESEND_COOLDOWN_SECONDS"]}


@auth_bp.post("/forgot-password/verify-code")
def forgot_password_verify_code():
    data = _get_payload()
    email = _normalize_email(data.get("email", ""))
    code = data.get("code", "")
    new_password = data.get("new_password", "")
    confirm = data.get("confirm_password", "")

    if not _is_valid_email(email):
        return _json_error("invalid email", 400)
    if not (code.isdigit() and len(code) == 6):
        return _json_error("invalid or expired code", 400)

    min_len = current_app.config["MIN_PASSWORD_LENGTH"]
    if len(new_password) < min_len:
        return _json_error(f"password must be at least {min_len} characters", 400)
    if new_password != confirm:
        return _json_error("passwords do not match", 400)

    with session_scope() as db:
        record, error, retry_after = verify_code(
            db,
            email=email,
            purpose="reset",
            code=code,
            secret=current_app.config["SECRET_KEY"],
            ttl_seconds=current_app.config["CODE_TTL_SECONDS"],
            max_attempts=current_app.config["CODE_MAX_ATTEMPTS"],
            lockout_seconds=current_app.config["CODE_LOCKOUT_SECONDS"],
        )
        if error == "locked":
            return _json_error("too many attempts, try later", 429, retryAfterSeconds=retry_after)
        if error == "invalid" or record is None:
            return _json_error("invalid or expired code", 400)

        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if not user:
            return _json_error("invalid or expired code", 400)

        user.password_hash = generate_password_hash(new_password)

    return {"ok": True, "redirect": "/login"}
