from __future__ import annotations

from typing import Any

from .contracts import (
    APPROVED_COLOR_TOKENS,
    APPROVED_LAYOUTS,
    BLOCK_TYPES,
    PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION,
    PAGE_TYPES,
    as_dict,
    as_list,
    clean_text,
)

FORBIDDEN_READER_TERMS = {"moduleId", "traceRefs", "sourceIds", "artifact_json", "robotics_risk", "analysis_reports"}
FORBIDDEN_PRESENTATION_TERMS = {"本页", "判断依据", "关键依据", "解读边界", "表格边界", "图表解读", "关键表格"}
FORBIDDEN_PAGE_TITLES = {"逻辑拆解", "边界与限制", "来源与核验"}


def _flatten_text(value: Any) -> list[str]:
    if isinstance(value, dict):
        items: list[str] = []
        for item in value.values():
            items.extend(_flatten_text(item))
        return items
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(_flatten_text(item))
        return items
    text = clean_text(value)
    return [text] if text else []


def validate_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if bundle.get("schemaVersion") != PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION:
        errors.append({"code": "invalid_bundle_schema", "severity": "error"})
    pages = [page for page in as_list(bundle.get("pages")) if isinstance(page, dict)]
    if not pages:
        errors.append({"code": "missing_pages", "severity": "error"})
    elif clean_text(pages[0].get("pageType")) != "cover":
        errors.append({"code": "missing_cover_page", "severity": "error"})
    elif len(pages) < 2 or clean_text(pages[1].get("pageType")) != "table_of_contents":
        errors.append({"code": "missing_toc_page", "severity": "error"})
    evidence_ids = {clean_text(item.get("evidenceId")) for item in as_list(bundle.get("evidenceRefs")) if isinstance(item, dict)}
    table_ids = {clean_text(item.get("tableId")) for item in as_list(as_dict(bundle.get("semanticModel")).get("tables")) if isinstance(item, dict)}
    for page in pages:
        page_type = clean_text(page.get("pageType"))
        if page_type and page_type not in PAGE_TYPES:
            errors.append({"code": "unsupported_page_type", "severity": "error", "pageId": page.get("id"), "pageType": page_type})
        layout = clean_text(page.get("layout"))
        if layout and layout not in APPROVED_LAYOUTS:
            errors.append({"code": "unsupported_layout", "severity": "error", "pageId": page.get("id"), "layout": layout})
        title = clean_text(page.get("title"))
        if title in FORBIDDEN_PAGE_TITLES:
            errors.append({"code": "forbidden_page_title", "severity": "error", "pageId": page.get("id"), "title": title})
        text = " ".join(part for part in [title, *_flatten_text(page.get("blocks"))] if part)
        for term in FORBIDDEN_READER_TERMS:
            if term in text:
                errors.append({"code": "internal_term_leakage", "severity": "error", "pageId": page.get("id"), "term": term})
        for term in FORBIDDEN_PRESENTATION_TERMS:
            if term in text:
                errors.append({"code": "template_term_leakage", "severity": "error", "pageId": page.get("id"), "term": term})
        for block in as_list(page.get("blocks")):
            if not isinstance(block, dict):
                continue
            block_type = clean_text(block.get("type"))
            if block_type and block_type not in BLOCK_TYPES:
                errors.append({"code": "unsupported_block_type", "severity": "error", "pageId": page.get("id"), "blockType": block_type})
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
