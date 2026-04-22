from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AnalysisSession


ANALYSIS_SESSION_STATUS_COLLECTING = "collecting"
ANALYSIS_SESSION_STATUS_READY = "ready"
ANALYSIS_SESSION_STATUS_RUNNING = "running"
ANALYSIS_SESSION_STATUS_COMPLETED = "completed"
ANALYSIS_SESSION_STATUS_FAILED = "failed"
ANALYSIS_SESSION_STATUS_STALE = "stale"


class AnalysisSessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_scope(
        self,
        *,
        user_id: int,
        workspace_id: str,
        role: str,
        conversation_id: str,
    ) -> AnalysisSession | None:
        stmt = select(AnalysisSession).where(
            AnalysisSession.user_id == user_id,
            AnalysisSession.workspace_id == workspace_id,
            AnalysisSession.role == role,
            AnalysisSession.conversation_id == conversation_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_or_create(
        self,
        *,
        user_id: int,
        workspace_id: str,
        role: str,
        conversation_id: str,
        enabled_modules: list[str] | None = None,
    ) -> AnalysisSession:
        row = self.get_by_scope(
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
            conversation_id=conversation_id,
        )
        if row is not None:
            return row

        now = datetime.utcnow()
        row = AnalysisSession(
            session_id=_new_session_id(),
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
            conversation_id=conversation_id,
            status=ANALYSIS_SESSION_STATUS_COLLECTING,
            revision=0,
            enabled_modules_json={"items": list(enabled_modules or [])},
            slot_values_json={},
            slot_states_json={},
            missing_slots_json={"items": []},
            question_plan_json={"groups": []},
            module_states_json={},
            module_results_json={},
            compatibility_json={"legacySharedInputs": {}, "legacyModuleInputs": {}},
            bundle_json={},
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def save_payload(self, row: AnalysisSession, payload: dict[str, Any]) -> AnalysisSession:
        now = datetime.utcnow()
        row.status = _clean_status(payload.get("status")) or ANALYSIS_SESSION_STATUS_COLLECTING
        row.revision = _clean_int(payload.get("revision"), default=0)
        row.enabled_modules_json = {"items": _string_list(payload.get("enabledModules"))}
        row.slot_values_json = _dict_value(payload.get("slotValues"))
        row.slot_states_json = _dict_value(payload.get("slotStates"))
        row.missing_slots_json = {"items": _string_list(payload.get("missingSlots"))}
        row.question_plan_json = {"groups": _list_of_dicts(payload.get("questionPlan"))}
        row.module_states_json = _dict_value(payload.get("moduleStates"))
        row.module_results_json = _dict_value(payload.get("moduleResults"))
        row.compatibility_json = _dict_value(payload.get("compatibility"))
        row.bundle_json = _dict_value(payload.get("handoffBundle"))
        row.updated_at = now
        self.db.flush()
        return row


def load_analysis_session_state(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    role: str,
    conversation_id: str,
    enabled_modules: list[str] | None = None,
) -> dict[str, Any] | None:
    repository = AnalysisSessionRepository(db)
    row = repository.get_by_scope(
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
        conversation_id=conversation_id,
    )
    if row is None and not list(enabled_modules or []):
        return None
    if row is None:
        row = repository.get_or_create(
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
            conversation_id=conversation_id,
            enabled_modules=list(enabled_modules or []),
        )
    return analysis_session_to_payload(row)


def save_analysis_session_state(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    role: str,
    conversation_id: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or not payload:
        return None
    repository = AnalysisSessionRepository(db)
    row = repository.get_or_create(
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
        conversation_id=conversation_id,
        enabled_modules=_string_list(payload.get("enabledModules")),
    )
    repository.save_payload(row, payload)
    return analysis_session_to_payload(row)


def create_transient_analysis_session(*, enabled_modules: list[str]) -> dict[str, Any]:
    return {
        "sessionId": "",
        "status": ANALYSIS_SESSION_STATUS_COLLECTING,
        "revision": 0,
        "enabledModules": list(enabled_modules),
        "slotValues": {},
        "slotStates": {},
        "missingSlots": [],
        "questionPlan": [],
        "moduleStates": {},
        "moduleResults": {},
        "compatibility": {"legacySharedInputs": {}, "legacyModuleInputs": {}},
        "handoffBundle": {},
    }


def analysis_session_to_payload(row: AnalysisSession) -> dict[str, Any]:
    return {
        "sessionId": row.session_id,
        "status": _clean_status(row.status) or ANALYSIS_SESSION_STATUS_COLLECTING,
        "revision": int(row.revision or 0),
        "enabledModules": _string_list((row.enabled_modules_json or {}).get("items", [])),
        "slotValues": _dict_value(row.slot_values_json),
        "slotStates": _dict_value(row.slot_states_json),
        "missingSlots": _string_list((row.missing_slots_json or {}).get("items", [])),
        "questionPlan": _list_of_dicts((row.question_plan_json or {}).get("groups", [])),
        "moduleStates": _dict_value(row.module_states_json),
        "moduleResults": _dict_value(row.module_results_json),
        "compatibility": _dict_value(row.compatibility_json),
        "handoffBundle": _dict_value(row.bundle_json),
        "createdAt": _format_datetime(row.created_at),
        "updatedAt": _format_datetime(row.updated_at),
    }


def _new_session_id() -> str:
    return f"asess_{uuid.uuid4().hex[:24]}"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.replace(microsecond=0).isoformat()


def _clean_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    allowed = {
        ANALYSIS_SESSION_STATUS_COLLECTING,
        ANALYSIS_SESSION_STATUS_READY,
        ANALYSIS_SESSION_STATUS_RUNNING,
        ANALYSIS_SESSION_STATUS_COMPLETED,
        ANALYSIS_SESSION_STATUS_FAILED,
        ANALYSIS_SESSION_STATUS_STALE,
    }
    return text if text in allowed else ""


def _clean_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError:
        return default


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        clean = str(item or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]
