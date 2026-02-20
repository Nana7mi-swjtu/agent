from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from flask import current_app
from sqlalchemy import create_engine
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
