from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

LongText = Text().with_variant(LONGTEXT(), "mysql")


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
        UniqueConstraint("user_id", "workspace_id", "role", "conversation_id", name="uq_agent_conversation_threads_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
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


class AgentChatJob(Base):
    __tablename__ = "agent_chat_jobs"
    __table_args__ = (
        Index("ix_agent_chat_jobs_scope_status", "user_id", "workspace_id", "role", "conversation_id", "status"),
        Index("ix_agent_chat_jobs_conversation_created", "user_id", "workspace_id", "conversation_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    entity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


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


class RoboticsPolicyDocument(Base):
    __tablename__ = "robotics_policy_documents"
    __table_args__ = (
        UniqueConstraint("policy_id", name="uq_robotics_policy_documents_policy_id"),
        Index("ix_robotics_policy_documents_cache_key", "cache_key"),
        Index("ix_robotics_policy_documents_url_hash", "url_hash"),
        Index("ix_robotics_policy_documents_published", "published_at"),
        Index("ix_robotics_policy_documents_fetched", "fetched_at"),
        Index("ix_robotics_policy_documents_status", "status"),
        Index("ix_robotics_policy_documents_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    url_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issuing_agency: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_text: Mapped[str | None] = mapped_column(LongText, nullable=True)
    matched_keywords_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    relevance_segments_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="fetched")
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", "role", "conversation_id", name="uq_analysis_sessions_scope"),
        UniqueConstraint("session_id", name="uq_analysis_sessions_session_id"),
        Index("ix_analysis_sessions_scope_status", "user_id", "workspace_id", "role", "conversation_id", "status"),
        Index("ix_analysis_sessions_updated", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="collecting", index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled_modules_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    slot_values_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    slot_states_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    missing_slots_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    question_plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    module_states_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    module_results_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    compatibility_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    bundle_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"
    __table_args__ = (
        UniqueConstraint("report_id", name="uq_analysis_reports_report_id"),
        Index("ix_analysis_reports_scope_created", "user_id", "workspace_id", "role", "conversation_id", "created_at"),
        Index("ix_analysis_reports_session", "analysis_session_id", "analysis_session_revision"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    analysis_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    analysis_session_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled_modules_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    module_run_ids_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifact_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    markdown_body: Mapped[str | None] = mapped_column(LongText, nullable=True)
    html_body: Mapped[str | None] = mapped_column(LongText, nullable=True)
    visual_assets_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attachments_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    limitations_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    download_metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class AnalysisModuleArtifact(Base):
    __tablename__ = "analysis_module_artifacts"
    __table_args__ = (
        UniqueConstraint("artifact_id", name="uq_analysis_module_artifacts_artifact_id"),
        Index("ix_analysis_module_artifacts_scope_created", "user_id", "workspace_id", "role", "conversation_id", "created_at"),
        Index("ix_analysis_module_artifacts_session", "analysis_session_id", "analysis_session_revision"),
        Index("ix_analysis_module_artifacts_module_run", "module_id", "module_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    analysis_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    analysis_session_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    module_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    module_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed", index=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="text/markdown")
    markdown_body: Mapped[str | None] = mapped_column(LongText, nullable=True)
    text_body: Mapped[str | None] = mapped_column(LongText, nullable=True)
    artifact_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class RoboticsCninfoAnnouncement(Base):
    __tablename__ = "robotics_cninfo_announcements"
    __table_args__ = (
        UniqueConstraint("announcement_id", name="uq_robotics_cninfo_announcements_announcement_id"),
        Index("ix_robotics_cninfo_announcements_cache_key", "cache_key"),
        Index("ix_robotics_cninfo_announcements_adjunct_hash", "adjunct_url_hash"),
        Index("ix_robotics_cninfo_announcements_pdf_hash", "pdf_url_hash"),
        Index("ix_robotics_cninfo_announcements_sec_code_time", "sec_code", "announcement_time"),
        Index("ix_robotics_cninfo_announcements_sec_name", "sec_name"),
        Index("ix_robotics_cninfo_announcements_fetched", "fetched_at"),
        Index("ix_robotics_cninfo_announcements_status", "status"),
        Index("ix_robotics_cninfo_announcements_parse_status", "parse_status"),
        Index("ix_robotics_cninfo_announcements_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    announcement_id: Mapped[str] = mapped_column(String(128), nullable=False)
    cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sec_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sec_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    org_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    announcement_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    announcement_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    adjunct_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    adjunct_url_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pdf_url_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pdf_storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_text: Mapped[str | None] = mapped_column(LongText, nullable=True)
    matched_keywords_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="fetched")
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parse_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    parse_error: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class RoboticsBiddingDocument(Base):
    __tablename__ = "robotics_bidding_documents"
    __table_args__ = (
        UniqueConstraint("notice_id", name="uq_robotics_bidding_documents_notice_id"),
        Index("ix_robotics_bidding_documents_cache_key", "cache_key"),
        Index("ix_robotics_bidding_documents_url_hash", "url_hash"),
        Index("ix_robotics_bidding_documents_published", "published_at"),
        Index("ix_robotics_bidding_documents_fetched", "fetched_at"),
        Index("ix_robotics_bidding_documents_status", "status"),
        Index("ix_robotics_bidding_documents_region", "region"),
        Index("ix_robotics_bidding_documents_enterprise", "matched_enterprise_name"),
        Index("ix_robotics_bidding_documents_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notice_id: Mapped[str] = mapped_column(String(128), nullable=False)
    cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    url_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notice_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    project_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    project_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    winning_bidder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[str | None] = mapped_column(String(128), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_text: Mapped[str | None] = mapped_column(LongText, nullable=True)
    matched_enterprise_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    matched_keywords_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="fetched")
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class RoboticsListedCompanyProfile(Base):
    __tablename__ = "robotics_listed_company_profiles"
    __table_args__ = (
        UniqueConstraint("profile_key", name="uq_robotics_listed_company_profiles_key"),
        Index("ix_robotics_listed_company_profiles_stock_code", "stock_code"),
        Index("ix_robotics_listed_company_profiles_company_name", "company_name"),
        Index("ix_robotics_listed_company_profiles_security_name", "security_name"),
        Index("ix_robotics_listed_company_profiles_supported", "is_supported"),
        Index("ix_robotics_listed_company_profiles_updated", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_key: Mapped[str] = mapped_column(String(128), nullable=False)
    stock_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    market: Mapped[str | None] = mapped_column(String(64), nullable=True)
    security_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    industry_segments_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    robotics_keywords_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cninfo_column: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cninfo_org_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_supported: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unsupported_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class RoboticsInsightRun(Base):
    __tablename__ = "robotics_insight_runs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_robotics_insight_runs_run_id"),
        Index("ix_robotics_insight_runs_enterprise", "enterprise_name"),
        Index("ix_robotics_insight_runs_stock_code", "stock_code"),
        Index("ix_robotics_insight_runs_status", "status"),
        Index("ix_robotics_insight_runs_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    enterprise_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stock_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    handoff_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


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
