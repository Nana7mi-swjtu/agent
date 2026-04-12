from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class AgentConversationThread(Base):
    __tablename__ = "agent_conversation_threads"
    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", "role", name="uq_agent_conversation_threads_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_user_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_assistant_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_clarification_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    messages: Mapped[list["AgentConversationMessage"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
    )


class AgentConversationMessage(Base):
    __tablename__ = "agent_conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agent_conversation_threads.id"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    thread: Mapped["AgentConversationThread"] = relationship(back_populates="messages")


class EmailCode(Base):
    __tablename__ = "email_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class RagDocument(Base):
    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    derived_text_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded", index=True)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    loader_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    loader_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ocr_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    chunk_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    chunk_fallback_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_fallback_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    derived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    chunks: Mapped[list["RagChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["RagIndexJob"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class BankruptcyAnalysisRecord(Base):
    __tablename__ = "bankruptcy_analysis_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    enterprise_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded", index=True)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    plot_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("rag_documents.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strategy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    document: Mapped["RagDocument"] = relationship(back_populates="chunks")


class RagIndexJob(Base):
    __tablename__ = "rag_index_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("rag_documents.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    error_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    chunks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_chunk_strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    applied_chunk_strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    chunk_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    chunk_fallback_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_fallback_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    document: Mapped["RagDocument"] = relationship(back_populates="jobs")


class RagQueryLog(Base):
    __tablename__ = "rag_query_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    filters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    vector_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    embedder_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    chunk_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
