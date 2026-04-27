from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AnalysisReport
from .contracts import DEFAULT_RENDER_STYLE, as_dict, clean_text, drop_empty
from .publication import REPORT_DOWNLOAD_FORMAT

REPORT_PREVIEW_LIMIT = 600
_ASCII_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def bounded_report_preview(markdown_body: str, *, limit: int = REPORT_PREVIEW_LIMIT) -> str:
    clean = str(markdown_body or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip() + "…"


def report_download_metadata(report_id: str) -> dict[str, Any]:
    clean_report_id = clean_text(report_id)
    if not clean_report_id:
        return {"availableFormats": [REPORT_DOWNLOAD_FORMAT], "downloadUrls": {}}
    return {
        "availableFormats": [REPORT_DOWNLOAD_FORMAT],
        "downloadUrls": {
            REPORT_DOWNLOAD_FORMAT: f"/api/workspace/reports/{clean_report_id}/download?format={REPORT_DOWNLOAD_FORMAT}",
        },
    }


def report_preview_url(report_id: str) -> str:
    clean_report_id = clean_text(report_id)
    if not clean_report_id:
        return ""
    return f"/api/workspace/reports/{clean_report_id}/preview?format={REPORT_DOWNLOAD_FORMAT}"


def analysis_report_to_payload(row: AnalysisReport, *, include_body: bool = False) -> dict[str, Any]:
    artifact = as_dict(row.artifact_json)
    paginated_bundle = as_dict(artifact.get("paginatedReportBundle"))
    preview_excerpt = (
        clean_text(artifact.get("previewExcerpt"))
        or clean_text(artifact.get("preview"))
        or bounded_report_preview(row.markdown_body or "")
    )
    metadata = report_download_metadata(row.report_id)
    source_snapshot = as_dict(artifact.get("sourceSnapshot"))
    source_documents = source_snapshot.get("documents") if isinstance(source_snapshot.get("documents"), list) else []
    payload = drop_empty(
        {
            "reportId": row.report_id,
            "title": row.title,
            "status": row.status,
            "previewExcerpt": preview_excerpt,
            "preview": preview_excerpt,
            "availableFormats": metadata["availableFormats"],
            "downloadUrls": metadata["downloadUrls"],
            "previewUrl": report_preview_url(row.report_id),
            "renderStyle": clean_text(as_dict(artifact.get("renderProfile")).get("style")) or DEFAULT_RENDER_STYLE,
            "bundleSchemaVersion": clean_text(paginated_bundle.get("schemaVersion")),
            "renderProfile": as_dict(artifact.get("renderProfile") or paginated_bundle.get("renderProfile")),
            "exportManifest": as_dict(artifact.get("exportManifest") or paginated_bundle.get("exportManifest")),
            "pageCount": len(paginated_bundle.get("pages", [])) if isinstance(paginated_bundle.get("pages"), list) else 0,
            "sourceDocumentCount": len([item for item in source_documents if isinstance(item, dict)]),
            "limitations": (row.limitations_json or {}).get("items", []) if isinstance(row.limitations_json, dict) else [],
            "createdAt": row.created_at.isoformat() if row.created_at else "",
            "updatedAt": row.updated_at.isoformat() if row.updated_at else "",
        }
    )
    if include_body:
        payload["artifact"] = artifact
        payload["markdownBody"] = row.markdown_body or ""
        payload["htmlBody"] = row.html_body or ""
    return payload


def safe_report_filename(row: AnalysisReport, report_format: str) -> str:
    extension = clean_text(report_format).lower() or REPORT_DOWNLOAD_FORMAT
    base = _ascii_filename(row.title or row.report_id).rsplit(".", 1)[0]
    if not base:
        base = _ascii_filename(row.report_id) or "report"
    return f"{base}-{row.report_id}.{extension}"


def find_report_asset(row: AnalysisReport, asset_id: str) -> dict[str, Any] | None:
    target = clean_text(asset_id)
    if not target:
        return None
    artifact = as_dict(row.artifact_json)
    for collection_name in ("visualAssets", "attachments"):
        for item in _list_of_dicts(artifact.get(collection_name)):
            if clean_text(item.get("assetId") or item.get("id")) == target:
                return item
    return None


def inline_asset_response_payload(asset: dict[str, Any]) -> tuple[bytes, str, str] | None:
    content_type = clean_text(asset.get("contentType")) or "application/octet-stream"
    filename = clean_text(asset.get("filename") or asset.get("title") or asset.get("assetId") or "asset") or "asset"
    inline_content = clean_text(asset.get("inlineContent"))
    if inline_content:
        if content_type == "application/octet-stream":
            content_type = "text/plain; charset=utf-8"
        return inline_content.encode("utf-8"), content_type, filename
    render_payload = asset.get("renderPayload")
    if isinstance(render_payload, dict) and render_payload:
        return json.dumps(render_payload, ensure_ascii=False, indent=2).encode("utf-8"), "application/json", filename
    return None


def report_row_forbidden_values(row: AnalysisReport) -> list[str]:
    artifact = as_dict(row.artifact_json)
    values = set(_string_list((row.enabled_modules_json or {}).get("items", [])))
    values.update(clean_text(value) for value in as_dict(row.module_run_ids_json).values())
    values.add(clean_text(row.analysis_session_id))
    for item in _list_of_dicts(artifact.get("moduleSummaries")):
        values.add(clean_text(item.get("moduleId")))
        values.add(clean_text(item.get("runId")))
    internal_items = as_dict(as_dict(artifact.get("internalTraceIndex")).get("items"))
    for item in internal_items.values():
        if not isinstance(item, dict):
            continue
        values.add(clean_text(item.get("moduleId")))
        values.add(clean_text(item.get("runId")))
    return [value for value in values if len(value) >= 4]


def get_analysis_report(
    db: Session,
    *,
    user_id: int,
    report_id: str,
    workspace_id: str | None = None,
) -> AnalysisReport | None:
    clean_report_id = clean_text(report_id)
    if not clean_report_id:
        return None
    criteria = [AnalysisReport.user_id == user_id, AnalysisReport.report_id == clean_report_id]
    if workspace_id:
        criteria.append(AnalysisReport.workspace_id == workspace_id)
    return db.execute(select(AnalysisReport).where(*criteria)).scalar_one_or_none()


def save_analysis_report_artifact(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    role: str,
    conversation_id: str,
    artifact: dict[str, Any] | None,
) -> AnalysisReport | None:
    if not isinstance(artifact, dict) or not artifact:
        return None
    report_id = clean_text(artifact.get("reportId"))
    if not report_id:
        return None
    scope = as_dict(artifact.get("scope"))
    row = db.execute(select(AnalysisReport).where(AnalysisReport.report_id == report_id)).scalar_one_or_none()
    if row is None:
        from datetime import UTC, datetime

        now = datetime.now(UTC).replace(tzinfo=None)
        row = AnalysisReport(
            report_id=report_id,
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
            conversation_id=conversation_id,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    row.status = clean_text(artifact.get("status")) or "completed"
    row.title = clean_text(artifact.get("title")) or "分析报告"
    row.analysis_session_id = clean_text(scope.get("analysisSessionId")) or None
    row.analysis_session_revision = _safe_int(scope.get("analysisSessionRevision"), default=0)
    row.enabled_modules_json = {"items": _string_list(scope.get("enabledModules"))}
    row.module_run_ids_json = as_dict(scope.get("moduleRunIds"))
    row.artifact_json = {key: value for key, value in artifact.items() if key not in {"markdownBody", "htmlBody"}}
    row.markdown_body = clean_text(artifact.get("markdownBody"))
    row.html_body = clean_text(artifact.get("htmlBody"))
    row.visual_assets_json = {"items": _list_of_dicts(artifact.get("visualAssets"))}
    row.attachments_json = {"items": _list_of_dicts(artifact.get("attachments"))}
    row.limitations_json = {"items": artifact.get("limitations") if isinstance(artifact.get("limitations"), list) else []}
    row.download_metadata_json = report_download_metadata(report_id)
    from datetime import UTC, datetime

    row.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.flush()
    return row


def _ascii_filename(value: Any) -> str:
    text = str(value or "").encode("ascii", errors="ignore").decode("ascii").strip()
    text = _ASCII_FILENAME_PATTERN.sub("-", text).strip("._-")
    return text


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        clean = clean_text(item)
        if clean and clean not in result:
            result.append(clean)
    return result
