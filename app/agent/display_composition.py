from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DISPLAY_COMPOSITION_PROMPT_VERSION = "display_composer.v1"
DISPLAY_COMPOSITION_PLACEHOLDER_PATTERN = re.compile(r"\{\{(table|asset):([A-Za-z0-9._-]+)\}\}")

_RAW_PLACEHOLDER_PATTERN = re.compile(r"\{\{([^{}]+)\}\}")
_BLOCKED_INTERNAL_FIELDS = (
    "moduleId",
    "runId",
    "traceRefs",
    "sourceIds",
    "eventIds",
    "citationMap",
    "domainOutputIds",
    "findingIds",
    "modelOutputIds",
    "storageRef",
)
_BLOCKED_INTERNAL_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(item) for item in _BLOCKED_INTERNAL_FIELDS) + r")\b",
    flags=re.IGNORECASE,
)


def load_display_composition_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent / "prompts" / f"{DISPLAY_COMPOSITION_PROMPT_VERSION}.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return (
        "你是一个展示编排 agent。你的唯一任务是基于输入的 documentHandoff，生成面向用户展示的 Markdown 文档。"
        "你只能整理、压缩、排序、组合 documentHandoff 中已经存在的结论、表格、图表和证据材料。"
        "不得新增事实、数字、结论、来源、图表、表格或判断。"
        "只能使用 {{table:<tableId>}} 和 {{asset:<assetId>}} 占位符。"
        "禁止输出 moduleId、runId、traceRefs、sourceIds、eventIds、citationMap、domainOutputIds、findingIds、modelOutputIds、storageRef。"
    )


def compose_display_markdown(
    document_handoff: Any,
    *,
    writer: Any | None = None,
    fallback_markdown: str = "",
) -> dict[str, Any]:
    handoff = _dict_value(document_handoff)
    fallback = _clean_text(fallback_markdown)
    prompt_version = DISPLAY_COMPOSITION_PROMPT_VERSION
    validation_errors: list[str] = []
    composed_markdown = ""
    if handoff and writer is not None:
        composed_markdown = _invoke_writer(writer, build_display_composition_packet(handoff))
        validation_errors = validate_display_markdown(composed_markdown, handoff)
        if composed_markdown and not validation_errors:
            return _drop_empty(
                {
                    "markdown": composed_markdown,
                    "composedMarkdown": composed_markdown,
                    "displayComposition": {
                        "mode": "composed",
                        "source": "documentHandoff",
                        "promptVersion": prompt_version,
                        "validationErrors": [],
                    },
                }
            )
        composed_markdown = ""
    if fallback:
        fallback_errors = validate_display_markdown(fallback, handoff, allow_placeholders=False)
        return _drop_empty(
            {
                "markdown": fallback,
                "fallbackMarkdown": fallback,
                "displayComposition": {
                    "mode": "fallback_markdown",
                    "source": "fallbackMarkdown",
                    "promptVersion": prompt_version,
                    "validationErrors": validation_errors or fallback_errors,
                },
            }
        )
    handoff_fallback = _handoff_text_fallback(handoff)
    return _drop_empty(
        {
            "markdown": handoff_fallback,
            "displayComposition": {
                "mode": "fallback_handoff",
                "source": "documentHandoff",
                "promptVersion": prompt_version,
                "validationErrors": validation_errors,
            },
        }
    )


