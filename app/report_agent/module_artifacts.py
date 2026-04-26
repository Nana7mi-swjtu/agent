from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.display_composition import compose_display_markdown
from ..models import AnalysisModuleArtifact
from .contracts import as_dict, clean_text

MODULE_ARTIFACT_SCHEMA_VERSION = "analysis_module_artifact.v1"


def build_analysis_module_artifacts(
    *,
    analysis_session: dict[str, Any],
    module_results: dict[str, dict[str, Any]],
    module_ids: list[str] | None = None,
    composer_writer: Any | None = None,
) -> list[dict[str, Any]]:
    session_payload = _dict_value(analysis_session)
    ordered_module_ids = _string_list(module_ids or session_payload.get("enabledModules"))
    if not ordered_module_ids:
        ordered_module_ids = [module_id for module_id in module_results.keys() if clean_text(module_id)]

    artifacts: list[dict[str, Any]] = []
    for module_id in ordered_module_ids:
        result = module_results.get(module_id)
        if not isinstance(result, dict):
            continue
        display_snapshot = compose_display_markdown(
            result.get("displayHandoff"),
            writer=composer_writer,
        )
        markdown_body = _clean_body_text(display_snapshot.get("markdown"))
        if not markdown_body:
            continue
        artifacts.append(
            _drop_empty(
                {
                    "schemaVersion": MODULE_ARTIFACT_SCHEMA_VERSION,
                    "artifactId": clean_text(result.get("moduleArtifactId")) or _new_module_artifact_id(),
                    "moduleId": clean_text(result.get("moduleId")) or module_id,
                    "moduleRunId": clean_text(result.get("runId")),
                    "title": _module_artifact_title(result, module_id=module_id),
                    "status": clean_text(result.get("status")) or "completed",
                    "contentType": "text/markdown",
                    "markdownBody": markdown_body,
                    "displayComposition": _dict_value(display_snapshot.get("displayComposition")),
                    "executiveSummary": _module_executive_summary(result),
                    "readerPacket": _module_reader_packet(result),
                    "evidenceReferences": _module_evidence_references(result),
                    "factTables": _module_fact_tables(result),
                    "chartCandidates": _module_chart_candidates(result),
                    "renderedAssets": _module_rendered_assets(result),
                    "visualSummaries": _module_visual_summaries(result),
                    "analysisSession": {
                        "sessionId": clean_text(session_payload.get("sessionId")),
                        "revision": _safe_int(session_payload.get("revision"), default=0),
                    },
                    "metadata": {
                        "displayName": clean_text(result.get("displayName")),
                        "summary": clean_text(result.get("summary")),
                        "moduleResult": result,
                    },
                }
            )
        )
    return artifacts


