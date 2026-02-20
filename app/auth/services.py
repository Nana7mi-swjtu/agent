from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select, update

from ..models import EmailCode


def utcnow() -> datetime:
    return datetime.utcnow()


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), code.encode("utf-8"), hashlib.sha256).hexdigest()


def get_latest_code(session, email: str, purpose: str) -> EmailCode | None:
    stmt = (
        select(EmailCode)
        .where(EmailCode.email == email, EmailCode.purpose == purpose)
        .order_by(EmailCode.created_at.desc())
    )
    return session.execute(stmt).scalars().first()


def invalidate_active_codes(session, email: str, purpose: str, now: datetime) -> None:
    stmt = (
        update(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.used_at.is_(None),
            EmailCode.expires_at > now,
        )
        .values(used_at=now)
    )
    session.execute(stmt)


def issue_code(
    session,
    *,
    email: str,
    purpose: str,
    secret: str,
    ttl_seconds: int,
    cooldown_seconds: int,
    password_hash: str | None = None,
):
    now = utcnow()
    latest = get_latest_code(session, email, purpose)

    if latest and latest.locked_until and latest.locked_until > now:
        remaining = int((latest.locked_until - now).total_seconds())
        return None, "locked", remaining

    if latest and (now - latest.created_at).total_seconds() < cooldown_seconds:
        remaining = int(cooldown_seconds - (now - latest.created_at).total_seconds())
        return None, "cooldown", max(remaining, 1)

    invalidate_active_codes(session, email, purpose, now)

    code = generate_code()
    code_hash = hash_code(code, secret)

    record = EmailCode(
        email=email,
        purpose=purpose,
        code_hash=code_hash,
        password_hash=password_hash,
        expires_at=now + timedelta(seconds=ttl_seconds),
        used_at=None,
        attempt_count=0,
        locked_until=None,
        created_at=now,
    )
    session.add(record)
    return code, None, None


def verify_code(
    session,
    *,
    email: str,
    purpose: str,
    code: str,
    secret: str,
    ttl_seconds: int,
    max_attempts: int,
    lockout_seconds: int,
):
    now = utcnow()
    record = get_latest_code(session, email, purpose)

    if not record:
        return None, "invalid", None

    if record.locked_until and record.locked_until > now:
        remaining = int((record.locked_until - now).total_seconds())
        return None, "locked", remaining

    if record.used_at is not None or record.expires_at <= now:
        return None, "invalid", None

    expected_hash = hash_code(code, secret)
    if not hmac.compare_digest(expected_hash, record.code_hash):
        record.attempt_count += 1
        if record.attempt_count >= max_attempts:
            record.locked_until = now + timedelta(seconds=lockout_seconds)
        session.flush()
        return None, "invalid", None

    record.used_at = now
    session.flush()
    return record, None, None
