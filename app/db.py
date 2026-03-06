from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from flask import current_app
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def init_db(app) -> None:
    database_url = app.config["DATABASE_URL"]
    if not database_url.startswith("mysql"):
        raise RuntimeError("DATABASE_URL must use MySQL (mysql+pymysql://...)")

    engine_kwargs = {"future": True, "pool_pre_ping": True}

    engine = create_engine(database_url, **engine_kwargs)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    app.extensions["db_engine"] = engine
    app.extensions["db_sessionmaker"] = SessionLocal

    if app.config.get("AUTO_CREATE_DB", False):
        from .models import Base as ModelsBase

        ModelsBase.metadata.create_all(engine)
        _ensure_profile_columns(engine)


def _ensure_profile_columns(engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    columns = {col["name"] for col in inspector.get_columns("users")}
    alter_sql: list[str] = []

    if "nickname" not in columns:
        alter_sql.append("ADD COLUMN nickname VARCHAR(64) NULL AFTER id")
    if "avatar_url" not in columns:
        alter_sql.append("ADD COLUMN avatar_url VARCHAR(512) NULL AFTER email")
    if "updated_at" not in columns:
        alter_sql.append(
            "ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER created_at"
        )
    if "preferences" not in columns:
        alter_sql.append("ADD COLUMN preferences JSON NULL AFTER avatar_url")

    if not alter_sql:
        return

    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE users {', '.join(alter_sql)}"))


def get_session():
    sessionmaker_factory = current_app.extensions["db_sessionmaker"]
    return sessionmaker_factory()


@contextmanager
def session_scope() -> Iterator:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