def build_display_composition_packet(document_handoff: Any) -> dict[str, Any]:
    handoff = _dict_value(document_handoff)
    fact_tables = _list_of_dicts(handoff.get("factTables"))
    rendered_assets = _list_of_dicts(handoff.get("renderedAssets"))
    return _drop_empty(
        {
            "documentHandoff": {
                "title": _clean_text(handoff.get("title")),
                "executiveSummary": _drop_empty(
                    {
                        "headline": _clean_text(_dict_value(handoff.get("executiveSummary")).get("headline")),
                        "opportunity": _clean_text(_dict_value(handoff.get("executiveSummary")).get("opportunity")),
                        "risk": _clean_text(_dict_value(handoff.get("executiveSummary")).get("risk")),
                    }
                ),
                "recommendedSections": [
                    _drop_empty(
                        {
                            "id": _clean_text(item.get("id")),
                            "title": _clean_text(item.get("title")),
                            "content": _string_list(item.get("content")),
                            "items": [_reader_item_payload(entry) for entry in _list_of_dicts(item.get("items"))[:6]],
                            "emptyState": _clean_text(item.get("emptyState")),
                            "resourceRefs": _dict_value(item.get("resourceRefs")),
                        }
                    )
                    for item in _list_of_dicts(handoff.get("recommendedSections"))
                ],
                "opportunitySections": [_reader_item_payload(item) for item in _list_of_dicts(handoff.get("opportunitySections"))[:6]],
                "riskSections": [_reader_item_payload(item) for item in _list_of_dicts(handoff.get("riskSections"))[:6]],
                "evidenceReferences": [_reader_evidence_payload(item) for item in _list_of_dicts(handoff.get("evidenceReferences"))[:8]],
                "visualSummaries": [_reader_visual_payload(item) for item in _list_of_dicts(handoff.get("visualSummaries"))[:6]],
                "factTables": [
                    _drop_empty(
                        {
                            "tableId": _clean_text(item.get("tableId")),
                            "title": _clean_text(item.get("title") or item.get("tableId")),
                            "description": _clean_text(item.get("description")),
                            "emptyText": _clean_text(item.get("emptyText")),
                            "columnLabels": [
                                _clean_text(column.get("label") or column.get("key"))
                                for column in _list_of_dicts(item.get("columns"))[:8]
                                if _clean_text(column.get("label") or column.get("key"))
                            ],
                            "rowCount": len(_list_of_dicts(item.get("rows"))),
                        }
                    )
                    for item in fact_tables
                ],
                "renderedAssets": [
                    _drop_empty(
                        {
                            "assetId": _clean_text(item.get("assetId")),
                            "title": _clean_text(item.get("title") or item.get("assetId")),
                            "caption": _clean_text(item.get("caption")),
                            "interpretationBoundary": _clean_text(item.get("interpretationBoundary")),
                            "sourceTableId": _clean_text(item.get("sourceTableId")),
                            "fallbackTableId": _clean_text(item.get("fallbackTableId")),
                        }
                    )
                    for item in rendered_assets
                ],
                "sectionResources": _dict_value(handoff.get("sectionResources")),
                "limitations": _string_list(handoff.get("limitations")),
            }
        }
    )


def validate_display_markdown(
    markdown: str,
    document_handoff: Any,
    *,
    allow_placeholders: bool = True,
) -> list[str]:
    clean = _clean_text(markdown)
    handoff = _dict_value(document_handoff)
    if not clean:
        return ["empty_output"]
    errors: list[str] = []
    if _BLOCKED_INTERNAL_PATTERN.search(clean):
        errors.append("blocked_internal_field")
    raw_placeholders = _RAW_PLACEHOLDER_PATTERN.findall(clean)
    if not allow_placeholders and raw_placeholders:
        errors.append("placeholders_not_allowed")
    table_ids = {
        _clean_text(item.get("tableId"))
        for item in _list_of_dicts(handoff.get("factTables"))
        if _clean_text(item.get("tableId"))
    }
    asset_ids = {
        _clean_text(item.get("assetId"))
        for item in _list_of_dicts(handoff.get("renderedAssets"))
        if _clean_text(item.get("assetId"))
    }
    valid_tokens = {
        f"{kind}:{identifier}"
        for kind, identifier in DISPLAY_COMPOSITION_PLACEHOLDER_PATTERN.findall(clean)
    }
    for raw in raw_placeholders:
        token = raw.strip()
        if token not in valid_tokens:
            errors.append(f"invalid_placeholder:{token}")
    for kind, identifier in DISPLAY_COMPOSITION_PLACEHOLDER_PATTERN.findall(clean):
        if kind == "table" and identifier not in table_ids:
            errors.append(f"unknown_table:{identifier}")
        if kind == "asset" and identifier not in asset_ids:
            errors.append(f"unknown_asset:{identifier}")
    return _dedupe(errors)


