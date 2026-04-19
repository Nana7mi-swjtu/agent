from __future__ import annotations

import json
import logging

from flask import Blueprint, Response, current_app, request, session, stream_with_context
from sqlalchemy import select

from ..agent.jobs import (
    AgentChatJobConflict,
    AgentChatJobNotFound,
    create_chat_job,
    get_chat_job,
    list_chat_jobs_for_conversation,
    serialize_job,
    submit_agent_chat_job,
)
from ..agent.analysis_session import load_analysis_session_state, save_analysis_session_state
from ..agent.memory import load_conversation_history, save_conversation_turn
from ..agent.services import AgentServiceError, generate_reply_payload
from ..db import session_scope
from ..logging_utils import bind_log_context, log_audit_event
from ..models import User
from .roles import ROLE_PRESETS


workspace_bp = Blueprint("workspace", __name__)
logger = logging.getLogger(__name__)


def _json_error(message: str, status_code: int):
    return {"ok": False, "error": message}, status_code


def _json_error_data(message: str, status_code: int, data: dict):
    return {"ok": False, "error": message, "data": data}, status_code


def _current_user_id() -> int | None:
    user_id = session.get("user_id")
    if isinstance(user_id, int):
        return user_id
    return None


def _extract_workspace(data: dict | None) -> dict:
    if not isinstance(data, dict):
        return {}
    workspace = data.get("workspace")
    if isinstance(workspace, dict):
        return workspace
    return {}


def _workspace_id(data: dict | None) -> str:
    workspace = _extract_workspace(data)
    workspace_id = workspace.get("id")
    if isinstance(workspace_id, str) and workspace_id.strip():
        return workspace_id.strip()
    return "default"


def _conversation_id(data: dict | None) -> str:
    if not isinstance(data, dict):
        return ""
    value = data.get("conversationId")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _selected_role(data: dict | None) -> str | None:
    role = _extract_workspace(data).get("role")
    if isinstance(role, str) and role in ROLE_PRESETS:
        return role
    return None


def _extract_analysis_request(data: dict | None) -> tuple[list[str], dict, dict]:
    if not isinstance(data, dict):
        return [], {}, {}
    enabled_modules = data.get("enabledAnalysisModules")
    shared_inputs = data.get("analysisSharedInputs")
    module_inputs = data.get("analysisModuleInputs")
    parsed_enabled = [
        str(item).strip()
        for item in enabled_modules
        if isinstance(item, str) and str(item).strip()
    ] if isinstance(enabled_modules, list) else []
    parsed_shared = dict(shared_inputs) if isinstance(shared_inputs, dict) else {}
    parsed_module_inputs = {
        str(module_id).strip(): dict(payload)
        for module_id, payload in module_inputs.items()
        if str(module_id).strip() and isinstance(payload, dict)
    } if isinstance(module_inputs, dict) else {}
    return parsed_enabled, parsed_shared, parsed_module_inputs


def _upsert_role_preferences(user: User, role: str) -> dict:
    current_preferences = user.preferences if isinstance(user.preferences, dict) else {}
    preferences = dict(current_preferences)
    workspace_raw = preferences.get("workspace")
    workspace = dict(workspace_raw) if isinstance(workspace_raw, dict) else {}
    if not isinstance(workspace.get("id"), str) or not str(workspace.get("id")).strip():
        workspace["id"] = f"user-{user.id}"
    workspace["role"] = role
    preferences["workspace"] = workspace
    user.preferences = preferences
    return preferences


