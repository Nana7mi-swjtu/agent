from __future__ import annotations

import io
from pathlib import Path
from threading import Lock
from typing import Any

from flask import current_app
from werkzeug.datastructures import FileStorage

from ..db import session_scope
from .assets import (
    build_record_plot_url,
    cleanup_artifact,
    create_csv_asset,
    create_plot_asset,
    create_record_plot_asset,
    plots_root,
    resolve_plot_asset,
    uploads_root,
)
from .errors import (
    BankruptcyAuthorizationError,
    BankruptcyConfigurationError,
    BankruptcyNotFoundError,
    BankruptcyValidationError,
)
from .repository import create_record, get_record_for_scope, list_records_for_scope, set_record_status

_runtime_lock = Lock()
_runtime: dict[str, Any] | None = None

_CJK_FONT_CANDIDATES = (
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Arial Unicode MS",
    "PingFang SC",
    "Heiti SC",
)


def _project_root() -> Path:
    from pathlib import Path as _Path

    return _Path(current_app.root_path).parent


def _resolve_runtime_path(raw_path: str) -> Path:
    candidate = Path(str(raw_path).strip())
    if not candidate.is_absolute():
        candidate = _project_root() / candidate
    return candidate


def reset_runtime_for_tests() -> None:
    global _runtime
    with _runtime_lock:
        _runtime = None


def _configure_matplotlib_fonts(matplotlib: Any) -> None:
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    cjk_fonts = [name for name in _CJK_FONT_CANDIDATES if name in available]
    if cjk_fonts:
        matplotlib.rcParams["font.family"] = "sans-serif"
        matplotlib.rcParams["font.sans-serif"] = [*cjk_fonts, *matplotlib.rcParams.get("font.sans-serif", [])]
    matplotlib.rcParams["axes.unicode_minus"] = False


def _load_dependencies() -> dict[str, Any]:
    try:
        import joblib
        import matplotlib
        import numpy as np
        import pandas as pd
        import shap
    except ImportError as exc:
        raise BankruptcyConfigurationError(f"required package is missing: {exc}") from exc
    matplotlib.use("Agg")
    _configure_matplotlib_fonts(matplotlib)
    import matplotlib.pyplot as plt

    return {
        "joblib": joblib,
        "np": np,
        "pd": pd,
        "plt": plt,
        "shap": shap,
    }


def _build_runtime() -> dict[str, Any]:
    deps = _load_dependencies()
    model_path = _resolve_runtime_path(str(current_app.config.get("BANKRUPTCY_MODEL_PATH", "")))
    scaler_path = _resolve_runtime_path(str(current_app.config.get("BANKRUPTCY_SCALER_PATH", "")))
    if not model_path.exists():
        raise BankruptcyConfigurationError(f"model file not found: {model_path}")
    if not scaler_path.exists():
        raise BankruptcyConfigurationError(f"scaler file not found: {scaler_path}")

    model = deps["joblib"].load(model_path)
    scaler = deps["joblib"].load(scaler_path)
    feature_names = list(map(str, getattr(scaler, "feature_names_in_", [])))
    if not feature_names:
        raise BankruptcyConfigurationError("scaler is missing feature_names_in_ metadata")

    return {
        **deps,
        "model": model,
        "scaler": scaler,
        "feature_names": feature_names,
    }


def _get_runtime() -> dict[str, Any]:
    global _runtime
    if _runtime is not None:
        return _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = _build_runtime()
    return _runtime


def _describe_empty_csv(raw_bytes: bytes, *, feature_names: list[str]) -> str:
    text = raw_bytes.decode("utf-8-sig", errors="ignore")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "csv file is empty"

    first_row_values = [value.strip() for value in lines[0].split(",") if value.strip()]
    known_columns = set(feature_names) | {"Bankrupt?", "enterprise_name"}
    if first_row_values and all(value in known_columns for value in first_row_values):
        return "csv must include at least one data row below the header row"
    return "csv must include a header row with the required feature names and one data row"


def _read_upload_bytes(file_storage: FileStorage) -> tuple[bytes, str, str]:
    if file_storage is None or not str(getattr(file_storage, "filename", "")).strip():
        raise BankruptcyValidationError("file is required")
    file_name = str(file_storage.filename).strip()
    try:
        file_storage.stream.seek(0)
        raw_bytes = file_storage.stream.read()
        if isinstance(raw_bytes, str):
            raw_bytes = raw_bytes.encode("utf-8")
    except Exception as exc:
        raise BankruptcyValidationError(f"failed to read csv file: {exc}") from exc
    if not raw_bytes or not raw_bytes.strip():
        raise BankruptcyValidationError("csv file is empty")
    mime_type = str(getattr(file_storage, "mimetype", "") or "text/csv")
    return raw_bytes, file_name, mime_type


