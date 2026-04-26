from __future__ import annotations

from typing import Any

from .artifact import bundle_to_analysis_report_artifact
from .bundle import generate_paginated_report
from .contracts import REPORT_SOURCE_SNAPSHOT_SCHEMA_VERSION, clean_text


def _clean_source_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\x00", "").strip()


def _title_candidate_from_text(text: str) -> str:
    for raw_line in text.splitlines():
        candidate = raw_line.lstrip("#*- 0123456789.").strip()
        if 4 <= len(candidate) <= 36:
            return candidate
    for token in ("。", "！", "？", "\n"):
        if token in text:
            candidate = text.split(token, 1)[0].strip()
            if 4 <= len(candidate) <= 36:
                return candidate
    clean = clean_text(text, limit=24)
    return clean


def _derive_report_title(source_documents: list[dict[str, Any]]) -> str:
    for document in source_documents:
        title = clean_text(document.get("title"), limit=36)
        if title:
            if title.endswith("报告"):
                return title
            if title.endswith("分析"):
                return f"{title}报告"
            return f"{title}分析报告"
    for document in source_documents:
        candidate = _title_candidate_from_text(_clean_source_text(document.get("content")))
        if candidate:
            if candidate.endswith("报告"):
                return candidate
            if candidate.endswith("分析"):
                return f"{candidate}报告"
            return f"{candidate}分析报告"
    return "智能分析报告"


def _documents_to_materials(source_documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []
    for index, document in enumerate(source_documents, start=1):
        content = _clean_source_text(document.get("content"))
        if not content:
            continue
        title = clean_text(document.get("title"), limit=120) or f"原文材料 {index}"
        materials.append(
            {
                "sourceId": clean_text(document.get("sourceId")) or f"source_{index}",
                "title": title,
                "contentType": clean_text(document.get("contentType")) or "auto",
                "content": content,
                "metadata": {
                    "origin": "raw_text_request",
                    **(dict(document.get("metadata")) if isinstance(document.get("metadata"), dict) else {}),
                },
                "source": {
                    "id": clean_text(document.get("sourceId")) or f"source_{index}",
                    "type": "raw_text",
                },
            }
        )
    return materials


def _source_snapshot(source_documents: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schemaVersion": REPORT_SOURCE_SNAPSHOT_SCHEMA_VERSION,
        "documents": [
            {
                "sourceId": clean_text(document.get("sourceId")) or f"source_{index}",
                "title": clean_text(document.get("title"), limit=160) or f"原文材料 {index}",
                "contentType": clean_text(document.get("contentType")) or "auto",
                "content": _clean_source_text(document.get("content")),
            }
            for index, document in enumerate(source_documents, start=1)
            if _clean_source_text(document.get("content"))
        ],
    }


def generate_report_artifact_from_source_documents(
    source_documents: list[dict[str, Any]],
    *,
    source_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    documents = [dict(item) for item in source_documents if isinstance(item, dict)]
    materials = _documents_to_materials(documents)
    if not materials:
        return None
    report_title = _derive_report_title(documents)
    bundle = generate_paginated_report(
        materials=materials,
        title=report_title,
        render_style="professional",
        source_context=source_context or {"adapter": "RawTextReportRequest", "documentCount": len(materials)},
    )
    artifact = bundle_to_analysis_report_artifact(bundle, source_snapshot=_source_snapshot(documents))
    artifact["scope"] = {
        **(dict(artifact.get("scope", {})) if isinstance(artifact.get("scope"), dict) else {}),
        "sourceDocumentCount": len(materials),
    }
    artifact["previewExcerpt"] = clean_text(artifact.get("markdownBody"), limit=600)
    artifact["preview"] = artifact["previewExcerpt"]
    return artifact