def _workspace_payload(preferences: dict | None) -> dict:
    selected = _selected_role(preferences)
    workspace = _extract_workspace(preferences)
    workspace_id = workspace.get("id") if isinstance(workspace.get("id"), str) else "default"
    return {
        "workspaceId": workspace_id,
        "selectedRole": selected,
        "ragDebugVisualizationEnabled": bool(current_app.config.get("RAG_DEBUG_VISUALIZATION_ENABLED", False)),
        "agentTraceVisualizationEnabled": bool(current_app.config.get("AGENT_TRACE_VISUALIZATION_ENABLED", False)),
        "agentTraceDebugDetailsEnabled": bool(current_app.config.get("AGENT_TRACE_DEBUG_DETAILS_ENABLED", False)),
        "chatStreamingEnabled": bool(current_app.config.get("WORKSPACE_CHAT_STREAMING_ENABLED", True)),
        "agentChatJobsEnabled": bool(current_app.config.get("AGENT_CHAT_JOBS_ENABLED", True)),
        "roles": [
            {
                "key": key,
                "name": value["name"],
                "description": value["description"],
            }
            for key, value in ROLE_PRESETS.items()
        ],
        "systemPrompt": ROLE_PRESETS[selected]["systemPrompt"] if selected else "",
    }


def _chat_response_data(
    *,
    result: dict,
    role: str,
    system_prompt: str,
    trace_enabled: bool,
    debug_enabled: bool,
) -> dict:
    data = {
        "role": role,
        "systemPrompt": system_prompt,
        "reply": result["reply"],
        "citations": result["citations"],
        "sources": result.get("sources", []),
        "noEvidence": result["noEvidence"],
        "graph": result.get("graph", {}),
        "graphMeta": result.get("graphMeta", {}),
    }
    if isinstance(result.get("analysisResults"), dict):
        data["analysisResults"] = result.get("analysisResults", {})
    if isinstance(result.get("analysisHandoffBundle"), dict):
        data["analysisHandoffBundle"] = result.get("analysisHandoffBundle", {})
    if isinstance(result.get("analysisSession"), dict):
        data["analysisSession"] = result.get("analysisSession", {})
    if trace_enabled and isinstance(result.get("trace"), dict):
        data["trace"] = result["trace"]
    if debug_enabled:
        data["debug"] = result.get("debug", {})
    return data


def _job_response_data(job) -> dict:
    data = serialize_job(job, include_result=False)
    if isinstance(job.result_json, dict):
        result = dict(job.result_json)
        result.setdefault("role", job.role)
        result.setdefault("systemPrompt", ROLE_PRESETS.get(job.role, {}).get("systemPrompt", ""))
        data["result"] = result
    return data


def _stream_event(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _reply_chunks(reply: str, *, chunk_size: int = 48) -> list[str]:
    text = str(reply or "")
    if not text:
        return []
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]


@workspace_bp.get("/context")
def get_workspace_context():
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    with session_scope() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            return _json_error("user not found", 404)

        return {
            "ok": True,
            "data": _workspace_payload(user.preferences),
        }


@workspace_bp.patch("/context")
def patch_workspace_context():
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    payload = request.get_json(silent=True)
    role = payload.get("role") if isinstance(payload, dict) else None
    if role not in ROLE_PRESETS:
        return _json_error("role is invalid", 400)

    with session_scope() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            return _json_error("user not found", 404)

        preferences = _upsert_role_preferences(user, role)
        return {
            "ok": True,
            "data": _workspace_payload(preferences),
        }


