from __future__ import annotations

from typing import Any


FACT_TABLE_SCHEMA_VERSION = "analysis_fact_table.v1"
CHART_CANDIDATE_SCHEMA_VERSION = "analysis_chart_candidate.v1"
RENDERED_ASSET_SCHEMA_VERSION = "analysis_rendered_asset.v1"

TRACE_REF_KEYS = (
    "sourceIds",
    "eventIds",
    "signalIds",
    "limitationIds",
    "rowIds",
    "tableIds",
    "chartIds",
    "assetIds",
    "domainOutputIds",
    "findingIds",
    "modelOutputIds",
)


def build_fact_table(
    *,
    table_id: str,
    title: str,
    columns: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    description: str = "",
    empty_text: str = "",
    trace_refs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return normalize_fact_table(
        {
            "tableId": table_id,
            "title": title,
            "columns": columns,
            "rows": rows,
            "description": description,
            "emptyText": empty_text,
            "traceRefs": trace_refs or {},
            "metadata": metadata or {},
        }
    )


def build_chart_candidate(
    *,
    chart_id: str,
    source_table_id: str,
    chart_type: str,
    title: str,
    series: list[dict[str, Any]],
    caption: str = "",
    interpretation_boundary: str = "",
    eligibility: dict[str, Any] | None = None,
    fallback_table_id: str = "",
    trace_refs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return normalize_chart_candidate(
        {
            "chartId": chart_id,
            "sourceTableId": source_table_id,
            "chartType": chart_type,
            "title": title,
            "series": series,
            "caption": caption,
            "interpretationBoundary": interpretation_boundary,
            "eligibility": eligibility or {},
            "fallbackTableId": fallback_table_id,
            "traceRefs": trace_refs or {},
            "metadata": metadata or {},
        }
    )


def build_rendered_asset(
    *,
    asset_id: str,
    chart_id: str,
    source_table_id: str,
    title: str,
    content_type: str,
    alt_text: str,
    caption: str = "",
    interpretation_boundary: str = "",
    render_payload: dict[str, Any] | None = None,
    trace_refs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return normalize_rendered_asset(
        {
            "assetId": asset_id,
            "chartId": chart_id,
            "sourceTableId": source_table_id,
            "title": title,
            "contentType": content_type,
            "altText": alt_text,
            "caption": caption,
            "interpretationBoundary": interpretation_boundary,
            "renderPayload": render_payload or {},
            "traceRefs": trace_refs or {},
            "metadata": metadata or {},
        }
    )


def normalize_fact_table(value: Any) -> dict[str, Any]:
    payload = dict(value or {}) if isinstance(value, dict) else {}
    columns = []
    column_keys: list[str] = []
    for item in payload.get("columns", []) if isinstance(payload.get("columns"), list) else []:
        if not isinstance(item, dict):
            continue
        key = _clean_text(item.get("key"))
        label = _clean_text(item.get("label")) or key
        if not key or key in column_keys:
            continue
        column_keys.append(key)
        columns.append(
            _drop_empty(
                {
                    "key": key,
                    "label": label,
                    "kind": _clean_text(item.get("kind")),
                    "align": _clean_text(item.get("align")),
                }
            )
        )

    rows = []
    for index, item in enumerate(payload.get("rows", []) if isinstance(payload.get("rows"), list) else [], start=1):
        if not isinstance(item, dict):
            continue
        raw_cells = item.get("cells") if isinstance(item.get("cells"), dict) else {}
        cells = {
            key: _normalize_cell_value(raw_cells.get(key))
            for key in column_keys
            if raw_cells.get(key) not in (None, "", [], {})
        }
        empty_state = bool(item.get("emptyState"))
        rows.append(
            _drop_empty(
                {
                    "rowId": _clean_text(item.get("rowId")) or f"{_clean_text(payload.get('tableId'))}_row_{index:02d}",
                    "cells": cells,
                    "traceRefs": normalize_trace_refs(item.get("traceRefs") or item.get("trace_refs")),
                    "emptyState": empty_state or None,
                    "summary": _clean_text(item.get("summary")),
                }
            )
        )

    return _drop_empty(
        {
            "schemaVersion": FACT_TABLE_SCHEMA_VERSION,
            "tableId": _clean_text(payload.get("tableId") or payload.get("id")),
            "title": _clean_text(payload.get("title")) or "表格",
            "description": _clean_text(payload.get("description")),
            "emptyText": _clean_text(payload.get("emptyText") or payload.get("empty_text")),
            "columns": columns,
            "rows": rows,
            "traceRefs": normalize_trace_refs(payload.get("traceRefs") or payload.get("trace_refs")),
            "metadata": _dict_value(payload.get("metadata")),
        }
    )


def normalize_chart_candidate(value: Any) -> dict[str, Any]:
    payload = dict(value or {}) if isinstance(value, dict) else {}
    series: list[dict[str, Any]] = []
    for item in payload.get("series", []) if isinstance(payload.get("series"), list) else []:
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("label") or item.get("name"))
        if not label:
            continue
        series.append(
            _drop_empty(
                {
                    "label": label,
                    "value": _normalize_cell_value(item.get("value")),
                    "date": _clean_text(item.get("date")),
                    "summary": _clean_text(item.get("summary")),
                    "rowId": _clean_text(item.get("rowId")),
                }
            )
        )

    return _drop_empty(
        {
            "schemaVersion": CHART_CANDIDATE_SCHEMA_VERSION,
            "chartId": _clean_text(payload.get("chartId") or payload.get("id")),
            "sourceTableId": _clean_text(payload.get("sourceTableId")),
            "chartType": _clean_text(payload.get("chartType")).lower() or "bar",
            "title": _clean_text(payload.get("title")) or "图表",
            "caption": _clean_text(payload.get("caption")),
            "interpretationBoundary": _clean_text(payload.get("interpretationBoundary")),
            "eligibility": _dict_value(payload.get("eligibility")),
            "fallbackTableId": _clean_text(payload.get("fallbackTableId")),
            "series": series,
            "traceRefs": normalize_trace_refs(payload.get("traceRefs") or payload.get("trace_refs")),
            "metadata": _dict_value(payload.get("metadata")),
        }
    )


def normalize_rendered_asset(value: Any) -> dict[str, Any]:
    payload = dict(value or {}) if isinstance(value, dict) else {}
    return _drop_empty(
        {
            "schemaVersion": RENDERED_ASSET_SCHEMA_VERSION,
            "assetId": _clean_text(payload.get("assetId") or payload.get("id")),
            "chartId": _clean_text(payload.get("chartId")),
            "sourceTableId": _clean_text(payload.get("sourceTableId")),
            "title": _clean_text(payload.get("title")) or "图表资产",
            "caption": _clean_text(payload.get("caption")),
            "altText": _clean_text(payload.get("altText") or payload.get("accessibilityText")) or _clean_text(payload.get("title")),
            "contentType": _clean_text(payload.get("contentType")) or "image/png",
            "interpretationBoundary": _clean_text(payload.get("interpretationBoundary")),
            "renderPayload": _dict_value(payload.get("renderPayload") or payload.get("render_payload")),
            "traceRefs": normalize_trace_refs(payload.get("traceRefs") or payload.get("trace_refs")),
            "metadata": _dict_value(payload.get("metadata")),
        }
    )


def validate_tabular_artifacts(
    fact_tables: Any,
    chart_candidates: Any,
    rendered_assets: Any,
) -> list[str]:
    tables = [normalize_fact_table(item) for item in fact_tables if isinstance(item, dict)] if isinstance(fact_tables, list) else []
    candidates = [normalize_chart_candidate(item) for item in chart_candidates if isinstance(item, dict)] if isinstance(chart_candidates, list) else []
    assets = [normalize_rendered_asset(item) for item in rendered_assets if isinstance(item, dict)] if isinstance(rendered_assets, list) else []
    errors = [
        *validate_fact_tables(tables),
        *validate_chart_candidates(candidates, fact_tables=tables),
        *validate_rendered_assets(assets, chart_candidates=candidates, fact_tables=tables),
    ]
    return errors


def validate_fact_tables(fact_tables: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for table in fact_tables:
        table_id = _clean_text(table.get("tableId"))
        if not table_id:
            errors.append("fact table missing tableId")
            continue
        if table_id in seen_ids:
            errors.append(f"duplicate fact table id: {table_id}")
        seen_ids.add(table_id)
        column_keys = [_clean_text(item.get("key")) for item in table.get("columns", []) if isinstance(item, dict)]
        if not column_keys:
            errors.append(f"fact table {table_id} missing columns")
        for row in table.get("rows", []) if isinstance(table.get("rows"), list) else []:
            if not isinstance(row, dict):
                errors.append(f"fact table {table_id} contains invalid row")
                continue
            cells = row.get("cells") if isinstance(row.get("cells"), dict) else {}
            for key in cells.keys():
                if key not in column_keys:
                    errors.append(f"fact table {table_id} row {row.get('rowId', '')} has unknown cell key {key}")
            substantive = any(value not in (None, "", [], {}) for value in cells.values())
            trace_refs = normalize_trace_refs(row.get("traceRefs"))
            if substantive and not trace_refs and not bool(row.get("emptyState")):
                errors.append(f"fact table {table_id} row {row.get('rowId', '')} missing traceRefs")
    return errors


def validate_chart_candidates(
    chart_candidates: list[dict[str, Any]],
    *,
    fact_tables: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    table_ids = {_clean_text(item.get("tableId")) for item in fact_tables}
    for candidate in chart_candidates:
        chart_id = _clean_text(candidate.get("chartId"))
        if not chart_id:
            errors.append("chart candidate missing chartId")
            continue
        if chart_id in seen_ids:
            errors.append(f"duplicate chart candidate id: {chart_id}")
        seen_ids.add(chart_id)
        source_table_id = _clean_text(candidate.get("sourceTableId"))
        if not source_table_id:
            errors.append(f"chart candidate {chart_id} missing sourceTableId")
        elif source_table_id not in table_ids:
            errors.append(f"chart candidate {chart_id} references unknown table {source_table_id}")
        if not _clean_text(candidate.get("interpretationBoundary")):
            errors.append(f"chart candidate {chart_id} missing interpretationBoundary")
        if not isinstance(candidate.get("series"), list) or not candidate.get("series"):
            errors.append(f"chart candidate {chart_id} missing series")
    return errors


def validate_rendered_assets(
    rendered_assets: list[dict[str, Any]],
    *,
    chart_candidates: list[dict[str, Any]],
    fact_tables: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    candidate_ids = {_clean_text(item.get("chartId")) for item in chart_candidates}
    table_ids = {_clean_text(item.get("tableId")) for item in fact_tables}
    seen_ids: set[str] = set()
    for asset in rendered_assets:
        asset_id = _clean_text(asset.get("assetId"))
        if not asset_id:
            errors.append("rendered asset missing assetId")
            continue
        if asset_id in seen_ids:
            errors.append(f"duplicate rendered asset id: {asset_id}")
        seen_ids.add(asset_id)
        chart_id = _clean_text(asset.get("chartId"))
        if chart_id and chart_id not in candidate_ids:
            errors.append(f"rendered asset {asset_id} references unknown chart {chart_id}")
        table_id = _clean_text(asset.get("sourceTableId"))
        if table_id and table_id not in table_ids:
            errors.append(f"rendered asset {asset_id} references unknown table {table_id}")
        if not _clean_text(asset.get("altText")):
            errors.append(f"rendered asset {asset_id} missing altText")
        if not _clean_text(asset.get("contentType")):
            errors.append(f"rendered asset {asset_id} missing contentType")
    return errors


def ensure_valid_tabular_artifacts(
    fact_tables: Any,
    chart_candidates: Any,
    rendered_assets: Any,
) -> None:
    errors = validate_tabular_artifacts(fact_tables, chart_candidates, rendered_assets)
    if errors:
        raise ValueError("; ".join(errors))


def normalize_trace_refs(value: Any) -> dict[str, list[str]]:
    payload = dict(value or {}) if isinstance(value, dict) else {}
    refs: dict[str, list[str]] = {}
    for key in TRACE_REF_KEYS:
        items = _string_list(payload.get(key))
        if items:
            refs[key] = items
    return refs


def _normalize_cell_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    return _clean_text(value)


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


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
