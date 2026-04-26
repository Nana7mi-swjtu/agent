from __future__ import annotations

from typing import Any

from .contracts import APPROVED_COLOR_TOKENS, APPROVED_LAYOUTS, PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION, as_dict, as_list, clean_text

FORBIDDEN_READER_TERMS = {"moduleId", "traceRefs", "sourceIds", "artifact_json", "robotics_risk", "analysis_reports"}


def validate_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if bundle.get("schemaVersion") != PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION:
        errors.append({"code": "invalid_bundle_schema", "severity": "error"})
    pages = [page for page in as_list(bundle.get("pages")) if isinstance(page, dict)]
    if not pages:
        errors.append({"code": "missing_pages", "severity": "error"})
    evidence_ids = {clean_text(item.get("evidenceId")) for item in as_list(bundle.get("evidenceRefs")) if isinstance(item, dict)}
    table_ids = {clean_text(item.get("tableId")) for item in as_list(as_dict(bundle.get("semanticModel")).get("tables")) if isinstance(item, dict)}
    for page in pages:
        layout = clean_text(page.get("layout"))
        if layout and layout not in APPROVED_LAYOUTS:
            errors.append({"code": "unsupported_layout", "severity": "error", "pageId": page.get("id"), "layout": layout})
        text = " ".join(clean_text(block) for block in as_list(page.get("blocks")))
        for term in FORBIDDEN_READER_TERMS:
            if term in text:
                errors.append({"code": "internal_term_leakage", "severity": "error", "pageId": page.get("id"), "term": term})
        for ref in as_list(page.get("evidenceRefs")):
            if clean_text(ref) and clean_text(ref) not in evidence_ids:
                errors.append({"code": "missing_evidence_ref", "severity": "warning", "pageId": page.get("id"), "evidenceRef": ref})
        tokens = as_dict(page.get("styleTokens"))
        for key, value in tokens.items():
            token = clean_text(value)
            if key.endswith("Color") and token not in APPROVED_COLOR_TOKENS:
                errors.append({"code": "unsupported_color_token", "severity": "error", "pageId": page.get("id"), "token": token})
    for chart in as_list(bundle.get("chartSpecs")):
        if not isinstance(chart, dict):
            continue
        data_ref = clean_text(chart.get("dataRef"))
        if data_ref and data_ref not in table_ids:
            errors.append({"code": "ungrounded_chart", "severity": "error", "chartId": chart.get("chartId"), "dataRef": data_ref})
    return errors


def has_blocking_errors(flags: list[dict[str, Any]]) -> bool:
    return any(clean_text(flag.get("severity")) == "error" for flag in flags if isinstance(flag, dict))