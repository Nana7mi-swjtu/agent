from __future__ import annotations

import os

import pytest

from app import create_app


def _test_db_url() -> str:
    test_db_url = os.getenv("TEST_DATABASE_URL")
    if not test_db_url:
        pytest.skip("TEST_DATABASE_URL is required for MySQL tests")
    if not test_db_url.startswith("mysql"):
        pytest.skip("TEST_DATABASE_URL must be a MySQL connection string")
    return test_db_url


def _base_config(tmp_path) -> dict[str, object]:
    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    return {
        "DATABASE_URL": _test_db_url(),
        "AUTO_CREATE_DB": True,
        "EMAIL_BACKEND": "memory",
        "SESSION_TYPE": "filesystem",
        "SESSION_FILE_DIR": str(session_dir),
        "SECRET_KEY": "test-secret",
        "CORS_ENABLED": True,
    }


def test_create_app_rejects_wildcard_origin_with_credentials(tmp_path):
    config = _base_config(tmp_path) | {
        "CORS_ALLOWED_ORIGINS": ("*",),
        "CORS_ALLOW_CREDENTIALS": True,
    }
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS cannot include '\\*'"):
        create_app(config)


def test_create_app_rejects_empty_cors_origins_when_enabled(tmp_path):
    config = _base_config(tmp_path) | {
        "CORS_ALLOWED_ORIGINS": (),
        "CORS_ALLOW_CREDENTIALS": True,
    }
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS cannot be empty"):
        create_app(config)