@workspace_bp.post("/chat/jobs")
def create_workspace_chat_job():
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)
    if not bool(current_app.config.get("AGENT_CHAT_JOBS_ENABLED", True)):
        return _json_error("agent chat jobs are disabled", 404)

    payload = request.get_json(silent=True)
    message = payload.get("message", "") if isinstance(payload, dict) else ""
    message = str(message).strip()
    if not message:
        return _json_error("message is required", 400)
    conversation_id = _conversation_id(payload)
    if not conversation_id:
        return _json_error("conversationId is required", 400)

    request_workspace_id = ""
    entity = ""
    intent = ""
    enabled_analysis_modules: list[str] = []
    analysis_shared_inputs: dict = {}
    analysis_module_inputs: dict = {}
    if isinstance(payload, dict):
        raw_workspace_id = payload.get("workspaceId")
        if isinstance(raw_workspace_id, str):
            request_workspace_id = raw_workspace_id.strip()
        raw_entity = payload.get("entity")
        if isinstance(raw_entity, str):
            entity = raw_entity.strip()
        raw_intent = payload.get("intent")
        if isinstance(raw_intent, str):
            intent = raw_intent.strip()
        enabled_analysis_modules, analysis_shared_inputs, analysis_module_inputs = _extract_analysis_request(payload)

    app_obj = current_app._get_current_object()
    with session_scope() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            return _json_error("user not found", 404)

        role = _selected_role(user.preferences)
        if not role:
            return _json_error("please select a role first", 400)

        workspace_id = request_workspace_id or _workspace_id(user.preferences)
        bind_log_context(user_id=user_id, workspace_id=workspace_id)
        try:
            job = create_chat_job(
                db,
                user_id=user_id,
                workspace_id=workspace_id,
                role=role,
                conversation_id=conversation_id,
                message=message,
                entity=entity,
                intent=intent,
            )
        except AgentChatJobConflict as exc:
            bind_log_context(job_id=exc.active_job.id)
            log_audit_event(
                "workspace.chat.job.conflict",
                operation_status="conflict",
                resource_type="agent_chat_job",
                resource_id=str(exc.active_job.id),
                conversation_id=conversation_id,
                role=role,
            )
            return _json_error_data(
                "agent chat job already active for conversation",
                409,
                {"job": _job_response_data(exc.active_job)},
            )
        bind_log_context(job_id=job.id)
        log_audit_event(
            "workspace.chat.job.requested",
            operation_status="requested",
            resource_type="agent_chat_job",
            resource_id=str(job.id),
            conversation_id=conversation_id,
            role=role,
        )
        job_id = int(job.id)
        data = _job_response_data(job)

    submit_agent_chat_job(app_obj, job_id)
    return {"ok": True, "data": data}, 202


@workspace_bp.get("/chat/jobs")
def list_workspace_chat_jobs():
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)
    conversation_id = str(request.args.get("conversationId", "") or "").strip()
    if not conversation_id:
        return _json_error("conversationId is required", 400)
    workspace_id = str(request.args.get("workspaceId", "") or "").strip() or "default"

    with session_scope() as db:
        jobs = list_chat_jobs_for_conversation(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
        )
        return {"ok": True, "data": {"jobs": [_job_response_data(job) for job in jobs]}}


@workspace_bp.get("/chat/jobs/<int:job_id>")
def get_workspace_chat_job(job_id: int):
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)
    workspace_id = str(request.args.get("workspaceId", "") or "").strip() or None

    with session_scope() as db:
        try:
            job = get_chat_job(db, user_id=user_id, workspace_id=workspace_id, job_id=job_id)
        except AgentChatJobNotFound:
            return _json_error("agent chat job not found", 404)
        return {"ok": True, "data": _job_response_data(job)}


