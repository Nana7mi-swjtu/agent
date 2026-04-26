from __future__ import annotations

import re
from typing import Any

from .contracts import APPROVED_COLOR_TOKENS, APPROVED_LAYOUTS, as_list, clean_text

_TIME_FIELD_HINTS = ("date", "time", "month", "quarter", "year", "week", "day", "period", "日期", "时间", "月份", "季度", "年份")
_TIME_VALUE_RE = re.compile(r"^(?:19|20)\d{2}(?:[-/.年](?:0?[1-9]|1[0-2]))?(?:[-/.月](?:0?[1-9]|[12]\d|3[01])日?)?$|^\d{4}Q[1-4]$", re.IGNORECASE)


def looks_temporal_chart_axis(field_name: str, rows: list[dict[str, Any]]) -> bool:
    lowered = clean_text(field_name).lower()
    if any(token in lowered for token in _TIME_FIELD_HINTS):
        return True
    samples = [clean_text(row.get(field_name)) for row in rows[:6] if isinstance(row, dict) and clean_text(row.get(field_name))]
    if len(samples) < 2:
        return False
    matched = sum(1 for item in samples if _TIME_VALUE_RE.match(item))
    return matched >= max(2, len(samples) - 1)


def build_chart_specs(semantic_model: dict[str, Any]) -> list[dict[str, Any]]:
    specs = []
    tables = {clean_text(item.get("tableId")): item for item in as_list(semantic_model.get("tables")) if isinstance(item, dict)}
    for opportunity in as_list(semantic_model.get("visualOpportunities")):
        if not isinstance(opportunity, dict):
            continue
        data_ref = clean_text(opportunity.get("dataRef"))
        table = tables.get(data_ref)
        if not table:
            continue
        columns = [clean_text(col.get("key")) for col in as_list(table.get("columns")) if isinstance(col, dict)]
        rows = [row for row in as_list(table.get("rows")) if isinstance(row, dict)]
        if not columns or not rows:
            continue
        x_field = columns[0]
        y_field = ""
        for column in columns[1:]:
            if any(isinstance(row.get(column), (int, float)) for row in rows):
                y_field = column
                break
        if not y_field:
            continue
        chart_type = "line_chart" if looks_temporal_chart_axis(x_field, rows) else clean_text(opportunity.get("type")) or "bar_chart"
        specs.append(
            {
                "chartId": f"chart_{len(specs) + 1}",
                "type": chart_type,
                "title": clean_text(opportunity.get("title"), limit=100) or clean_text(table.get("title"), limit=100) or "图表",
                "dataRef": data_ref,
                "xField": x_field,
                "yField": y_field,
                "sourceMaterialId": clean_text(opportunity.get("sourceMaterialId")),
                "styleTokens": {"palette": "business_cool", "accentColor": "primary"},
            }
        )
    return specs


def enforce_visual_tokens(page: dict[str, Any]) -> dict[str, Any]:
    layout = clean_text(page.get("layout"))
    page["layout"] = layout if layout in APPROVED_LAYOUTS else "title_text"
    style_tokens = page.get("styleTokens") if isinstance(page.get("styleTokens"), dict) else {}
    clean_tokens = {}
    for key, value in style_tokens.items():
        clean_value = clean_text(value)
        if key.endswith("Color") and clean_value not in APPROVED_COLOR_TOKENS:
            continue
        clean_tokens[key] = clean_value
    if clean_tokens:
        page["styleTokens"] = clean_tokens
    return page
