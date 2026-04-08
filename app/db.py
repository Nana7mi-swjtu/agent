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
        _ensure_rag_columns(engine)
        _ensure_bankruptcy_columns(engine)


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


def _ensure_rag_columns(engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as conn:
        if "rag_documents" in table_names:
            columns = {col["name"] for col in inspector.get_columns("rag_documents")}
            alter_sql: list[str] = []
            if "derived_text_path" not in columns:
                alter_sql.append("ADD COLUMN derived_text_path VARCHAR(1024) NULL AFTER storage_path")
            if "chunk_strategy" not in columns:
                alter_sql.append("ADD COLUMN chunk_strategy VARCHAR(32) NULL AFTER embedding_dimension")
            if "loader_type" not in columns:
                alter_sql.append("ADD COLUMN loader_type VARCHAR(64) NULL AFTER embedding_dimension")
            if "loader_version" not in columns:
                alter_sql.append("ADD COLUMN loader_version VARCHAR(32) NULL AFTER loader_type")
            if "extraction_method" not in columns:
                alter_sql.append("ADD COLUMN extraction_method VARCHAR(64) NULL AFTER loader_version")
            if "ocr_used" not in columns:
                alter_sql.append("ADD COLUMN ocr_used INT NOT NULL DEFAULT 0 AFTER extraction_method")
            if "ocr_provider" not in columns:
                alter_sql.append("ADD COLUMN ocr_provider VARCHAR(64) NULL AFTER ocr_used")
            if "chunk_provider" not in columns:
                alter_sql.append("ADD COLUMN chunk_provider VARCHAR(64) NULL AFTER chunk_strategy")
            if "chunk_model" not in columns:
                alter_sql.append("ADD COLUMN chunk_model VARCHAR(128) NULL AFTER chunk_provider")
            if "chunk_version" not in columns:
                alter_sql.append("ADD COLUMN chunk_version VARCHAR(32) NULL AFTER chunk_model")
            if "chunk_fallback_used" not in columns:
                alter_sql.append("ADD COLUMN chunk_fallback_used INT NOT NULL DEFAULT 0 AFTER chunk_version")
            if "chunk_fallback_reason" not in columns:
                alter_sql.append("ADD COLUMN chunk_fallback_reason VARCHAR(1024) NULL AFTER chunk_fallback_used")
            if "derived_at" not in columns:
                alter_sql.append("ADD COLUMN derived_at DATETIME NULL AFTER indexed_at")
            if alter_sql:
                conn.execute(text(f"ALTER TABLE rag_documents {', '.join(alter_sql)}"))

        if "rag_chunks" in table_names:
            columns = {col["name"] for col in inspector.get_columns("rag_chunks")}
            alter_sql = []
            if "topic" not in columns:
                alter_sql.append("ADD COLUMN topic VARCHAR(255) NULL AFTER section")
            if "summary" not in columns:
                alter_sql.append("ADD COLUMN summary LONGTEXT NULL AFTER topic")
            if "token_count" not in columns:
                alter_sql.append("ADD COLUMN token_count INT NULL AFTER summary")
            if "start_offset" not in columns:
                alter_sql.append("ADD COLUMN start_offset INT NULL AFTER token_count")
            if "end_offset" not in columns:
                alter_sql.append("ADD COLUMN end_offset INT NULL AFTER start_offset")
            if "strategy_version" not in columns:
                alter_sql.append("ADD COLUMN strategy_version VARCHAR(32) NULL AFTER end_offset")
            if alter_sql:
                conn.execute(text(f"ALTER TABLE rag_chunks {', '.join(alter_sql)}"))

        if "rag_index_jobs" in table_names:
            columns = {col["name"] for col in inspector.get_columns("rag_index_jobs")}
            alter_sql = []
            if "requested_chunk_strategy" not in columns:
                alter_sql.append("ADD COLUMN requested_chunk_strategy VARCHAR(32) NULL AFTER chunks_count")
            if "applied_chunk_strategy" not in columns:
                alter_sql.append("ADD COLUMN applied_chunk_strategy VARCHAR(32) NULL AFTER requested_chunk_strategy")
            if "chunk_provider" not in columns:
                alter_sql.append("ADD COLUMN chunk_provider VARCHAR(64) NULL AFTER applied_chunk_strategy")
            if "chunk_model" not in columns:
                alter_sql.append("ADD COLUMN chunk_model VARCHAR(128) NULL AFTER chunk_provider")
            if "chunk_version" not in columns:
                alter_sql.append("ADD COLUMN chunk_version VARCHAR(32) NULL AFTER chunk_model")
            if "chunk_fallback_used" not in columns:
                alter_sql.append("ADD COLUMN chunk_fallback_used INT NOT NULL DEFAULT 0 AFTER chunk_version")
            if "chunk_fallback_reason" not in columns:
                alter_sql.append("ADD COLUMN chunk_fallback_reason VARCHAR(1024) NULL AFTER chunk_fallback_used")
            if alter_sql:
                conn.execute(text(f"ALTER TABLE rag_index_jobs {', '.join(alter_sql)}"))

        if "rag_query_logs" in table_names:
            columns = {col["name"] for col in inspector.get_columns("rag_query_logs")}
            alter_sql = []
            if "chunk_strategy" not in columns:
                alter_sql.append("ADD COLUMN chunk_strategy VARCHAR(32) NULL AFTER embedding_dimension")
            if "chunk_provider" not in columns:
                alter_sql.append("ADD COLUMN chunk_provider VARCHAR(64) NULL AFTER chunk_strategy")
            if "chunk_model" not in columns:
                alter_sql.append("ADD COLUMN chunk_model VARCHAR(128) NULL AFTER chunk_provider")
            if alter_sql:
                conn.execute(text(f"ALTER TABLE rag_query_logs {', '.join(alter_sql)}"))


def _ensure_bankruptcy_columns(engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "bankruptcy_analysis_records" not in table_names:
        return

    columns = {col["name"] for col in inspector.get_columns("bankruptcy_analysis_records")}
    alter_sql: list[str] = []
    if "enterprise_name" not in columns:
        alter_sql.append("ADD COLUMN enterprise_name VARCHAR(255) NULL AFTER storage_path")
    if "status" not in columns:
        alter_sql.append("ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'uploaded' AFTER enterprise_name")
    if "error_message" not in columns:
        alter_sql.append("ADD COLUMN error_message VARCHAR(2048) NULL AFTER status")
    if "probability" not in columns:
        alter_sql.append("ADD COLUMN probability DOUBLE NULL AFTER error_message")
    if "threshold" not in columns:
        alter_sql.append("ADD COLUMN threshold DOUBLE NULL AFTER probability")
    if "risk_level" not in columns:
        alter_sql.append("ADD COLUMN risk_level VARCHAR(20) NULL AFTER threshold")
    if "result_json" not in columns:
        alter_sql.append("ADD COLUMN result_json JSON NULL AFTER risk_level")
    if "plot_path" not in columns:
        alter_sql.append("ADD COLUMN plot_path VARCHAR(1024) NULL AFTER result_json")
    if "analyzed_at" not in columns:
        alter_sql.append("ADD COLUMN analyzed_at DATETIME NULL AFTER plot_path")
    if "updated_at" not in columns:
        alter_sql.append(
            "ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER created_at"
        )
    if "deleted_at" not in columns:
        alter_sql.append("ADD COLUMN deleted_at DATETIME NULL AFTER updated_at")

    if not alter_sql:
        return

    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE bankruptcy_analysis_records {', '.join(alter_sql)}"))


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
