from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AnalysisReport
from .agent import generate_report_artifact_from_source_documents
from .contracts import DEFAULT_RENDER_STYLE, as_dict, clean_text, drop_empty
from .legacy_reporting import (
    REPORT_DOWNLOAD_FORMAT,
    SUPPORTED_REPORT_DOWNLOAD_FORMATS,
    PublishedReportValidationError,
    find_report_asset as _find_report_asset,
    get_analysis_report as _get_analysis_report,
    inline_asset_response_payload as _inline_asset_response_payload,
    render_report_pdf,
    report_row_forbidden_values as _report_row_forbidden_values,
    safe_report_filename as _safe_report_filename,
    save_analysis_report_artifact as _save_analysis_report_artifact,
)

DEFAULT_REPORT_RENDER_STYLE = DEFAULT_RENDER_STYLE
REPORT_REQUEST_GENERATE = "generate"
REPORT_REQUEST_REGENERATE = "regenerate"
REPORT_PREVIEW_LIMIT = 600


class ReportRequestError(RuntimeError):
    pass


class ReportActionError(ReportRequestError):
    pass


def _clean_source_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\x00", "").strip()


def _report_download_metadata(report_id: str) -> dict[str, Any]:
    clean_report_id = clean_text(report_id)
    if not clean_report_id:
        return {"availableFormats": [REPORT_DOWNLOAD_FORMAT], "downloadUrls": {}}
    return {
        "availableFormats": [REPORT_DOWNLOAD_FORMAT],
        "downloadUrls": {
            REPORT_DOWNLOAD_FORMAT: f"/api/workspace/reports/{clean_report_id}/download?format={REPORT_DOWNLOAD_FORMAT}",
        },
    }


def _report_preview_url(report_id: str) -> str:
    clean_report_id = clean_text(report_id)
    if not clean_report_id:
        return ""
    return f"/api/workspace/reports/{clean_report_id}/preview?format={REPORT_DOWNLOAD_FORMAT}"


