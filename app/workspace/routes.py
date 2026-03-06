from __future__ import annotations

from flask import Blueprint, request, session
from sqlalchemy import select

from ..db import session_scope
from ..models import User


workspace_bp = Blueprint("workspace", __name__)

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


def _selected_role(data: dict | None) -> str | None:
    role = _extract_workspace(data).get("role")
    if isinstance(role, str) and role in ROLE_PRESETS:
        return role
    return None


def _upsert_role_preferences(user: User, role: str) -> dict:
    preferences = user.preferences if isinstance(user.preferences, dict) else {}
    workspace = preferences.get("workspace") if isinstance(preferences.get("workspace"), dict) else {}
    workspace["role"] = role
    preferences["workspace"] = workspace
    user.preferences = preferences
    return preferences


def _workspace_payload(preferences: dict | None) -> dict:
    selected = _selected_role(preferences)
    return {
        "selectedRole": selected,
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

    with session_scope() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if not user:
            return _json_error("user not found", 404)

        role = _selected_role(user.preferences)
        if not role:
            return _json_error("please select a role first", 400)

        preset = ROLE_PRESETS[role]
        # Placeholder response path until external LLM integration is added.
        reply = (
            f"[{preset['name']}模式] 已收到你的问题：{message}。"
            "建议先明确目标、约束和可量化指标，我可以继续帮你拆成分步执行清单。"
        )

        return {
            "ok": True,
            "data": {
                "role": role,
                "systemPrompt": preset["systemPrompt"],
                "reply": reply,
            },
        }