def _read_stored_bytes(path_str: str) -> bytes:
    path = Path(str(path_str or "").strip())
    if not path.exists():
        raise BankruptcyValidationError("saved csv file is unavailable")
    raw_bytes = path.read_bytes()
    if not raw_bytes or not raw_bytes.strip():
        raise BankruptcyValidationError("saved csv file is empty")
    return raw_bytes


def _load_frame_from_bytes(raw_bytes: bytes, *, pd: Any, feature_names: list[str]):
    try:
        frame = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise BankruptcyValidationError(f"failed to parse csv file: {exc}") from exc
    if frame.empty:
        raise BankruptcyValidationError(_describe_empty_csv(raw_bytes, feature_names=feature_names))
    if len(frame.index) != 1:
        raise BankruptcyValidationError("only single-sample csv files are supported")
    return frame


def _normalize_display_name(raw_name: str, *, fallback_name: str = "") -> str:
    value = str(raw_name or "").strip()
    if value:
        return value
    fallback = str(fallback_name or "").strip()
    return fallback or "Unknown company"


def _apply_enterprise_metadata(frame: Any, enterprise_name: str, *, fallback_name: str = ""):
    display_name = ""
    if "enterprise_name" in frame.columns:
        display_name = str(frame.iloc[0].get("enterprise_name", "")).strip()
    if not display_name and enterprise_name:
        display_name = enterprise_name
        frame = frame.copy()
        frame["enterprise_name"] = enterprise_name
    return _normalize_display_name(display_name, fallback_name=fallback_name), frame


def _prepare_feature_frame(frame: Any, *, feature_names: list[str], pd: Any):
    features = frame.drop(columns=["Bankrupt?", "enterprise_name"], errors="ignore").copy()
    missing = [column for column in feature_names if column not in features.columns]
    if missing:
        raise BankruptcyValidationError(f"missing required feature columns: {', '.join(missing)}")
    features = features.loc[:, feature_names]
    for column in feature_names:
        try:
            features[column] = pd.to_numeric(features[column], errors="raise")
        except Exception as exc:
            raise BankruptcyValidationError(f"feature '{column}' must be numeric") from exc
    return features.iloc[[0]]


def _extract_top_features(*, shap_values: Any, feature_names: list[str], np: Any, top_count: int) -> list[dict[str, Any]]:
    values = shap_values
    if isinstance(values, list):
        values = values[-1]
    matrix = np.asarray(values)
    if matrix.ndim == 1:
        sample_values = matrix
    elif matrix.ndim >= 2:
        sample_values = matrix[0]
    else:
        raise BankruptcyConfigurationError("unexpected shap output shape")

    ranked = [
        {
            "name": feature_name,
            "shapValue": float(sample_values[idx]),
            "direction": "increase_risk" if float(sample_values[idx]) > 0 else "decrease_risk",
            "absoluteValue": abs(float(sample_values[idx])),
        }
        for idx, feature_name in enumerate(feature_names)
    ]
    ranked.sort(key=lambda item: item["absoluteValue"], reverse=True)
    return ranked[: max(1, int(top_count))]


def _render_plot(
    *,
    plot_path: Path,
    top_features: list[dict[str, Any]],
    company_name: str,
    plt: Any,
) -> None:
    labels = [item["name"] for item in reversed(top_features)]
    values = [item["shapValue"] for item in reversed(top_features)]
    colors = ["#d62728" if value > 0 else "#1f77b4" for value in values]

    plt.figure(figsize=(8, 5))
    plt.barh(labels, values, color=colors)
    plt.axvline(0, color="black", linewidth=1)
    plt.xlabel("SHAP value (impact on bankruptcy risk)")
    plt.title(f"SHAP Contributions - {company_name}")
    plt.tight_layout()
    plt.savefig(plot_path, dpi=300, bbox_inches="tight")
    plt.close()


def _analyze_frame(
    *,
    frame: Any,
    company_name: str,
    feature_names: list[str],
    runtime: dict[str, Any],
    plot_path: Path,
) -> dict[str, Any]:
    pd = runtime["pd"]
    np = runtime["np"]
    plt = runtime["plt"]
    shap = runtime["shap"]

    features = _prepare_feature_frame(frame, feature_names=feature_names, pd=pd)
    scaler = runtime["scaler"]
    model = runtime["model"]
    scaled = scaler.transform(features)
    scaled_frame = pd.DataFrame(scaled, columns=feature_names)

    probability = float(model.predict_proba(scaled_frame)[0, 1])
    threshold = float(current_app.config.get("BANKRUPTCY_THRESHOLD", 0.63))
    risk_level = "high" if probability > threshold else "low"

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(scaled_frame)
    top_count = int(current_app.config.get("BANKRUPTCY_TOP_FEATURE_COUNT", 10))
    top_features = _extract_top_features(
        shap_values=shap_values,
        feature_names=feature_names,
        np=np,
        top_count=top_count,
    )
    _render_plot(plot_path=plot_path, top_features=top_features, company_name=company_name, plt=plt)

    return {
        "companyName": company_name,
        "probability": probability,
        "threshold": threshold,
        "riskLevel": risk_level,
        "topFeatures": top_features,
        "inputSummary": {
            "rowCount": int(len(frame.index)),
            "featureCount": int(len(feature_names)),
        },
    }


