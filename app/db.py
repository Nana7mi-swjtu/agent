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
        _ensure_agent_conversation_columns(engine)
        _ensure_agent_chat_job_columns(engine)
        _ensure_rag_columns(engine)
        _ensure_bankruptcy_columns(engine)
        _ensure_robotics_evidence_columns(engine)


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


def _ensure_agent_conversation_columns(engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "agent_conversation_threads" not in table_names:
        return

    columns = {col["name"] for col in inspector.get_columns("agent_conversation_threads")}
    with engine.begin() as conn:
        if "conversation_id" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE agent_conversation_threads "
                    "ADD COLUMN conversation_id VARCHAR(128) NOT NULL AFTER role"
                )
            )

        indexes = {
            item["name"]: tuple(item.get("column_names") or [])
            for item in inspect(engine).get_indexes("agent_conversation_threads")
        }
        current_scope = indexes.get("uq_agent_conversation_threads_scope")
        if current_scope == ("user_id", "workspace_id", "role"):
            conn.execute(text("ALTER TABLE agent_conversation_threads DROP INDEX uq_agent_conversation_threads_scope"))
            current_scope = None
        if current_scope != ("user_id", "workspace_id", "role", "conversation_id"):
            conn.execute(
                text(
                    "ALTER TABLE agent_conversation_threads "
                    "ADD UNIQUE KEY uq_agent_conversation_threads_scope "
                    "(user_id, workspace_id, role, conversation_id)"
                )
            )


def _ensure_agent_chat_job_columns(engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "agent_chat_jobs" not in table_names:
        return

    columns = {col["name"] for col in inspector.get_columns("agent_chat_jobs")}
    alter_sql: list[str] = []
    if "entity" not in columns:
        alter_sql.append("ADD COLUMN entity VARCHAR(255) NULL AFTER message")
    if "intent" not in columns:
        alter_sql.append("ADD COLUMN intent VARCHAR(255) NULL AFTER entity")
    if "result_json" not in columns:
        alter_sql.append("ADD COLUMN result_json JSON NULL AFTER status")
    if "error_message" not in columns:
        alter_sql.append("ADD COLUMN error_message VARCHAR(2048) NULL AFTER result_json")
    if "started_at" not in columns:
        alter_sql.append("ADD COLUMN started_at DATETIME NULL AFTER created_at")
    if "completed_at" not in columns:
        alter_sql.append("ADD COLUMN completed_at DATETIME NULL AFTER started_at")
    if "updated_at" not in columns:
        alter_sql.append(
            "ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER completed_at"
        )

    with engine.begin() as conn:
        if alter_sql:
            conn.execute(text(f"ALTER TABLE agent_chat_jobs {', '.join(alter_sql)}"))

        indexes = {item["name"] for item in inspect(engine).get_indexes("agent_chat_jobs")}
        if "ix_agent_chat_jobs_scope_status" not in indexes:
            conn.execute(
                text(
                    "ALTER TABLE agent_chat_jobs "
                    "ADD INDEX ix_agent_chat_jobs_scope_status "
                    "(user_id, workspace_id, role, conversation_id, status)"
                )
            )
        if "ix_agent_chat_jobs_conversation_created" not in indexes:
            conn.execute(
                text(
                    "ALTER TABLE agent_chat_jobs "
                    "ADD INDEX ix_agent_chat_jobs_conversation_created "
                    "(user_id, workspace_id, conversation_id, created_at)"
                )
            )


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


def _ensure_robotics_evidence_columns(engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    expected_tables = {
        "robotics_policy_documents",
        "robotics_cninfo_announcements",
        "robotics_bidding_documents",
        "robotics_listed_company_profiles",
        "robotics_insight_runs",
    }
    if not expected_tables.intersection(table_names):
        return

    index_specs = {
        "robotics_policy_documents": {
            "ix_robotics_policy_documents_cache_key": "(cache_key)",
            "ix_robotics_policy_documents_url_hash": "(url_hash)",
            "ix_robotics_policy_documents_published": "(published_at)",
            "ix_robotics_policy_documents_fetched": "(fetched_at)",
            "ix_robotics_policy_documents_status": "(status)",
            "ix_robotics_policy_documents_content_hash": "(content_hash)",
        },
        "robotics_cninfo_announcements": {
            "ix_robotics_cninfo_announcements_cache_key": "(cache_key)",
            "ix_robotics_cninfo_announcements_adjunct_hash": "(adjunct_url_hash)",
            "ix_robotics_cninfo_announcements_pdf_hash": "(pdf_url_hash)",
            "ix_robotics_cninfo_announcements_sec_code_time": "(sec_code, announcement_time)",
            "ix_robotics_cninfo_announcements_sec_name": "(sec_name)",
            "ix_robotics_cninfo_announcements_fetched": "(fetched_at)",
            "ix_robotics_cninfo_announcements_status": "(status)",
            "ix_robotics_cninfo_announcements_parse_status": "(parse_status)",
            "ix_robotics_cninfo_announcements_content_hash": "(content_hash)",
        },
        "robotics_bidding_documents": {
            "ix_robotics_bidding_documents_cache_key": "(cache_key)",
            "ix_robotics_bidding_documents_url_hash": "(url_hash)",
            "ix_robotics_bidding_documents_published": "(published_at)",
            "ix_robotics_bidding_documents_fetched": "(fetched_at)",
            "ix_robotics_bidding_documents_status": "(status)",
            "ix_robotics_bidding_documents_region": "(region)",
            "ix_robotics_bidding_documents_enterprise": "(matched_enterprise_name)",
            "ix_robotics_bidding_documents_content_hash": "(content_hash)",
        },
        "robotics_listed_company_profiles": {
            "ix_robotics_listed_company_profiles_stock_code": "(stock_code)",
            "ix_robotics_listed_company_profiles_company_name": "(company_name)",
            "ix_robotics_listed_company_profiles_security_name": "(security_name)",
            "ix_robotics_listed_company_profiles_supported": "(is_supported)",
            "ix_robotics_listed_company_profiles_updated": "(updated_at)",
        },
        "robotics_insight_runs": {
            "ix_robotics_insight_runs_enterprise": "(enterprise_name)",
            "ix_robotics_insight_runs_stock_code": "(stock_code)",
            "ix_robotics_insight_runs_status": "(status)",
            "ix_robotics_insight_runs_created": "(created_at)",
        },
    }

    with engine.begin() as conn:
        for table_name, table_indexes in index_specs.items():
            if table_name not in table_names:
                continue
            existing_indexes = {item["name"] for item in inspect(engine).get_indexes(table_name)}
            for index_name, columns_sql in table_indexes.items():
                if index_name not in existing_indexes:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD INDEX {index_name} {columns_sql}"))


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