@workspace_bp.post("/chat")
def workspace_chat():
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    payload = request.get_json(silent=True)
    message = payload.get("message", "") if isinstance(payload, dict) else ""
    message = str(message).strip()
    if not message:
        return _json_error("message is required", 400)
    conversation_id = _conversation_id(payload)
    if not conversation_id:
        return _json_error("conversationId is required", 400)
    request_workspace_id = ""
    entity = ""
    intent = ""
    enabled_analysis_modules: list[str] = []
    analysis_shared_inputs: dict = {}
    analysis_module_inputs: dict = {}
    if isinstance(payload, dict):
        raw_workspace_id = payload.get("workspaceId")
        if isinstance(raw_workspace_id, str):
            request_workspace_id = raw_workspace_id.strip()
        raw_entity = payload.get("entity")
        if isinstance(raw_entity, str):
            entity = raw_entity.strip()
        raw_intent = payload.get("intent")
        if isinstance(raw_intent, str):
            intent = raw_intent.strip()
        enabled_analysis_modules, analysis_shared_inputs, analysis_module_inputs = _extract_analysis_request(payload)

    with session_scope() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            return _json_error("user not found", 404)

        role = _selected_role(user.preferences)
        if not role:
            return _json_error("please select a role first", 400)

        workspace_id = request_workspace_id or _workspace_id(user.preferences)
        bind_log_context(user_id=user_id, workspace_id=workspace_id)
        log_audit_event(
            "workspace.chat.requested",
            operation_status="requested",
            resource_type="workspace",
            resource_id=workspace_id,
            role=role,
        )
        preset = ROLE_PRESETS[role]
        debug_enabled = bool(
            current_app.config.get("RAG_DEBUG_VISUALIZATION_ENABLED", False)
            and current_app.config.get("RAG_ENABLED", False)
        )
        trace_enabled = bool(current_app.config.get("AGENT_TRACE_VISUALIZATION_ENABLED", False))
        trace_details_enabled = bool(current_app.config.get("AGENT_TRACE_DEBUG_DETAILS_ENABLED", False))
        thread, conversation_history, conversation_context = load_conversation_history(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
            conversation_id=conversation_id,
        )
        analysis_session_state = load_analysis_session_state(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
            conversation_id=conversation_id,
            enabled_modules=enabled_analysis_modules,
        )
        try:
            result = generate_reply_payload(
                role=role,
                system_prompt=preset["systemPrompt"],
                user_message=message,
                user_id=user_id,
                workspace_id=workspace_id,
                conversation_history=conversation_history,
                conversation_context=conversation_context,
                rag_debug_enabled=debug_enabled,
                entity=entity,
                intent=intent,
                enabled_analysis_modules=enabled_analysis_modules,
                analysis_shared_inputs=analysis_shared_inputs,
                analysis_module_inputs=analysis_module_inputs,
                analysis_session_state=analysis_session_state,
                agent_trace_enabled=trace_enabled,
                agent_trace_debug_details_enabled=trace_details_enabled,
            )
        except AgentServiceError:
            log_audit_event(
                "workspace.chat.failed",
                operation_status="failed",
                resource_type="workspace",
                resource_id=workspace_id,
                role=role,
            )
            logger.exception("Agent runtime failed for workspace chat")
            return _json_error("agent service unavailable", 502)

        log_audit_event(
            "workspace.chat.completed",
            operation_status="succeeded",
            resource_type="workspace",
            resource_id=workspace_id,
            role=role,
        )
        save_conversation_turn(
            db,
            thread=thread,
            user_message=message,
            assistant_result=result,
            intent=str(result.get("intent", intent)).strip(),
            conversation_context=conversation_context,
        )
        persisted_analysis_session = save_analysis_session_state(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
            conversation_id=conversation_id,
            payload=result.get("analysisSession"),
        )
        if persisted_analysis_session:
            result["analysisSession"] = persisted_analysis_session

        return {
            "ok": True,
            "data": _chat_response_data(
                result=result,
                role=role,
                system_prompt=preset["systemPrompt"],
                trace_enabled=trace_enabled,
                debug_enabled=debug_enabled,
            ),
        }


