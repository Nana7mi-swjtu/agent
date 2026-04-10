from __future__ import annotations

import logging

from flask import Blueprint, current_app, request, session
from sqlalchemy import select

from ..agent.services import AgentServiceError, generate_reply_payload
from ..db import session_scope
from ..logging_utils import bind_log_context, log_audit_event
from ..models import User


workspace_bp = Blueprint("workspace", __name__)
logger = logging.getLogger(__name__)

ROLE_PRESETS = {
    "investor": {
        "name": "投资者",
        "description": "关注风险收益、现金流与估值逻辑。",
        "systemPrompt": (
            "你是投资者决策助手。你的目标是帮助用户评估项目的收益、风险、退出机制与资金效率，"
            "并给出可执行的尽调清单与投资建议。"
        ),
    },
    "enterprise_manager": {
        "name": "企业管理者",
        "description": "关注经营效率、组织协同与战略落地。",
        "systemPrompt": (
            "你是企业经营助手。你的目标是从战略、组织、财务和流程四个层面给出可执行建议，"
            "并优先输出短周期可验证的行动项。"
        ),
    },
    "regulator": {
        "name": "监管机构",
        "description": "关注合规风险、审计透明度与政策对齐。",
        "systemPrompt": (
            "你是监管分析助手。你的目标是识别潜在合规风险、披露缺口与流程漏洞，"
            "并给出符合监管口径的整改建议与跟踪机制。"
        ),
    },
}


def _json_error(message: str, status_code: int):
    return {"ok": False, "error": message}, status_code


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


def _selected_role(data: dict | None) -> str | None:
    role = _extract_workspace(data).get("role")
    if isinstance(role, str) and role in ROLE_PRESETS:
        return role
    return None


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
    request_workspace_id = ""
    if isinstance(payload, dict):
        raw_workspace_id = payload.get("workspaceId")
        if isinstance(raw_workspace_id, str):
            request_workspace_id = raw_workspace_id.strip()

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
        try:
            result = generate_reply_payload(
                role=role,
                system_prompt=preset["systemPrompt"],
                user_message=message,
                user_id=user_id,
                workspace_id=workspace_id,
                rag_debug_enabled=debug_enabled,
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
        return {
            "ok": True,
            "data": {
                "role": role,
                "systemPrompt": preset["systemPrompt"],
                "reply": result["reply"],
                "citations": result["citations"],
                "noEvidence": result["noEvidence"],
                **({"trace": result.get("trace", {})} if trace_enabled and isinstance(result.get("trace"), dict) else {}),
                **({"debug": result.get("debug", {})} if debug_enabled else {}),
            },
        }
