from __future__ import annotations

from typing import Any

from .contracts import as_list, clean_text
from .visual_planning import build_chart_specs, enforce_visual_tokens

MAX_ITEMS_PER_PAGE = 5
MAX_TABLE_ROWS_PER_PAGE = 8


def _block(block_type: str, **kwargs: Any) -> dict[str, Any]:
    return {"type": block_type, **{key: value for key, value in kwargs.items() if value not in (None, "", [], {})}}


def _items_from_findings(findings: list[dict[str, Any]], *, limit: int = MAX_ITEMS_PER_PAGE) -> list[dict[str, Any]]:
    items = []
    for finding in findings[:limit]:
        items.append(
            {
                "title": clean_text(finding.get("title"), limit=80) or "关键发现",
                "summary": clean_text(finding.get("summary"), limit=220),
                "evidenceRefs": as_list(finding.get("evidenceRefs")),
            }
        )
    return items


def _toc_items(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": clean_text(page.get("id")),
            "title": clean_text(page.get("title")),
            "pageNumber": page.get("pageNumber"),
        }
        for page in pages
        if page.get("tocEntry") and clean_text(page.get("title"))
    ]


def plan_pages(*, title: str, semantic_model: dict[str, Any], render_profile: dict[str, Any]) -> dict[str, Any]:
    findings = [item for item in as_list(semantic_model.get("findings")) if isinstance(item, dict)]
    metrics = [item for item in as_list(semantic_model.get("metrics")) if isinstance(item, dict)]
    tables = [item for item in as_list(semantic_model.get("tables")) if isinstance(item, dict)]
    evidence_refs = [item for item in as_list(semantic_model.get("evidenceRefs")) if isinstance(item, dict)]
    chart_specs = build_chart_specs(semantic_model)
    pages: list[dict[str, Any]] = [
        {
            "id": "page_cover",
            "pageNumber": 1,
            "pageType": "cover",
            "type": "cover",
            "title": "封面",
            "tocEntry": False,
            "layout": "cover",
            "blocks": [_block("hero", title=title)],
            "styleTokens": {"accentColor": "primary"},
        }
    ]
    body_pages: list[dict[str, Any]] = []
    summary_blocks = []
    summary_items = _items_from_findings(findings, limit=4)
    summary_blocks.append(
        _block(
            "items",
            title="核心摘要",
            items=summary_items or [{"title": "材料覆盖", "summary": "已接收材料，但可支撑的关键结论有限。"}],
        )
    )
    body_pages.append(
        {
            "id": "page_summary",
            "pageType": "executive_summary",
            "type": "body",
            "title": "执行摘要",
            "tocEntry": True,
            "layout": "title_text",
            "blocks": summary_blocks,
            "evidenceRefs": sorted({ref for item in summary_items for ref in as_list(item.get("evidenceRefs"))}),
            "styleTokens": {"accentColor": "primary"},
        }
    )
    remaining_findings = findings[4:]
    if remaining_findings:
        body_pages.append(
            {
                "id": "page_insights",
                "pageType": "insight",
                "type": "body",
                "title": "关键发现",
                "tocEntry": True,
                "layout": "title_text",
                "blocks": [_block("items", title="发现列表", items=_items_from_findings(remaining_findings, limit=MAX_ITEMS_PER_PAGE))],
                "evidenceRefs": sorted({ref for item in _items_from_findings(remaining_findings) for ref in as_list(item.get("evidenceRefs"))}),
                "styleTokens": {"accentColor": "accent"},
            }
        )
    for index, chart in enumerate(chart_specs[:3], start=1):
        body_pages.append(
            {
                "id": f"page_chart_{index}",
                "pageType": "chart_analysis",
                "type": "body",
                "title": clean_text(chart.get("title"), limit=80) or f"图表分析 {index}",
                "tocEntry": True,
                "layout": "title_chart_notes",
                "blocks": [
                    _block("chart", chartId=chart.get("chartId"), title=chart.get("title"), chartSpec=chart),
                    _block("paragraph", text="该图表用于帮助读者快速理解输入材料中的趋势变化与结构对比。"),
                ],
                "evidenceRefs": [f"evidence_{clean_text(chart.get('sourceMaterialId'))}_1"],
                "styleTokens": {"accentColor": "primary"},
            }
        )
    for index, table in enumerate(tables[:2], start=1):
        rows = as_list(table.get("rows"))
        displayed_table = {**table, "rows": rows[:MAX_TABLE_ROWS_PER_PAGE]}
        moved = len(rows) > MAX_TABLE_ROWS_PER_PAGE
        body_pages.append(
            {
                "id": f"page_table_{index}",
                "pageType": "table_analysis",
                "type": "body",
                "title": clean_text(table.get("title"), limit=80) or f"数据表 {index}",
                "tocEntry": True,
                "layout": "title_table_notes",
                "blocks": [
                    _block("table_block", title=table.get("title"), table=displayed_table),
                    *([_block("callout", title="表格已截断", text="完整数据较长，超出分页容量的行应进入附录或原始材料。")] if moved else []),
                ],
                "evidenceRefs": [f"evidence_{clean_text(table.get('sourceMaterialId'))}_1"],
                "styleTokens": {"accentColor": "accent"},
            }
        )
    body_pages.append(
        {
            "id": "page_recommendation",
            "pageType": "recommendation",
            "type": "body",
            "title": "建议与行动",
            "tocEntry": True,
            "layout": "title_text",
            "blocks": [
                _block("items", title="使用建议", items=[{"title": "优先复核关键结论", "summary": "对报告中的重要判断，应结合原始材料、业务上下文和后续数据变化持续复核。"}]),
            ],
            "styleTokens": {"accentColor": "success"},
        }
    )
    for offset, page in enumerate(body_pages, start=3):
        page["pageNumber"] = offset
        enforce_visual_tokens(page)
    toc_page = {
        "id": "page_toc",
        "pageNumber": 2,
        "pageType": "table_of_contents",
        "type": "table_of_contents",
        "title": "目录",
        "tocEntry": False,
        "layout": "toc",
        "items": _toc_items(body_pages),
    }
    pages.append(toc_page)
    pages.extend(body_pages)
    return {"pages": pages, "chartSpecs": chart_specs}