def _summarize_result(record, *, plot_url: str = "") -> dict[str, Any]:
    result_json = record.result_json if isinstance(record.result_json, dict) else {}
    top_features = result_json.get("topFeatures", []) if isinstance(result_json.get("topFeatures"), list) else []
    input_summary = result_json.get("inputSummary", {}) if isinstance(result_json.get("inputSummary"), dict) else {}
    company_name = str(result_json.get("companyName") or record.source_name or record.file_name or "Unknown company")
    return {
        "id": int(record.id),
        "workspaceId": record.workspace_id,
        "companyName": company_name,
        "sourceName": record.source_name,
        "fileName": record.file_name,
        "fileExtension": record.file_extension,
        "status": record.status,
        "enterpriseName": record.enterprise_name or "",
        "errorMessage": record.error_message,
        "probability": float(record.probability) if record.probability is not None else None,
        "threshold": float(record.threshold) if record.threshold is not None else None,
        "riskLevel": record.risk_level if isinstance(record.risk_level, str) else "",
        "topFeatures": top_features,
        "plotUrl": plot_url,
        "inputSummary": {
            "rowCount": int(input_summary.get("rowCount", 0) or 0),
            "featureCount": int(input_summary.get("featureCount", 0) or 0),
        },
        "createdAt": record.created_at.isoformat(),
        "updatedAt": record.updated_at.isoformat(),
        "analyzedAt": record.analyzed_at.isoformat() if record.analyzed_at else None,
    }


def _record_list_payload(record) -> dict[str, Any]:
    detail = _summarize_result(record)
    return {
        "id": detail["id"],
        "workspaceId": detail["workspaceId"],
        "companyName": detail["companyName"],
        "sourceName": detail["sourceName"],
        "fileName": detail["fileName"],
        "status": detail["status"],
        "probability": detail["probability"],
        "riskLevel": detail["riskLevel"],
        "createdAt": detail["createdAt"],
        "updatedAt": detail["updatedAt"],
        "analyzedAt": detail["analyzedAt"],
    }


def _record_detail_payload(record) -> dict[str, Any]:
    plot_url = ""
    if record.status == "analyzed" and record.plot_path:
        plot_url = build_record_plot_url(record_id=record.id, workspace_id=record.workspace_id)
    return _summarize_result(record, plot_url=plot_url)


def save_bankruptcy_record(
    *,
    user_id: int,
    workspace_id: str,
    file_storage: FileStorage,
    enterprise_name: str = "",
) -> dict[str, Any]:
    runtime = _get_runtime()
    feature_names = list(runtime["feature_names"])
    pd = runtime["pd"]

    raw_bytes, original_name, mime_type = _read_upload_bytes(file_storage)
    frame = _load_frame_from_bytes(raw_bytes, pd=pd, feature_names=feature_names)
    fallback_name = Path(original_name).stem
    company_name, normalized_frame = _apply_enterprise_metadata(
        frame,
        str(enterprise_name or "").strip(),
        fallback_name=fallback_name,
    )
    _prepare_feature_frame(normalized_frame, feature_names=feature_names, pd=pd)

    storage_path = create_csv_asset(user_id=user_id, workspace_id=workspace_id, original_name=original_name)
    storage_path.write_bytes(raw_bytes)
    extension = storage_path.suffix.lstrip(".").lower() or "csv"

    with session_scope() as db:
        record = create_record(
            db=db,
            user_id=user_id,
            workspace_id=workspace_id,
            source_name=company_name,
            file_name=original_name,
            file_extension=extension,
            mime_type=mime_type,
            storage_path=str(storage_path),
            enterprise_name=company_name,
        )
        return _record_detail_payload(record)


def list_bankruptcy_records(*, user_id: int, workspace_id: str) -> list[dict[str, Any]]:
    with session_scope() as db:
        records = list_records_for_scope(db=db, user_id=user_id, workspace_id=workspace_id)
        return [_record_list_payload(record) for record in records]


