from __future__ import annotations

import logging

from flask import Blueprint, current_app, request, send_file, session

from ..logging_utils import bind_log_context, log_audit_event
from .errors import (
    BankruptcyAuthorizationError,
    BankruptcyConfigurationError,
    BankruptcyNotFoundError,
    BankruptcyValidationError,
)
from .service import (
    analyze_bankruptcy_csv,
    analyze_bankruptcy_record,
    delete_bankruptcy_record,
    get_bankruptcy_record_detail,
    list_bankruptcy_records,
    read_bankruptcy_record_plot,
    read_plot_asset,
    save_bankruptcy_record,
)

bankruptcy_bp = Blueprint("bankruptcy", __name__)
logger = logging.getLogger(__name__)


def _json_error(message: str, status_code: int):
    return {"ok": False, "error": message}, status_code


def _current_user_id() -> int | None:
    user_id = session.get("user_id")
    if isinstance(user_id, int):
        return user_id
    return None


def _ensure_enabled():
    if not bool(current_app.config.get("BANKRUPTCY_ANALYSIS_ENABLED", False)):
        return _json_error("bankruptcy analysis is disabled", 404)
    return None


@bankruptcy_bp.post("/predict")
def predict():
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    workspace_id = str(request.form.get("workspaceId", "default")).strip() or "default"
    bind_log_context(user_id=user_id, workspace_id=workspace_id)
    enterprise_name = str(request.form.get("enterpriseName", "")).strip()
    file_storage = request.files.get("file")

    try:
        data = analyze_bankruptcy_csv(
            user_id=user_id,
            workspace_id=workspace_id,
            file_storage=file_storage,
            enterprise_name=enterprise_name,
        )
    except BankruptcyValidationError as exc:
        return _json_error(str(exc), 400)
    except BankruptcyConfigurationError as exc:
        log_audit_event(
            "bankruptcy.predict.failed",
            operation_status="failed",
            resource_type="workspace",
            resource_id=workspace_id,
        )
        logger.exception("Bankruptcy runtime is unavailable")
        return _json_error(str(exc), 503)
    except Exception:
        log_audit_event(
            "bankruptcy.predict.failed",
            operation_status="failed",
            resource_type="workspace",
            resource_id=workspace_id,
        )
        logger.exception("Bankruptcy analysis failed")
        return _json_error("bankruptcy analysis failed", 500)

    log_audit_event(
        "bankruptcy.predict.completed",
        operation_status="succeeded",
        resource_type="workspace",
        resource_id=workspace_id,
    )
    return {"ok": True, "data": data}


@bankruptcy_bp.route("/records", methods=["GET", "POST"])
def records():
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    if request.method == "GET":
        workspace_id = str(request.args.get("workspaceId", "default")).strip() or "default"
        bind_log_context(user_id=user_id, workspace_id=workspace_id)
        try:
            records = list_bankruptcy_records(user_id=user_id, workspace_id=workspace_id)
        except BankruptcyValidationError as exc:
            return _json_error(str(exc), 400)
        return {"ok": True, "data": {"records": records}}

    workspace_id = str(request.form.get("workspaceId", "default")).strip() or "default"
    bind_log_context(user_id=user_id, workspace_id=workspace_id)
    enterprise_name = str(request.form.get("enterpriseName", "")).strip()
    file_storage = request.files.get("file")
    try:
        data = save_bankruptcy_record(
            user_id=user_id,
            workspace_id=workspace_id,
            file_storage=file_storage,
            enterprise_name=enterprise_name,
        )
    except BankruptcyValidationError as exc:
        return _json_error(str(exc), 400)
    except BankruptcyConfigurationError as exc:
        log_audit_event(
            "bankruptcy.record.save_failed",
            operation_status="failed",
            resource_type="workspace",
            resource_id=workspace_id,
        )
        logger.exception("Bankruptcy runtime is unavailable")
        return _json_error(str(exc), 503)
    except Exception:
        log_audit_event(
            "bankruptcy.record.save_failed",
            operation_status="failed",
            resource_type="workspace",
            resource_id=workspace_id,
        )
        logger.exception("Failed to save bankruptcy record")
        return _json_error("failed to save bankruptcy record", 500)
    log_audit_event(
        "bankruptcy.record.saved",
        operation_status="succeeded",
        resource_type="record",
        resource_id=data.get("id"),
    )
    return {"ok": True, "data": data}


