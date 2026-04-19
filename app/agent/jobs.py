from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from flask import Flask, current_app
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..logging_utils import bind_log_context, log_audit_event
from ..models import AgentChatJob, User
from ..workspace.roles import ROLE_PRESETS
from .analysis_session import load_analysis_session_state, save_analysis_session_state
from .memory import load_conversation_history, save_conversation_turn
from .services import AgentServiceError, generate_reply_payload

logger = logging.getLogger(__name__)

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCEEDED = "succeeded"
JOB_STATUS_FAILED = "failed"
ACTIVE_JOB_STATUSES = (JOB_STATUS_PENDING, JOB_STATUS_RUNNING)
TERMINAL_JOB_STATUSES = (JOB_STATUS_SUCCEEDED, JOB_STATUS_FAILED)


class AgentChatJobConflict(RuntimeError):
    def __init__(self, active_job: AgentChatJob):
        super().__init__("agent chat job already active for conversation")
        self.active_job = active_job


class AgentChatJobNotFound(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.utcnow()


def _safe_error_message(exc: BaseException) -> str:
    if isinstance(exc, AgentServiceError):
        return str(exc) or "agent service unavailable"
    return "agent job execution failed"


def serialize_job(job: AgentChatJob, *, include_result: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jobId": job.id,
        "status": str(job.status),
        "workspaceId": str(job.workspace_id),
        "role": str(job.role),
        "conversationId": str(job.conversation_id),
        "message": str(job.message),
        "entity": str(job.entity or ""),
        "intent": str(job.intent or ""),
        "error": str(job.error_message or ""),
        "createdAt": job.created_at.isoformat() if job.created_at else "",
        "startedAt": job.started_at.isoformat() if job.started_at else "",
        "completedAt": job.completed_at.isoformat() if job.completed_at else "",
        "updatedAt": job.updated_at.isoformat() if job.updated_at else "",
    }
    if include_result and isinstance(job.result_json, dict):
        payload["result"] = job.result_json
    return payload


def find_active_job(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    role: str,
    conversation_id: str,
) -> AgentChatJob | None:
    return (
        db.execute(
            select(AgentChatJob)
            .where(
                AgentChatJob.user_id == user_id,
                AgentChatJob.workspace_id == workspace_id,
                AgentChatJob.role == role,
                AgentChatJob.conversation_id == conversation_id,
                AgentChatJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(AgentChatJob.created_at, AgentChatJob.id)
            .limit(1)
        )
        .scalars()
        .first()
    )


def create_chat_job(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    role: str,
    conversation_id: str,
    message: str,
    entity: str = "",
    intent: str = "",
) -> AgentChatJob:
    active_job = find_active_job(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
        conversation_id=conversation_id,
    )
    if active_job is not None:
        raise AgentChatJobConflict(active_job)

    job = AgentChatJob(
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
        conversation_id=conversation_id,
        message=message,
        entity=entity or None,
        intent=intent or None,
        status=JOB_STATUS_PENDING,
        result_json=None,
        error_message=None,
        created_at=_utcnow(),
    )
    db.add(job)
    db.flush()
    return job


def get_chat_job(
    db: Session,
    *,
    user_id: int,
    job_id: int,
    workspace_id: str | None = None,
) -> AgentChatJob:
    criteria = [AgentChatJob.id == job_id, AgentChatJob.user_id == user_id]
    if workspace_id:
        criteria.append(AgentChatJob.workspace_id == workspace_id)
    job = db.execute(select(AgentChatJob).where(*criteria)).scalar_one_or_none()
    if job is None:
        raise AgentChatJobNotFound("agent chat job not found")
    return job


def list_chat_jobs_for_conversation(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    conversation_id: str,
    limit: int = 20,
) -> list[AgentChatJob]:
    return (
        db.execute(
            select(AgentChatJob)
            .where(
                AgentChatJob.user_id == user_id,
                AgentChatJob.workspace_id == workspace_id,
                AgentChatJob.conversation_id == conversation_id,
            )
            .order_by(desc(AgentChatJob.created_at), desc(AgentChatJob.id))
            .limit(max(1, min(int(limit), 50)))
        )
        .scalars()
        .all()
    )


def _mark_running(db: Session, job: AgentChatJob) -> None:
    now = _utcnow()
    job.status = JOB_STATUS_RUNNING
    job.started_at = now
    job.updated_at = now
    db.flush()


def _mark_succeeded(db: Session, job: AgentChatJob, result: dict[str, Any]) -> None:
    now = _utcnow()
    job.status = JOB_STATUS_SUCCEEDED
    job.result_json = result
    job.error_message = None
    job.completed_at = now
    job.updated_at = now
    db.flush()


def _mark_failed(db: Session, job: AgentChatJob, error_message: str) -> None:
    now = _utcnow()
    job.status = JOB_STATUS_FAILED
    job.error_message = error_message[:2048]
    job.completed_at = now
    job.updated_at = now
    db.flush()


def initialize_agent_chat_jobs(app: Flask) -> None:
    if "agent_chat_executor" in app.extensions:
        return
    max_workers = int(app.config.get("AGENT_CHAT_JOB_WORKERS", 2))
    app.extensions["agent_chat_executor"] = ThreadPoolExecutor(
        max_workers=max(1, max_workers),
        thread_name_prefix="agent-chat-job",
    )


def submit_agent_chat_job(app: Flask, job_id: int) -> None:
    if bool(app.config.get("AGENT_CHAT_JOBS_SYNC_EXECUTION", False)):
        run_agent_chat_job(app, job_id)
        return

    executor = app.extensions.get("agent_chat_executor")
    if executor is None:
        initialize_agent_chat_jobs(app)
        executor = app.extensions["agent_chat_executor"]
    executor.submit(run_agent_chat_job, app, int(job_id))


def run_agent_chat_job(app: Flask, job_id: int) -> None:
    with app.app_context():
        try:
            with session_scope() as db:
                job = db.execute(select(AgentChatJob).where(AgentChatJob.id == job_id)).scalar_one_or_none()
                if job is None or job.status != JOB_STATUS_PENDING:
                    return
                bind_log_context(user_id=job.user_id, workspace_id=job.workspace_id, job_id=job.id)
                _mark_running(db, job)
                log_audit_event(
                    "workspace.chat.job.started",
                    operation_status="started",
                    resource_type="agent_chat_job",
                    resource_id=str(job.id),
                    conversation_id=job.conversation_id,
                    role=job.role,
                )

            with session_scope() as db:
                job = db.execute(select(AgentChatJob).where(AgentChatJob.id == job_id)).scalar_one_or_none()
                if job is None:
                    return
                bind_log_context(user_id=job.user_id, workspace_id=job.workspace_id, job_id=job.id)
                user = db.execute(select(User).where(User.id == job.user_id)).scalar_one_or_none()
                if user is None:
                    raise AgentServiceError("user not found")
                if job.role not in ROLE_PRESETS:
                    raise AgentServiceError("role is invalid")

                trace_enabled = bool(current_app.config.get("AGENT_TRACE_VISUALIZATION_ENABLED", False))
                trace_details_enabled = bool(current_app.config.get("AGENT_TRACE_DEBUG_DETAILS_ENABLED", False))
                debug_enabled = bool(
                    current_app.config.get("RAG_DEBUG_VISUALIZATION_ENABLED", False)
                    and current_app.config.get("RAG_ENABLED", False)
                )
                preset = ROLE_PRESETS[job.role]
                thread, conversation_history, conversation_context = load_conversation_history(
                    db,
                    user_id=job.user_id,
                    workspace_id=job.workspace_id,
                    role=job.role,
                    conversation_id=job.conversation_id,
                )
                analysis_session_state = load_analysis_session_state(
                    db,
                    user_id=job.user_id,
                    workspace_id=job.workspace_id,
                    role=job.role,
                    conversation_id=job.conversation_id,
                )
                result = generate_reply_payload(
                    role=job.role,
                    system_prompt=preset["systemPrompt"],
                    user_message=job.message,
                    user_id=job.user_id,
                    workspace_id=job.workspace_id,
                    conversation_history=conversation_history,
                    conversation_context=conversation_context,
                    rag_debug_enabled=debug_enabled,
                    entity=str(job.entity or ""),
                    intent=str(job.intent or ""),
                    analysis_session_state=analysis_session_state,
                    agent_trace_enabled=trace_enabled,
                    agent_trace_debug_details_enabled=trace_details_enabled,
                )
                save_conversation_turn(
                    db,
                    thread=thread,
                    user_message=job.message,
                    assistant_result=result,
                    intent=str(result.get("intent", job.intent or "")).strip(),
                    conversation_context=conversation_context,
                )
                persisted_analysis_session = save_analysis_session_state(
                    db,
                    user_id=job.user_id,
                    workspace_id=job.workspace_id,
                    role=job.role,
                    conversation_id=job.conversation_id,
                    payload=result.get("analysisSession"),
                )
                if persisted_analysis_session:
                    result["analysisSession"] = persisted_analysis_session
                _mark_succeeded(db, job, result)
                log_audit_event(
                    "workspace.chat.job.completed",
                    operation_status="succeeded",
                    resource_type="agent_chat_job",
                    resource_id=str(job.id),
                    conversation_id=job.conversation_id,
                    role=job.role,
                )
        except Exception as exc:
            logger.exception("Agent chat job failed", extra={"event": "workspace.chat.job.failed", "job_id": job_id})
            try:
                with session_scope() as db:
                    job = db.execute(select(AgentChatJob).where(AgentChatJob.id == job_id)).scalar_one_or_none()
                    if job is None or job.status in TERMINAL_JOB_STATUSES:
                        return
                    bind_log_context(user_id=job.user_id, workspace_id=job.workspace_id, job_id=job.id)
                    _mark_failed(db, job, _safe_error_message(exc))
                    log_audit_event(
                        "workspace.chat.job.failed",
                        operation_status="failed",
                        resource_type="agent_chat_job",
                        resource_id=str(job.id),
                        conversation_id=job.conversation_id,
                        role=job.role,
                    )
            except Exception:
                logger.exception("Failed to persist agent chat job failure", extra={"event": "workspace.chat.job.failure_persist_failed"})
