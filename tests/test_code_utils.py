from datetime import timedelta

from app.auth.services import generate_code, hash_code, issue_code, utcnow, verify_code
from app.models import EmailCode


def test_generate_code_format():
    code = generate_code()
    assert code.isdigit()
    assert len(code) == 6


def test_hash_code_is_deterministic():
    assert hash_code("123456", "secret") == hash_code("123456", "secret")


def test_expired_code_rejected(db_session):
    now = utcnow()
    record = EmailCode(
        email="user@example.com",
        purpose="register",
        code_hash=hash_code("123456", "secret"),
        expires_at=now - timedelta(seconds=1),
        used_at=None,
        attempt_count=0,
        locked_until=None,
        created_at=now - timedelta(seconds=5),
    )
    db_session.add(record)
    db_session.commit()

    _, error, _ = verify_code(
        db_session,
        email="user@example.com",
        purpose="register",
        code="123456",
        secret="secret",
        ttl_seconds=600,
        max_attempts=5,
        lockout_seconds=600,
    )
    assert error == "invalid"


def test_lockout_after_failed_attempts(db_session):
    now = utcnow()
    record = EmailCode(
        email="user2@example.com",
        purpose="reset",
        code_hash=hash_code("123456", "secret"),
        expires_at=now + timedelta(seconds=600),
        used_at=None,
        attempt_count=4,
        locked_until=None,
        created_at=now,
    )
    db_session.add(record)
    db_session.commit()

    _, error, _ = verify_code(
        db_session,
        email="user2@example.com",
        purpose="reset",
        code="000000",
        secret="secret",
        ttl_seconds=600,
        max_attempts=5,
        lockout_seconds=600,
    )
    db_session.refresh(record)
    assert error == "invalid"
    assert record.locked_until is not None


def test_resend_cooldown_enforced(db_session):
    code, error, retry_after = issue_code(
        db_session,
        email="cooldown@example.com",
        purpose="register",
        secret="secret",
        ttl_seconds=600,
        cooldown_seconds=60,
        password_hash=None,
    )
    assert error is None
    assert code is not None
    db_session.commit()

    _, error, retry_after = issue_code(
        db_session,
        email="cooldown@example.com",
        purpose="register",
        secret="secret",
        ttl_seconds=600,
        cooldown_seconds=60,
        password_hash=None,
    )
    assert error == "cooldown"
    assert retry_after is not None


def test_new_code_invalidates_previous_active(db_session):
    now = utcnow()
    record = EmailCode(
        email="invalidate@example.com",
        purpose="reset",
        code_hash=hash_code("123456", "secret"),
        expires_at=now + timedelta(seconds=600),
        used_at=None,
        attempt_count=0,
        locked_until=None,
        created_at=now - timedelta(seconds=120),
    )
    db_session.add(record)
    db_session.commit()

    code, error, _ = issue_code(
        db_session,
        email="invalidate@example.com",
        purpose="reset",
        secret="secret",
        ttl_seconds=600,
        cooldown_seconds=60,
        password_hash=None,
    )
    assert error is None
    assert code is not None
    db_session.commit()

    db_session.refresh(record)
    assert record.used_at is not None