@workspace_bp.post("/chat/stream")
def workspace_chat_stream():
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    payload = request.get_json(silent=True)
    message = payload.get("message", "") if isinstance(payload, dict) else ""
    message = str(message).strip()
    if not message:
        return _json_error("message is required", 400)
    conversation_id = _conversation_id(payload)
    if not conversation_id:
        return _json_error("conversationId is required", 400)
    request_workspace_id = ""
    entity = ""
    intent = ""
    enabled_analysis_modules: list[str] = []
    analysis_shared_inputs: dict = {}
    analysis_module_inputs: dict = {}
    if isinstance(payload, dict):
        raw_workspace_id = payload.get("workspaceId")
        if isinstance(raw_workspace_id, str):
            request_workspace_id = raw_workspace_id.strip()
        raw_entity = payload.get("entity")
        if isinstance(raw_entity, str):
            entity = raw_entity.strip()
        raw_intent = payload.get("intent")
        if isinstance(raw_intent, str):
            intent = raw_intent.strip()
        enabled_analysis_modules, analysis_shared_inputs, analysis_module_inputs = _extract_analysis_request(payload)

    with session_scope() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            return _json_error("user not found", 404)

        role = _selected_role(user.preferences)
        if not role:
            return _json_error("please select a role first", 400)

        workspace_id = request_workspace_id or _workspace_id(user.preferences)

    preset = ROLE_PRESETS[role]
    debug_enabled = bool(
        current_app.config.get("RAG_DEBUG_VISUALIZATION_ENABLED", False)
        and current_app.config.get("RAG_ENABLED", False)
    )
    trace_enabled = bool(current_app.config.get("AGENT_TRACE_VISUALIZATION_ENABLED", False))
    trace_details_enabled = bool(current_app.config.get("AGENT_TRACE_DEBUG_DETAILS_ENABLED", False))

    @stream_with_context
    def generate():
        bind_log_context(user_id=user_id, workspace_id=workspace_id)
        log_audit_event(
            "workspace.chat.requested",
            operation_status="requested",
            resource_type="workspace",
            resource_id=workspace_id,
            role=role,
        )
        yield _stream_event({"type": "started", "role": role})
        try:
            with session_scope() as db:
                thread, conversation_history, conversation_context = load_conversation_history(
                    db,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    role=role,
                    conversation_id=conversation_id,
                )
                analysis_session_state = load_analysis_session_state(
                    db,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    role=role,
                    conversation_id=conversation_id,
                    enabled_modules=enabled_analysis_modules,
                )
                result = generate_reply_payload(
                    role=role,
                    system_prompt=preset["systemPrompt"],
                    user_message=message,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    conversation_history=conversation_history,
                    conversation_context=conversation_context,
                    rag_debug_enabled=debug_enabled,
                    entity=entity,
                    intent=intent,
                    enabled_analysis_modules=enabled_analysis_modules,
                    analysis_shared_inputs=analysis_shared_inputs,
                    analysis_module_inputs=analysis_module_inputs,
                    analysis_session_state=analysis_session_state,
                    agent_trace_enabled=trace_enabled,
                    agent_trace_debug_details_enabled=trace_details_enabled,
                )
                save_conversation_turn(
                    db,
                    thread=thread,
                    user_message=message,
                    assistant_result=result,
                    intent=str(result.get("intent", intent)).strip(),
                    conversation_context=conversation_context,
                )
                persisted_analysis_session = save_analysis_session_state(
                    db,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    role=role,
                    conversation_id=conversation_id,
                    payload=result.get("analysisSession"),
                )
                if persisted_analysis_session:
                    result["analysisSession"] = persisted_analysis_session
        except AgentServiceError:
            log_audit_event(
                "workspace.chat.failed",
                operation_status="failed",
                resource_type="workspace",
                resource_id=workspace_id,
                role=role,
            )
            logger.exception("Agent runtime failed for workspace chat stream")
            yield _stream_event({"type": "error", "error": "agent service unavailable"})
            return

        log_audit_event(
            "workspace.chat.completed",
            operation_status="succeeded",
            resource_type="workspace",
            resource_id=workspace_id,
            role=role,
        )
        for chunk in _reply_chunks(result.get("reply", "")):
            yield _stream_event({"type": "delta", "text": chunk})
        meta = _chat_response_data(
            result=result,
            role=role,
            system_prompt=preset["systemPrompt"],
            trace_enabled=trace_enabled,
            debug_enabled=debug_enabled,
        )
        meta.pop("reply", None)
        yield _stream_event({"type": "meta", **meta})
        yield _stream_event({"type": "done"})

    response = Response(generate(), mimetype="application/x-ndjson")
    response.headers["Cache-Control"] = "no-store"
    return response