@bankruptcy_bp.get("/records/<int:record_id>")
def read_record(record_id: int):
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    workspace_id = str(request.args.get("workspaceId", "default")).strip() or "default"
    bind_log_context(user_id=user_id, workspace_id=workspace_id, record_id=record_id)
    try:
        data = get_bankruptcy_record_detail(user_id=user_id, workspace_id=workspace_id, record_id=record_id)
    except BankruptcyAuthorizationError as exc:
        return _json_error(str(exc), 403)
    except BankruptcyNotFoundError as exc:
        return _json_error(str(exc), 404)
    except BankruptcyValidationError as exc:
        return _json_error(str(exc), 400)
    return {"ok": True, "data": data}


@bankruptcy_bp.post("/records/<int:record_id>/analyze")
def analyze_record(record_id: int):
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    workspace_id = str(request.form.get("workspaceId", "")).strip() or str(request.args.get("workspaceId", "default")).strip() or "default"
    bind_log_context(user_id=user_id, workspace_id=workspace_id, record_id=record_id)
    try:
        data = analyze_bankruptcy_record(user_id=user_id, workspace_id=workspace_id, record_id=record_id)
    except BankruptcyAuthorizationError as exc:
        return _json_error(str(exc), 403)
    except BankruptcyNotFoundError as exc:
        return _json_error(str(exc), 404)
    except BankruptcyValidationError as exc:
        return _json_error(str(exc), 400)
    except BankruptcyConfigurationError as exc:
        log_audit_event(
            "bankruptcy.record.analyze_failed",
            operation_status="failed",
            resource_type="record",
            resource_id=record_id,
        )
        logger.exception("Bankruptcy runtime is unavailable")
        return _json_error(str(exc), 503)
    except Exception:
        log_audit_event(
            "bankruptcy.record.analyze_failed",
            operation_status="failed",
            resource_type="record",
            resource_id=record_id,
        )
        logger.exception("Bankruptcy analysis failed for saved record")
        return _json_error("bankruptcy analysis failed", 500)
    log_audit_event(
        "bankruptcy.record.analyzed",
        operation_status="succeeded",
        resource_type="record",
        resource_id=record_id,
    )
    return {"ok": True, "data": data}


@bankruptcy_bp.delete("/records/<int:record_id>")
def delete_record(record_id: int):
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    workspace_id = str(request.args.get("workspaceId", "default")).strip() or "default"
    bind_log_context(user_id=user_id, workspace_id=workspace_id, record_id=record_id)
    try:
        data = delete_bankruptcy_record(user_id=user_id, workspace_id=workspace_id, record_id=record_id)
    except BankruptcyAuthorizationError as exc:
        return _json_error(str(exc), 403)
    except BankruptcyNotFoundError as exc:
        return _json_error(str(exc), 404)
    except BankruptcyValidationError as exc:
        return _json_error(str(exc), 400)
    log_audit_event(
        "bankruptcy.record.deleted",
        operation_status="succeeded",
        resource_type="record",
        resource_id=record_id,
    )
    return {"ok": True, "data": data}


@bankruptcy_bp.get("/records/<int:record_id>/plot")
def read_record_plot(record_id: int):
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    workspace_id = str(request.args.get("workspaceId", "default")).strip() or "default"
    bind_log_context(user_id=user_id, workspace_id=workspace_id, record_id=record_id)
    try:
        plot_path = read_bankruptcy_record_plot(user_id=user_id, workspace_id=workspace_id, record_id=record_id)
    except BankruptcyAuthorizationError as exc:
        return _json_error(str(exc), 403)
    except BankruptcyNotFoundError as exc:
        return _json_error(str(exc), 404)
    except BankruptcyValidationError as exc:
        return _json_error(str(exc), 400)
    except Exception:
        logger.exception("Failed to read bankruptcy record plot")
        return _json_error("failed to read plot", 500)
    return send_file(plot_path, mimetype="image/png")


@bankruptcy_bp.get("/plots/<path:filename>")
def read_plot(filename: str):
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    workspace_id = str(request.args.get("workspaceId", "default")).strip() or "default"
    bind_log_context(user_id=user_id, workspace_id=workspace_id)
    token = str(request.args.get("token", "")).strip()

    try:
        plot_path = read_plot_asset(
            user_id=user_id,
            workspace_id=workspace_id,
            filename=filename,
            token=token,
        )
    except BankruptcyValidationError as exc:
        return _json_error(str(exc), 400)
    except BankruptcyAuthorizationError as exc:
        return _json_error(str(exc), 403)
    except Exception:
        logger.exception("Failed to read bankruptcy plot")
        return _json_error("failed to read plot", 500)

    return send_file(plot_path, mimetype="image/png")