def _invoke_writer(writer: Any, packet: dict[str, Any]) -> str:
    try:
        response = writer.invoke(
            [
                {"role": "system", "content": load_display_composition_prompt()},
                {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
            ]
        )
    except Exception:
        return ""
    content = getattr(response, "content", response)
    if isinstance(content, dict):
        text = _clean_text(content.get("markdown") or content.get("content"))
    else:
        text = _clean_text(content)
    return _strip_markdown_fence(text)


def _handoff_text_fallback(document_handoff: dict[str, Any]) -> str:
    handoff = _dict_value(document_handoff)
    title = _clean_text(handoff.get("title")) or "模块分析结果"
    executive = _dict_value(handoff.get("executiveSummary"))
    opportunity_sections = _list_of_dicts(handoff.get("opportunitySections"))
    risk_sections = _list_of_dicts(handoff.get("riskSections"))
    evidence_references = _list_of_dicts(handoff.get("evidenceReferences"))
    limitations = _string_list(handoff.get("limitations"))
    lines: list[str] = [f"# {title}", ""]
    summary_lines = [
        _clean_text(executive.get("headline")),
        _clean_text(executive.get("opportunity")),
        _clean_text(executive.get("risk")),
    ]
    if any(summary_lines):
        lines.extend(["## 执行摘要", ""])
        lines.extend([item for item in summary_lines if item])
        lines.append("")
    if opportunity_sections:
        lines.extend(["## 机会信号", ""])
        for item in opportunity_sections[:3]:
            title_text = _clean_text(item.get("title"))
            summary_text = _clean_text(item.get("summary") or item.get("basisSummary"))
            if title_text and summary_text:
                lines.append(f"- {title_text}：{summary_text}")
            elif title_text:
                lines.append(f"- {title_text}")
        lines.append("")
    if risk_sections:
        lines.extend(["## 风险信号", ""])
        for item in risk_sections[:3]:
            title_text = _clean_text(item.get("title"))
            summary_text = _clean_text(item.get("summary") or item.get("basisSummary"))
            if title_text and summary_text:
                lines.append(f"- {title_text}：{summary_text}")
            elif title_text:
                lines.append(f"- {title_text}")
        lines.append("")
    if evidence_references:
        lines.extend(["## 证据与引用", ""])
        for item in evidence_references[:5]:
            title_text = _clean_text(item.get("title"))
            summary_text = _clean_text(item.get("readerSummary") or item.get("verificationStatus"))
            if title_text and summary_text:
                lines.append(f"- {title_text}：{summary_text}")
            elif title_text:
                lines.append(f"- {title_text}")
        lines.append("")
    if limitations:
        lines.extend(["## 限制说明", ""])
        lines.extend([f"- {item}" for item in limitations[:5] if item])
        lines.append("")
    return "\n".join(lines).strip()


def _reader_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": _clean_text(item.get("id")),
            "type": _clean_text(item.get("type")),
            "title": _clean_text(item.get("title")),
            "summary": _clean_text(item.get("summary")),
            "basisSummary": _clean_text(item.get("basisSummary")),
            "interpretationBoundary": _clean_text(item.get("interpretationBoundary")),
            "resourceRefs": _dict_value(item.get("resourceRefs")),
        }
    )


def _reader_evidence_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": _clean_text(item.get("id")),
            "title": _clean_text(item.get("title")),
            "readerSummary": _clean_text(item.get("readerSummary")),
            "verificationStatus": _clean_text(item.get("verificationStatus")),
            "sourceName": _clean_text(item.get("sourceName")),
        }
    )


def _reader_visual_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": _clean_text(item.get("id")),
            "title": _clean_text(item.get("title")),
            "caption": _clean_text(item.get("caption")),
            "interpretationBoundary": _clean_text(item.get("interpretationBoundary")),
        }
    )


def _strip_markdown_fence(value: str) -> str:
    text = _clean_text(value)
    match = re.match(r"^```(?:markdown|md)?\s*(.*?)\s*```$", text, flags=re.S | re.I)
    if match is not None:
        return _clean_text(match.group(1))
    return text


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
        clean = _clean_text(item)
        if clean and clean not in result:
            result.append(clean)
    return result


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _drop_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _drop_empty(item) for key, item in value.items() if item not in (None, "", [], {})}
    if isinstance(value, list):
        return [_drop_empty(item) for item in value if item not in (None, "", [], {})]
    return value


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        clean = _clean_text(item)
        if clean and clean not in result:
            result.append(clean)
    return result