def _bounded_report_preview(markdown_body: str, *, limit: int = REPORT_PREVIEW_LIMIT) -> str:
    clean = str(markdown_body or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip() + "…"


def _normalize_report_documents(value: Any) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    if not isinstance(value, dict):
        return documents

    source_text = _clean_source_text(value.get("sourceText"))
    if source_text:
        documents.append(
            {
                "sourceId": "source_1",
                "title": "",
                "contentType": "auto",
                "content": source_text,
            }
        )

    raw_documents = value.get("documents")
    if isinstance(raw_documents, list):
        for index, item in enumerate(raw_documents, start=len(documents) + 1):
            if isinstance(item, str):
                content = _clean_source_text(item)
                if not content:
                    continue
                documents.append(
                    {
                        "sourceId": f"source_{index}",
                        "title": "",
                        "contentType": "auto",
                        "content": content,
                    }
                )
                continue
            if not isinstance(item, dict):
                continue
            content = _clean_source_text(item.get("content") or item.get("sourceText") or item.get("text"))
            if not content:
                continue
            documents.append(
                {
                    "sourceId": clean_text(item.get("sourceId")) or f"source_{index}",
                    "title": clean_text(item.get("title"), limit=160),
                    "contentType": clean_text(item.get("contentType")) or "auto",
                    "content": content,
                    "metadata": dict(item.get("metadata")) if isinstance(item.get("metadata"), dict) else {},
                }
            )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for document in documents:
        key = (str(document.get("sourceId") or ""), str(document.get("content") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(document)
    return deduped


def normalize_report_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    documents = _normalize_report_documents(value)
    if documents:
        return {
            "mode": REPORT_REQUEST_GENERATE,
            "documents": documents,
        }
    report_id = clean_text(value.get("reportId"))
    if report_id:
        return {
            "mode": REPORT_REQUEST_REGENERATE,
            "reportId": report_id,
        }
    return {}


def has_report_request(value: Any) -> bool:
    return bool(normalize_report_request(value))


def _source_documents_from_artifact(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = as_dict(artifact.get("sourceSnapshot"))
    documents = snapshot.get("documents")
    if not isinstance(documents, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(documents, start=1):
        if not isinstance(item, dict):
            continue
        content = _clean_source_text(item.get("content"))
        if not content:
            continue
        normalized.append(
            {
                "sourceId": clean_text(item.get("sourceId")) or f"source_{index}",
                "title": clean_text(item.get("title"), limit=160),
                "contentType": clean_text(item.get("contentType")) or "auto",
                "content": content,
            }
        )
    return normalized


def execute_report_request(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    request: dict[str, Any],
    report_writer: Any | None = None,
) -> dict[str, Any]:
    del report_writer
    normalized = normalize_report_request(request)
    if not normalized:
        raise ReportRequestError("report request is invalid")
    delete_legacy_report_rows(db, user_id=user_id, workspace_id=workspace_id)
    if normalized["mode"] == REPORT_REQUEST_GENERATE:
        artifact = generate_report_artifact_from_source_documents(
            list(normalized.get("documents", [])),
            source_context={"mode": REPORT_REQUEST_GENERATE, "documentCount": len(normalized.get("documents", []))},
        )
        if artifact is None:
            raise ReportRequestError("report generation failed")
        return artifact

    source_row = get_analysis_report(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        report_id=str(normalized["reportId"]),
    )
    if source_row is None:
        raise ReportRequestError("report not found")
    source_artifact = as_dict(source_row.artifact_json)
    source_documents = _source_documents_from_artifact(source_artifact)
    if not source_documents:
        raise ReportRequestError("source snapshot is unavailable")
    artifact = generate_report_artifact_from_source_documents(
        source_documents,
        source_context={"mode": REPORT_REQUEST_REGENERATE, "sourceReportId": clean_text(source_row.report_id)},
    )
    if artifact is None:
        raise ReportRequestError("report regeneration failed")
    if isinstance(source_artifact.get("scope"), dict):
        artifact["scope"] = {
            **dict(source_artifact.get("scope", {})),
            **(dict(artifact.get("scope", {})) if isinstance(artifact.get("scope"), dict) else {}),
        }
    return artifact


def report_preview_metadata(artifact: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(artifact, dict) or not artifact:
        return {}
    report_id = clean_text(artifact.get("reportId"))
    preview_excerpt = (
        clean_text(artifact.get("previewExcerpt"))
        or clean_text(artifact.get("preview"))
        or _bounded_report_preview(str(artifact.get("markdownBody") or ""))
    )
    metadata = _report_download_metadata(report_id)
    render_profile = as_dict(artifact.get("renderProfile"))
    return drop_empty(
        {
            "reportId": report_id,
            "title": clean_text(artifact.get("title")),
            "status": clean_text(artifact.get("status")) or "completed",
            "previewExcerpt": preview_excerpt,
            "preview": preview_excerpt,
            "availableFormats": metadata["availableFormats"],
            "downloadUrls": metadata["downloadUrls"],
            "previewUrl": _report_preview_url(report_id),
            "renderStyle": clean_text(render_profile.get("style")) or DEFAULT_REPORT_RENDER_STYLE,
            "limitations": artifact.get("limitations") if isinstance(artifact.get("limitations"), list) else [],
        }
    )


def analysis_report_to_payload(row: AnalysisReport, *, include_body: bool = False) -> dict[str, Any]:
    artifact = as_dict(row.artifact_json)
    paginated_bundle = as_dict(artifact.get("paginatedReportBundle"))
    preview_excerpt = (
        clean_text(artifact.get("previewExcerpt"))
        or clean_text(artifact.get("preview"))
        or _bounded_report_preview(row.markdown_body or "")
    )
    metadata = _report_download_metadata(row.report_id)
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
            "previewUrl": _report_preview_url(row.report_id),
            "renderStyle": clean_text(as_dict(artifact.get("renderProfile")).get("style")) or DEFAULT_REPORT_RENDER_STYLE,
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
    return _safe_report_filename(row, report_format)


def find_report_asset(row: AnalysisReport, asset_id: str) -> dict[str, Any] | None:
    return _find_report_asset(row, asset_id)


def inline_asset_response_payload(asset: dict[str, Any]) -> tuple[bytes, str, str] | None:
    return _inline_asset_response_payload(asset)


def report_row_forbidden_values(row: AnalysisReport) -> list[str]:
    return _report_row_forbidden_values(row)


def _bundle_backed_report_row(row: AnalysisReport | None) -> bool:
    if row is None:
        return False
    artifact = as_dict(row.artifact_json)
    bundle = as_dict(artifact.get("paginatedReportBundle"))
    return bool(clean_text(bundle.get("schemaVersion")))


def delete_legacy_report_rows(
    db: Session,
    *,
    user_id: int,
    workspace_id: str | None = None,
    report_id: str | None = None,
) -> list[str]:
    criteria = [AnalysisReport.user_id == user_id]
    clean_workspace_id = clean_text(workspace_id)
    clean_report_id = clean_text(report_id)
    if clean_workspace_id:
        criteria.append(AnalysisReport.workspace_id == clean_workspace_id)
    if clean_report_id:
        criteria.append(AnalysisReport.report_id == clean_report_id)
    rows = db.execute(select(AnalysisReport).where(*criteria)).scalars().all()
    deleted: list[str] = []
    for row in rows:
        if _bundle_backed_report_row(row):
            continue
        deleted.append(str(row.report_id))
        db.delete(row)
    if deleted:
        db.flush()
    return deleted


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
    delete_legacy_report_rows(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        report_id=clean_report_id,
    )
    row = _get_analysis_report(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        report_id=clean_report_id,
    )
    if row is None or _bundle_backed_report_row(row):
        return row
    db.delete(row)
    db.flush()
    return None


def save_analysis_report_artifact(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    role: str,
    conversation_id: str,
    artifact: dict[str, Any] | None,
) -> AnalysisReport | None:
    delete_legacy_report_rows(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    return _save_analysis_report_artifact(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
        conversation_id=conversation_id,
        artifact=artifact,
    )


def attach_analysis_session_scope(
    artifact: dict[str, Any] | None,
    *,
    analysis_session: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(artifact, dict) or not artifact:
        return artifact
    session_payload = dict(analysis_session) if isinstance(analysis_session, dict) else {}
    if not session_payload:
        return artifact
    scope = dict(artifact.get("scope", {})) if isinstance(artifact.get("scope"), dict) else {}
    session_id = clean_text(session_payload.get("sessionId"))
    if session_id and not clean_text(scope.get("analysisSessionId")):
        scope["analysisSessionId"] = session_id
    if session_payload.get("revision") is not None:
        scope["analysisSessionRevision"] = int(session_payload.get("revision") or 0)
    artifact["scope"] = scope
    return artifact


def persist_report_artifact_result(
    db: Session,
    *,
    result: dict[str, Any],
    user_id: int,
    workspace_id: str,
    role: str,
    conversation_id: str,
    analysis_session: dict[str, Any] | None = None,
) -> None:
    artifact = result.get("analysisReportArtifact")
    if not isinstance(artifact, dict) or not artifact:
        return
    attach_analysis_session_scope(artifact, analysis_session=analysis_session)
    row = save_analysis_report_artifact(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
        conversation_id=conversation_id,
        artifact=artifact,
    )
    if row is None:
        return
    result["analysisReport"] = analysis_report_to_payload(row)
    result.pop("analysisReportArtifact", None)
