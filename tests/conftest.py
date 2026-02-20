import os

import pytest
from sqlalchemy import text

from app import create_app
from app.db import get_session


@pytest.fixture
def app(tmp_path):
    test_db_url = os.getenv("TEST_DATABASE_URL")
    if not test_db_url:
        pytest.skip("TEST_DATABASE_URL is required for MySQL tests")
    if not test_db_url.startswith("mysql"):
        pytest.skip("TEST_DATABASE_URL must be a MySQL connection string")

    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "DATABASE_URL": test_db_url,
        "AUTO_CREATE_DB": True,
        "EMAIL_BACKEND": "memory",
        "SESSION_TYPE": "filesystem",
        "SESSION_FILE_DIR": str(session_dir),
        "SECRET_KEY": "test-secret",
    }
    app = create_app(config)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db_session(app):
    with app.app_context():
        session = get_session()
        try:
            session.execute(text("DELETE FROM email_codes"))
            session.execute(text("DELETE FROM users"))
            session.commit()
            yield session
        finally:
            session.close()
