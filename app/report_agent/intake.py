from __future__ import annotations

import json
from typing import Any

from .contracts import MATERIAL_TYPES, REPORT_MATERIAL_SCHEMA_VERSION, as_dict, clean_text, drop_empty, utc_now_iso


def _looks_like_markdown(text: str) -> bool:
    return any(marker in text for marker in ("# ", "## ", "|", "- ", "```"))


def _detect_payload_type(content: Any, requested_type: str = "auto") -> str:
    clean_type = clean_text(requested_type).lower() or "auto"
    if clean_type in MATERIAL_TYPES and clean_type != "auto":
        return clean_type
    if isinstance(content, list):
        if all(isinstance(item, dict) for item in content):
            return "table"
        return "mixed"
    if isinstance(content, dict):
        if any(key in content for key in ("artifactId", "moduleId", "markdownBody", "readerPacket")):
            return "module_artifact"
        if any(key in content for key in ("rows", "columns", "tableId")):
            return "table"
        if any(key in content for key in ("value", "unit", "metric", "metricId")):
            return "metric"
        return "json"
    text = clean_text(content)
    if not text:
        return "text"
    if text.startswith("{") or text.startswith("["):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return "table" if all(isinstance(item, dict) for item in parsed) else "mixed"
        if isinstance(parsed, dict):
            return "json"
    return "markdown" if _looks_like_markdown(text) else "text"


def _content_summary(content: Any, content_type: str) -> str:
    if isinstance(content, dict):
        title = clean_text(content.get("title") or content.get("name") or content.get("summary"), limit=160)
        if title:
            return title
        keys = ", ".join(list(content.keys())[:8])
        return f"{content_type} payload: {keys}" if keys else content_type
    if isinstance(content, list):
        return f"{content_type} payload with {len(content)} items"
    return clean_text(content, limit=220)


def normalize_material(value: Any, *, index: int = 0) -> dict[str, Any]:
    payload = dict(value) if isinstance(value, dict) else {"content": value}
    content = payload.get("content")
    if content is None:
        content = payload.get("data") if "data" in payload else payload.get("artifact")
    requested_type = payload.get("contentType") or payload.get("type") or "auto"
    detected_type = _detect_payload_type(content, requested_type)
    source = as_dict(payload.get("source"))
    source_id = clean_text(payload.get("sourceId") or source.get("id") or payload.get("artifactId") or f"material_{index + 1}")
    title = clean_text(payload.get("title") or source.get("title") or _content_summary(content, detected_type), limit=160)
    quality_flags = []
    if not clean_text(content) and not isinstance(content, (dict, list)):
        quality_flags.append({"code": "empty_material", "severity": "warning", "materialId": source_id})
    return drop_empty(
        {
            "schemaVersion": REPORT_MATERIAL_SCHEMA_VERSION,
            "materialId": source_id,
            "title": title or f"Material {index + 1}",
            "contentType": clean_text(requested_type).lower() or "auto",
            "detectedType": detected_type,
            "content": content,
            "metadata": as_dict(payload.get("metadata")),
            "source": source,
            "attachments": payload.get("attachments") if isinstance(payload.get("attachments"), list) else [],
            "receivedAt": utc_now_iso(),
            "qualityFlags": quality_flags,
        }
    )


def intake_materials(materials: list[Any]) -> dict[str, Any]:
    normalized = [normalize_material(item, index=index) for index, item in enumerate(materials or [])]
    flags = [flag for item in normalized for flag in item.get("qualityFlags", []) if isinstance(flag, dict)]
    return {"materials": normalized, "qualityFlags": flags}