def get_bankruptcy_record_detail(*, user_id: int, workspace_id: str, record_id: int) -> dict[str, Any]:
    with session_scope() as db:
        record = get_record_for_scope(db=db, record_id=record_id, user_id=user_id, workspace_id=workspace_id)
        return _record_detail_payload(record)


def analyze_bankruptcy_record(*, user_id: int, workspace_id: str, record_id: int) -> dict[str, Any]:
    runtime = _get_runtime()
    feature_names = list(runtime["feature_names"])
    pd = runtime["pd"]
    old_plot_path = ""
    new_plot_path = ""

    with session_scope() as db:
        record = get_record_for_scope(db=db, record_id=record_id, user_id=user_id, workspace_id=workspace_id)
        old_plot_path = str(record.plot_path or "")
        try:
            raw_bytes = _read_stored_bytes(record.storage_path)
            frame = _load_frame_from_bytes(raw_bytes, pd=pd, feature_names=feature_names)
            company_name, normalized_frame = _apply_enterprise_metadata(
                frame,
                str(record.enterprise_name or record.source_name or "").strip(),
                fallback_name=Path(record.file_name).stem,
            )
            plot_path = create_record_plot_asset(user_id=user_id, workspace_id=workspace_id, record_id=record.id)
            result = _analyze_frame(
                frame=normalized_frame,
                company_name=company_name,
                feature_names=feature_names,
                runtime=runtime,
                plot_path=plot_path,
            )
            new_plot_path = str(plot_path)
            set_record_status(
                record=record,
                status="analyzed",
                error_message=None,
                probability=result["probability"],
                threshold=result["threshold"],
                risk_level=result["riskLevel"],
                result_json=result,
                plot_path=str(plot_path),
            )
        except Exception as exc:
            error_message = str(exc) if isinstance(exc, (BankruptcyValidationError, BankruptcyConfigurationError)) else "bankruptcy analysis failed"
            set_record_status(
                record=record,
                status="failed",
                error_message=error_message,
            )
            if old_plot_path:
                cleanup_artifact(old_plot_path, expected_root=plots_root())
            raise
        detail = _record_detail_payload(record)

    if old_plot_path and new_plot_path and old_plot_path != new_plot_path:
        cleanup_artifact(old_plot_path, expected_root=plots_root())
    return detail


def delete_bankruptcy_record(*, user_id: int, workspace_id: str, record_id: int) -> dict[str, Any]:
    storage_path = ""
    plot_path = ""
    with session_scope() as db:
        record = get_record_for_scope(db=db, record_id=record_id, user_id=user_id, workspace_id=workspace_id)
        storage_path = str(record.storage_path or "")
        plot_path = str(record.plot_path or "")
        set_record_status(record=record, status="deleted", error_message=None)
        payload = {"id": int(record.id), "workspaceId": record.workspace_id, "status": "deleted"}

    cleanup_artifact(storage_path, expected_root=uploads_root())
    cleanup_artifact(plot_path, expected_root=plots_root())
    return payload


def read_bankruptcy_record_plot(*, user_id: int, workspace_id: str, record_id: int) -> Path:
    with session_scope() as db:
        record = get_record_for_scope(db=db, record_id=record_id, user_id=user_id, workspace_id=workspace_id)
        if record.status != "analyzed" or not record.plot_path:
            raise BankruptcyNotFoundError("bankruptcy plot not found")
        plot_path = Path(record.plot_path)
        if not plot_path.exists():
            raise BankruptcyNotFoundError("bankruptcy plot not found")
        return plot_path


def analyze_bankruptcy_csv(
    *,
    user_id: int,
    workspace_id: str,
    file_storage: FileStorage,
    enterprise_name: str = "",
) -> dict[str, Any]:
    runtime = _get_runtime()
    feature_names = list(runtime["feature_names"])
    pd = runtime["pd"]

    raw_bytes, original_name, _mime_type = _read_upload_bytes(file_storage)
    frame = _load_frame_from_bytes(raw_bytes, pd=pd, feature_names=feature_names)
    company_name, normalized_frame = _apply_enterprise_metadata(
        frame,
        str(enterprise_name or "").strip(),
        fallback_name=Path(original_name).stem,
    )
    plot_path, plot_url = create_plot_asset(user_id=user_id, workspace_id=workspace_id)
    result = _analyze_frame(
        frame=normalized_frame,
        company_name=company_name,
        feature_names=feature_names,
        runtime=runtime,
        plot_path=plot_path,
    )
    result["plotUrl"] = plot_url
    return result


def read_plot_asset(*, user_id: int, workspace_id: str, filename: str, token: str) -> Path:
    path = resolve_plot_asset(
        user_id=user_id,
        workspace_id=workspace_id,
        filename=filename,
        token=token,
    )
    if not path.exists():
        raise BankruptcyAuthorizationError("plot not found")
    return path