def save_analysis_module_artifacts(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    role: str,
    conversation_id: str,
    artifacts: list[dict[str, Any]],
    analysis_session: dict[str, Any] | None = None,
) -> list[AnalysisModuleArtifact]:
    rows: list[AnalysisModuleArtifact] = []
    session_payload = _dict_value(analysis_session)
    now = datetime.now(UTC).replace(tzinfo=None)
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_id = clean_text(artifact.get("artifactId"))
        module_id = clean_text(artifact.get("moduleId"))
        markdown_body = _clean_body_text(artifact.get("markdownBody") or artifact.get("textBody"))
        if not artifact_id or not module_id or not markdown_body:
            continue
        artifact_session = _dict_value(artifact.get("analysisSession"))
        analysis_session_id = clean_text(session_payload.get("sessionId") or artifact_session.get("sessionId")) or None
        analysis_session_revision = _safe_int(
            session_payload.get("revision", artifact_session.get("revision")),
            default=0,
        )
        row = db.execute(
            select(AnalysisModuleArtifact).where(AnalysisModuleArtifact.artifact_id == artifact_id)
        ).scalar_one_or_none()
        if row is None:
            row = AnalysisModuleArtifact(
                artifact_id=artifact_id,
                user_id=user_id,
                workspace_id=workspace_id,
                role=role,
                conversation_id=conversation_id,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        row.analysis_session_id = analysis_session_id
        row.analysis_session_revision = analysis_session_revision
        row.module_id = module_id
        row.module_run_id = clean_text(artifact.get("moduleRunId")) or None
        row.title = clean_text(artifact.get("title")) or "模块分析结果"
        row.status = clean_text(artifact.get("status")) or "completed"
        row.content_type = clean_text(artifact.get("contentType")) or "text/markdown"
        row.markdown_body = markdown_body
        row.text_body = _clean_body_text(artifact.get("textBody"))
        row.artifact_json = {
            key: value
            for key, value in artifact.items()
            if key not in {"markdownBody", "textBody"}
        }
        row.metadata_json = _dict_value(artifact.get("metadata"))
        row.updated_at = now
        rows.append(row)
    if rows:
        db.flush()
    return rows


def analysis_module_artifact_to_payload(
    row: AnalysisModuleArtifact,
    *,
    include_body: bool = True,
) -> dict[str, Any]:
    artifact_json = {
        key: value
        for key, value in _dict_value(row.artifact_json).items()
        if key not in {"composedMarkdown", "fallbackMarkdown"}
    }
    payload = _drop_empty(
        {
            **artifact_json,
            "artifactId": row.artifact_id,
            "moduleId": row.module_id,
            "moduleRunId": row.module_run_id,
            "title": row.title,
            "status": row.status,
            "contentType": row.content_type,
            "analysisSession": {
                "sessionId": row.analysis_session_id,
                "revision": int(row.analysis_session_revision or 0),
            },
            "createdAt": _format_datetime(row.created_at),
            "updatedAt": _format_datetime(row.updated_at),
        }
    )
    if include_body:
        payload["markdownBody"] = row.markdown_body or row.text_body or ""
    return payload


def get_analysis_module_artifacts_by_ids(
    db: Session,
    *,
    user_id: int,
    artifact_ids: list[str],
    workspace_id: str | None = None,
) -> list[AnalysisModuleArtifact]:
    clean_ids = _string_list(artifact_ids)
    if not clean_ids:
        return []
    criteria = [AnalysisModuleArtifact.user_id == user_id, AnalysisModuleArtifact.artifact_id.in_(clean_ids)]
    if workspace_id:
        criteria.append(AnalysisModuleArtifact.workspace_id == workspace_id)
    rows = db.execute(select(AnalysisModuleArtifact).where(*criteria)).scalars().all()
    row_by_id = {row.artifact_id: row for row in rows}
    return [row_by_id[artifact_id] for artifact_id in clean_ids if artifact_id in row_by_id]


def _module_reader_packet(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result.get("readerPacket"), dict) and result.get("readerPacket"):
        return _dict_value(result.get("readerPacket"))
    handoff = _dict_value(result.get("displayHandoff"))
    if isinstance(handoff.get("readerPacket"), dict) and handoff.get("readerPacket"):
        return _dict_value(handoff.get("readerPacket"))
    result_payload = _dict_value(result.get("result"))
    return _dict_value(result_payload.get("readerPacket"))


def _module_executive_summary(result: dict[str, Any]) -> dict[str, Any]:
    handoff = _dict_value(result.get("displayHandoff"))
    return _dict_value(handoff.get("executiveSummary"))


def _module_evidence_references(result: dict[str, Any]) -> list[dict[str, Any]]:
    references = _list_of_dicts(result.get("evidenceReferences"))
    if references:
        return references
    handoff = _dict_value(result.get("displayHandoff"))
    references = _list_of_dicts(handoff.get("evidenceReferences"))
    if references:
        return references
    reader_packet = _module_reader_packet(result)
    references = _list_of_dicts(reader_packet.get("evidenceReferences"))
    if references:
        return references
    return _list_of_dicts(handoff.get("evidenceTable"))


def _module_fact_tables(result: dict[str, Any]) -> list[dict[str, Any]]:
    tables = _list_of_dicts(result.get("factTables"))
    if tables:
        return tables
    handoff = _dict_value(result.get("displayHandoff"))
    tables = _list_of_dicts(handoff.get("factTables"))
    if tables:
        return tables
    result_payload = _dict_value(result.get("result"))
    return _list_of_dicts(result_payload.get("factTables"))


def _module_chart_candidates(result: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = _list_of_dicts(result.get("chartCandidates"))
    if candidates:
        return candidates
    handoff = _dict_value(result.get("displayHandoff"))
    candidates = _list_of_dicts(handoff.get("chartCandidates"))
    if candidates:
        return candidates
    result_payload = _dict_value(result.get("result"))
    return _list_of_dicts(result_payload.get("chartCandidates"))


def _module_rendered_assets(result: dict[str, Any]) -> list[dict[str, Any]]:
    assets = _list_of_dicts(result.get("renderedAssets"))
    if assets:
        return assets
    handoff = _dict_value(result.get("displayHandoff"))
    assets = _list_of_dicts(handoff.get("renderedAssets"))
    if assets:
        return assets
    result_payload = _dict_value(result.get("result"))
    return _list_of_dicts(result_payload.get("renderedAssets"))


def _module_visual_summaries(result: dict[str, Any]) -> list[dict[str, Any]]:
    visuals = _list_of_dicts(result.get("visualSummaries"))
    if visuals:
        return visuals
    handoff = _dict_value(result.get("displayHandoff"))
    visuals = _list_of_dicts(handoff.get("visualSummaries"))
    if visuals:
        return visuals
    return _list_of_dicts(_module_reader_packet(result).get("visualSummaries"))


def _module_artifact_title(result: dict[str, Any], *, module_id: str) -> str:
    handoff = _dict_value(result.get("displayHandoff"))
    return (
        clean_text(handoff.get("title"))
        or clean_text(result.get("title"))
        or clean_text(result.get("displayName"))
        or f"{module_id}分析结果"
    )


def _new_module_artifact_id() -> str:
    return f"mart_{uuid.uuid4().hex[:24]}"


def _clean_body_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\x00", "").strip()


def _format_datetime(value: Any) -> str:
    if not isinstance(value, datetime):
        return ""
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


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


def _drop_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _drop_empty(item)
            for key, item in value.items()
            if item not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_drop_empty(item) for item in value if item not in (None, "", [], {})]
    return value
