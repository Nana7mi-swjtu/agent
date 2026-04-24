from __future__ import annotations

import base64
import io
from collections import defaultdict
from functools import lru_cache
from typing import Any

from app.analysis_artifacts import (
    build_chart_candidate,
    build_fact_table,
    build_rendered_asset,
    ensure_valid_tabular_artifacts,
    normalize_trace_refs,
)

from .schemas import AnalysisScope, EnterpriseProfile, InsightEvent, RoboticsReaderPacket, SourceDocument

_CJK_FONT_CANDIDATES = (
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "PingFang SC",
    "Heiti SC",
    "Source Han Sans SC",
)


def build_robotics_tabular_artifacts(
    *,
    target_company: dict[str, Any],
    analysis_scope: AnalysisScope,
    profile: EnterpriseProfile,
    reader_packet: RoboticsReaderPacket,
    events: list[InsightEvent],
    sources: list[SourceDocument],
    limitations: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    fact_tables = build_fact_tables(
        target_company=target_company,
        analysis_scope=analysis_scope,
        profile=profile,
        reader_packet=reader_packet,
        events=events,
        sources=sources,
        limitations=limitations,
    )
    chart_candidates = build_chart_candidates(fact_tables)
    rendered_assets = render_chart_assets(chart_candidates, fact_tables)
    ensure_valid_tabular_artifacts(fact_tables, chart_candidates, rendered_assets)
    return fact_tables, chart_candidates, rendered_assets


def build_fact_tables(
    *,
    target_company: dict[str, Any],
    analysis_scope: AnalysisScope,
    profile: EnterpriseProfile,
    reader_packet: RoboticsReaderPacket,
    events: list[InsightEvent],
    sources: list[SourceDocument],
    limitations: list[str],
) -> list[dict[str, Any]]:
    pd = _load_pandas()
    limitation_ids = _limitation_ids(limitations)
    all_source_ids = [item.id for item in sources if item.id]
    all_event_ids = [item.id for item in events if item.id]
    all_signal_ids = [*[_clean_text(item.id) for item in reader_packet.opportunities], *[_clean_text(item.id) for item in reader_packet.risks]]

    snapshot_frame = pd.DataFrame(
        [
            {
                "companyName": _clean_text(target_company.get("name") or profile.name) or "目标企业",
                "stockCode": _clean_text(target_company.get("stockCode") or profile.stock_code) or "-",
                "industry": _clean_text(profile.industry) or "机器人",
                "segments": "、".join(profile.segments[:3]) or "-",
                "timeRange": _clean_text(analysis_scope.time_range) or "-",
                "focus": _clean_text(analysis_scope.focus) or "-",
                "sourceCount": len(sources),
                "eventCount": len(events),
                "opportunityCount": len(reader_packet.opportunities),
                "riskCount": len(reader_packet.risks),
            }
        ]
    )
    enterprise_snapshot = build_fact_table(
        table_id="enterprise_snapshot",
        title="企业概览",
        columns=[
            {"key": "companyName", "label": "企业"},
            {"key": "stockCode", "label": "股票代码"},
            {"key": "industry", "label": "行业"},
            {"key": "segments", "label": "产业链画像"},
            {"key": "timeRange", "label": "时间范围"},
            {"key": "focus", "label": "分析重点"},
            {"key": "sourceCount", "label": "来源数", "kind": "number"},
            {"key": "eventCount", "label": "事件数", "kind": "number"},
            {"key": "opportunityCount", "label": "机会主题数", "kind": "number"},
            {"key": "riskCount", "label": "风险主题数", "kind": "number"},
        ],
        rows=[
            {
                "rowId": "enterprise_snapshot_01",
                "cells": snapshot_frame.to_dict(orient="records")[0],
                "traceRefs": {
                    "sourceIds": all_source_ids,
                    "eventIds": all_event_ids,
                    "signalIds": all_signal_ids,
                    "limitationIds": limitation_ids,
                },
            }
        ],
        trace_refs={
            "sourceIds": all_source_ids,
            "eventIds": all_event_ids,
            "signalIds": all_signal_ids,
            "limitationIds": limitation_ids,
        },
    )

    opportunity_themes = _build_theme_table(
        table_id="opportunity_themes",
        title="机会主题",
        themes=reader_packet.opportunities,
        empty_message="未形成可支撑的机会主题，当前仅保留快照和限制说明。",
        limitation_ids=limitation_ids,
    )
    risk_themes = _build_theme_table(
        table_id="risk_themes",
        title="风险主题",
        themes=reader_packet.risks,
        empty_message="未形成可支撑的风险主题，当前仅保留快照和限制说明。",
        limitation_ids=limitation_ids,
    )

    evidence_rows = [
        {
            "rowId": item.id,
            "cells": {
                "title": item.title,
                "sourceType": item.source_type,
                "sourceName": item.source_name,
                "publishedAt": item.published_at or "-",
                "verificationStatus": item.verification_status,
                "readerSummary": item.reader_summary,
            },
            "traceRefs": {
                "sourceIds": list(item.source_ids),
                "eventIds": list(item.event_ids),
            },
        }
        for item in reader_packet.evidence_references
    ]
    evidence_references = build_fact_table(
        table_id="evidence_references",
        title="证据引用",
        columns=[
            {"key": "title", "label": "来源标题"},
            {"key": "sourceType", "label": "来源类型"},
            {"key": "sourceName", "label": "来源名称"},
            {"key": "publishedAt", "label": "发布时间"},
            {"key": "verificationStatus", "label": "核验状态"},
            {"key": "readerSummary", "label": "摘要"},
        ],
        rows=evidence_rows or [
            _empty_state_row(
                "evidence_references",
                {
                    "title": "暂无可引用证据",
                    "sourceType": "empty",
                    "sourceName": "-",
                    "publishedAt": "-",
                    "verificationStatus": "当前未采集到可引用来源。",
                    "readerSummary": "后续需补充政策、公告或招投标来源后再生成证据表。",
                },
                limitation_ids=limitation_ids,
            )
        ],
        empty_text="暂无可引用证据。",
        trace_refs={"sourceIds": all_source_ids, "eventIds": all_event_ids},
    )

    event_frame = pd.DataFrame(
        [
            {
                "rowId": item.id,
                "publishedAt": _clean_text(item.published_at),
                "direction": _clean_text(item.direction),
                "dimension": _clean_text(item.dimension),
                "title": _clean_text(item.title),
                "summary": _clean_text(item.summary),
                "sourceType": _clean_text(item.source_type),
                "sourceId": _clean_text(item.source_document_id),
            }
            for item in events
        ]
    )
    if not event_frame.empty:
        event_frame["publishedAtSort"] = pd.to_datetime(event_frame["publishedAt"], errors="coerce")
        event_frame = event_frame.sort_values(by=["publishedAtSort", "title"], ascending=[True, True], na_position="last")
    event_rows = [
        {
            "rowId": _clean_text(record.get("rowId")) or f"event_timeline_{index:02d}",
            "cells": {
                "publishedAt": _clean_text(record.get("publishedAt")) or "-",
                "direction": _clean_text(record.get("direction")) or "-",
                "dimension": _clean_text(record.get("dimension")) or "-",
                "title": _clean_text(record.get("title")) or "事件",
                "summary": _clean_text(record.get("summary")),
                "sourceType": _clean_text(record.get("sourceType")) or "-",
            },
            "traceRefs": {
                "sourceIds": [_clean_text(record.get("sourceId"))] if _clean_text(record.get("sourceId")) else [],
                "eventIds": [_clean_text(record.get("rowId"))] if _clean_text(record.get("rowId")) else [],
            },
        }
        for index, record in enumerate(event_frame.to_dict(orient="records") if not event_frame.empty else [], start=1)
    ]
    event_timeline = build_fact_table(
        table_id="event_timeline",
        title="事件时间线",
        columns=[
            {"key": "publishedAt", "label": "时间"},
            {"key": "direction", "label": "方向"},
            {"key": "dimension", "label": "维度"},
            {"key": "title", "label": "事件"},
            {"key": "summary", "label": "摘要"},
            {"key": "sourceType", "label": "来源类型"},
        ],
        rows=event_rows
        or [
            _empty_state_row(
                "event_timeline",
                {
                    "publishedAt": "-",
                    "direction": "-",
                    "dimension": "-",
                    "title": "暂无明确事件时间线",
                    "summary": "当前没有可用于编排时间线的结构化事件。",
                    "sourceType": "empty",
                },
                limitation_ids=limitation_ids,
            )
        ],
        empty_text="暂无明确事件时间线。",
        trace_refs={"sourceIds": all_source_ids, "eventIds": all_event_ids},
    )

    source_frame = pd.DataFrame(
        [
            {
                "sourceType": _clean_text(item.source_type) or "unknown",
                "relevanceScope": _clean_text(item.relevance_scope) or "unknown",
                "sourceId": _clean_text(item.id),
            }
            for item in sources
        ]
    )
    if not source_frame.empty:
        grouped_source_frame = (
            source_frame.groupby(["sourceType", "relevanceScope"], dropna=False)
            .agg(documentCount=("sourceId", "count"), sourceIds=("sourceId", lambda values: [item for item in values if item]))
            .reset_index()
            .sort_values(by=["documentCount", "sourceType"], ascending=[False, True])
        )
    else:
        grouped_source_frame = pd.DataFrame()
    composition_rows = [
        {
            "rowId": f"source_comp_{index:02d}",
            "cells": {
                "sourceType": _clean_text(record.get("sourceType")) or "unknown",
                "relevanceScope": _clean_text(record.get("relevanceScope")) or "unknown",
                "documentCount": int(record.get("documentCount") or 0),
            },
            "traceRefs": {
                "sourceIds": _string_list(record.get("sourceIds")),
            },
        }
        for index, record in enumerate(grouped_source_frame.to_dict(orient="records") if not grouped_source_frame.empty else [], start=1)
    ]
    source_composition = build_fact_table(
        table_id="source_composition",
        title="来源构成",
        columns=[
            {"key": "sourceType", "label": "来源类型"},
            {"key": "relevanceScope", "label": "相关范围"},
            {"key": "documentCount", "label": "文档数", "kind": "number"},
        ],
        rows=composition_rows
        or [
            _empty_state_row(
                "source_composition",
                {
                    "sourceType": "empty",
                    "relevanceScope": "-",
                    "documentCount": 0,
                },
                limitation_ids=limitation_ids,
            )
        ],
        empty_text="暂无来源构成数据。",
        trace_refs={"sourceIds": all_source_ids},
    )

    return [
        enterprise_snapshot,
        opportunity_themes,
        risk_themes,
        evidence_references,
        event_timeline,
        source_composition,
    ]


def build_chart_candidates(fact_tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table_map = {_clean_text(item.get("tableId")): item for item in fact_tables if isinstance(item, dict)}
    candidates: list[dict[str, Any]] = []
    candidates.extend(
        _build_ranking_chart_candidates(
            table_map.get("opportunity_themes"),
            chart_id="chart_opportunity_theme_strength",
            title="机会主题强度分布",
            caption="比较当前机会主题的相对强弱，帮助先看主线再看细节。",
        )
    )
    candidates.extend(
        _build_ranking_chart_candidates(
            table_map.get("risk_themes"),
            chart_id="chart_risk_theme_strength",
            title="风险主题强度分布",
            caption="比较当前风险主题的相对强弱，避免把相近风险拆成重复长句。",
        )
    )
    source_table = table_map.get("source_composition")
    if source_table:
        series = []
        for row in _substantive_rows(source_table):
            label = _cell_text(row, "sourceType")
            value = _numeric_cell(row, "documentCount")
            if label and value is not None:
                series.append({"label": label, "value": value, "rowId": _clean_text(row.get("rowId"))})
        if series:
            candidates.append(
                build_chart_candidate(
                    chart_id="chart_source_composition",
                    source_table_id="source_composition",
                    chart_type="donut",
                    title="证据来源构成",
                    series=series,
                    caption="展示本轮判断主要来自哪些来源类型，用于帮助理解证据覆盖面。",
                    interpretation_boundary="来源数量反映覆盖面，不单独代表证据质量高低。",
                    eligibility={"minRows": 1, "rowCount": len(series)},
                    fallback_table_id="source_composition",
                    trace_refs=_aggregate_table_trace_refs(source_table),
                )
            )
    timeline_table = table_map.get("event_timeline")
    if timeline_table:
        series = []
        for index, row in enumerate(_substantive_rows(timeline_table), start=1):
            label = _cell_text(row, "title")
            event_date = _cell_text(row, "publishedAt")
            if label:
                series.append(
                    {
                        "label": label,
                        "value": index,
                        "date": event_date,
                        "summary": _cell_text(row, "summary"),
                        "rowId": _clean_text(row.get("rowId")),
                    }
                )
        if series:
            candidates.append(
                build_chart_candidate(
                    chart_id="chart_event_timeline",
                    source_table_id="event_timeline",
                    chart_type="timeline",
                    title="事件时间线",
                    series=series,
                    caption="按时间排列主要事件，帮助快速识别节奏变化。",
                    interpretation_boundary="时间线仅反映已采集事件，不代表全部经营活动或事件权重。",
                    eligibility={"minRows": 1, "rowCount": len(series)},
                    fallback_table_id="event_timeline",
                    trace_refs=_aggregate_table_trace_refs(timeline_table),
                )
            )
    return candidates


def render_chart_assets(
    chart_candidates: list[dict[str, Any]],
    fact_tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    table_map = {_clean_text(item.get("tableId")): item for item in fact_tables if isinstance(item, dict)}
    assets: list[dict[str, Any]] = []
    for candidate in chart_candidates:
        if not isinstance(candidate, dict):
            continue
        chart_id = _clean_text(candidate.get("chartId"))
        source_table_id = _clean_text(candidate.get("sourceTableId"))
        image_data_url = _render_chart_data_url(candidate, table_map.get(source_table_id))
        if not image_data_url:
            continue
        assets.append(
            build_rendered_asset(
                asset_id=f"asset_{chart_id}",
                chart_id=chart_id,
                source_table_id=source_table_id,
                title=_clean_text(candidate.get("title")) or "图表资产",
                content_type="image/png",
                alt_text=_clean_text(candidate.get("title")) or "图表",
                caption=_clean_text(candidate.get("caption")),
                interpretation_boundary=_clean_text(candidate.get("interpretationBoundary")),
                render_payload={
                    "dataUrl": image_data_url,
                    "chartType": _clean_text(candidate.get("chartType")),
                    "fallbackTableId": _clean_text(candidate.get("fallbackTableId") or source_table_id),
                },
                trace_refs=normalize_trace_refs(candidate.get("traceRefs")),
            )
        )
    return assets


def _build_theme_table(
    *,
    table_id: str,
    title: str,
    themes: list[Any],
    empty_message: str,
    limitation_ids: list[str],
) -> dict[str, Any]:
    pd = _load_pandas()
    frame = pd.DataFrame(
        [
            {
                "rowId": _clean_text(item.id),
                "theme": _clean_text(item.title),
                "impactScore": int(item.impact_score or 0),
                "confidence": round(float(item.confidence or 0), 2),
                "evidenceCount": len(item.source_ids),
                "categories": "、".join(item.categories),
                "summary": _clean_text(item.summary),
                "basisSummary": _clean_text(item.basis_summary),
                "interpretationBoundary": _clean_text(item.interpretation_boundary),
                "sourceIds": list(item.source_ids),
                "eventIds": list(item.event_ids),
                "signalIds": list(item.signal_ids),
            }
            for item in themes
        ]
    )
    if not frame.empty:
        frame = frame.sort_values(by=["impactScore", "confidence", "theme"], ascending=[False, False, True])
    rows = [
        {
            "rowId": _clean_text(record.get("rowId")) or f"{table_id}_{index:02d}",
            "cells": {
                "theme": _clean_text(record.get("theme")),
                "impactScore": int(record.get("impactScore") or 0),
                "confidence": float(record.get("confidence") or 0),
                "evidenceCount": int(record.get("evidenceCount") or 0),
                "categories": _clean_text(record.get("categories")),
                "summary": _clean_text(record.get("summary")),
                "basisSummary": _clean_text(record.get("basisSummary")),
            },
            "traceRefs": {
                "sourceIds": _string_list(record.get("sourceIds")),
                "eventIds": _string_list(record.get("eventIds")),
                "signalIds": _string_list(record.get("signalIds")),
            },
            "summary": _clean_text(record.get("interpretationBoundary")),
        }
        for index, record in enumerate(frame.to_dict(orient="records") if not frame.empty else [], start=1)
    ]
    aggregate_trace_refs = {
        "sourceIds": _dedupe(source_id for item in themes for source_id in list(item.source_ids)),
        "eventIds": _dedupe(event_id for item in themes for event_id in list(item.event_ids)),
        "signalIds": _dedupe(signal_id for item in themes for signal_id in list(item.signal_ids)),
    }
    return build_fact_table(
        table_id=table_id,
        title=title,
        columns=[
            {"key": "theme", "label": "主题"},
            {"key": "impactScore", "label": "影响分", "kind": "number"},
            {"key": "confidence", "label": "置信度", "kind": "number"},
            {"key": "evidenceCount", "label": "证据数", "kind": "number"},
            {"key": "categories", "label": "归并维度"},
            {"key": "summary", "label": "主题解读"},
            {"key": "basisSummary", "label": "依据边界"},
        ],
        rows=rows
        or [
            _empty_state_row(
                table_id,
                {
                    "theme": f"暂无{title}",
                    "impactScore": 0,
                    "confidence": 0,
                    "evidenceCount": 0,
                    "categories": "-",
                    "summary": empty_message,
                    "basisSummary": "当前没有足够证据支持该主题进入正式表格。",
                },
                limitation_ids=limitation_ids,
            )
        ],
        empty_text=empty_message,
        trace_refs=aggregate_trace_refs,
    )


def _build_ranking_chart_candidates(
    table: dict[str, Any] | None,
    *,
    chart_id: str,
    title: str,
    caption: str,
) -> list[dict[str, Any]]:
    if not isinstance(table, dict):
        return []
    series = []
    for row in _substantive_rows(table)[:6]:
        label = _cell_text(row, "theme")
        value = _numeric_cell(row, "impactScore")
        if label and value is not None:
            series.append({"label": label, "value": value, "rowId": _clean_text(row.get("rowId"))})
    if not series:
        return []
    return [
        build_chart_candidate(
            chart_id=chart_id,
            source_table_id=_clean_text(table.get("tableId")),
            chart_type="bar",
            title=title,
            series=series,
            caption=caption,
            interpretation_boundary="图中分值仅用于相对排序，不等同于精确预测或结果保证。",
            eligibility={"minRows": 1, "maxRows": 6, "rowCount": len(series)},
            fallback_table_id=_clean_text(table.get("tableId")),
            trace_refs=_aggregate_table_trace_refs(table),
        )
    ]


def _render_chart_data_url(candidate: dict[str, Any], table: dict[str, Any] | None) -> str:
    chart_type = _clean_text(candidate.get("chartType")).lower()
    if chart_type == "bar":
        image_bytes = _render_bar_chart(candidate)
    elif chart_type == "donut":
        image_bytes = _render_donut_chart(candidate)
    elif chart_type == "timeline":
        image_bytes = _render_timeline_chart(candidate, table)
    else:
        image_bytes = b""
    if not image_bytes:
        return ""
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _render_bar_chart(candidate: dict[str, Any]) -> bytes:
    series = [item for item in candidate.get("series", []) if isinstance(item, dict)]
    if not series:
        return b""
    runtime = _load_plot_runtime()
    plt = runtime["plt"]
    labels = [str(item.get("label") or "") for item in reversed(series)]
    values = [float(item.get("value") or 0) for item in reversed(series)]
    colors = ["#0f766e", "#14b8a6", "#0ea5e9", "#2563eb", "#22c55e", "#84cc16"][: len(values)]
    fig = plt.figure(figsize=(8.6, 4.8))
    ax = fig.add_subplot(111)
    ax.barh(labels, values, color=colors)
    ax.set_title(_clean_text(candidate.get("title")) or "图表")
    ax.set_xlabel("相对强度")
    ax.grid(axis="x", linestyle="--", alpha=0.25)
    fig.tight_layout()
    return _figure_to_png_bytes(fig, plt)


def _render_donut_chart(candidate: dict[str, Any]) -> bytes:
    series = [item for item in candidate.get("series", []) if isinstance(item, dict)]
    if not series:
        return b""
    runtime = _load_plot_runtime()
    plt = runtime["plt"]
    labels = [str(item.get("label") or "") for item in series]
    values = [float(item.get("value") or 0) for item in series]
    fig = plt.figure(figsize=(6.4, 4.8))
    ax = fig.add_subplot(111)
    colors = ["#0f766e", "#14b8a6", "#0ea5e9", "#2563eb", "#22c55e", "#84cc16"][: len(values)]
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct="%1.0f",
        startangle=90,
        colors=colors,
        wedgeprops={"width": 0.45, "edgecolor": "white"},
    )
    for text in [*texts, *autotexts]:
        text.set_fontsize(9)
    ax.set_title(_clean_text(candidate.get("title")) or "图表")
    fig.tight_layout()
    return _figure_to_png_bytes(fig, plt)


def _render_timeline_chart(candidate: dict[str, Any], table: dict[str, Any] | None) -> bytes:
    series = [item for item in candidate.get("series", []) if isinstance(item, dict)]
    if not series:
        return b""
    runtime = _load_plot_runtime()
    plt = runtime["plt"]
    mdates = runtime["mdates"]
    fig = plt.figure(figsize=(8.8, 4.8))
    ax = fig.add_subplot(111)
    dates = []
    labels = []
    y_values = []
    for index, item in enumerate(series, start=1):
        dates.append(_parse_datetime(item.get("date")))
        labels.append(str(item.get("label") or f"事件{index}"))
        y_values.append(index)
    ax.plot(dates, y_values, color="#0f766e", linewidth=1.5, marker="o")
    for dt, y_value, label in zip(dates, y_values, labels):
        ax.annotate(label, (dt, y_value), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)
    ax.set_title(_clean_text(candidate.get("title")) or "事件时间线")
    ax.set_ylabel("事件序列")
    ax.grid(axis="x", linestyle="--", alpha=0.25)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate(rotation=25)
    fig.tight_layout()
    return _figure_to_png_bytes(fig, plt)


def _figure_to_png_bytes(figure: Any, plt: Any) -> bytes:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=220, bbox_inches="tight")
    plt.close(figure)
    return buffer.getvalue()


@lru_cache(maxsize=1)
def _load_pandas() -> Any:
    import pandas as pd

    return pd


@lru_cache(maxsize=1)
def _load_plot_runtime() -> dict[str, Any]:
    import matplotlib

    matplotlib.use("Agg")
    _configure_matplotlib_fonts(matplotlib)
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    return {"plt": plt, "mdates": mdates}


def _configure_matplotlib_fonts(matplotlib: Any) -> None:
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    cjk_fonts = [name for name in _CJK_FONT_CANDIDATES if name in available]
    if cjk_fonts:
        matplotlib.rcParams["font.family"] = "sans-serif"
        matplotlib.rcParams["font.sans-serif"] = [*cjk_fonts, *matplotlib.rcParams.get("font.sans-serif", [])]
    matplotlib.rcParams["axes.unicode_minus"] = False


def _substantive_rows(table: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in table.get("rows", []) if isinstance(table.get("rows"), list) else []:
        if not isinstance(row, dict) or bool(row.get("emptyState")):
            continue
        cells = row.get("cells") if isinstance(row.get("cells"), dict) else {}
        if any(value not in (None, "", [], {}) for value in cells.values()):
            rows.append(row)
    return rows


def _aggregate_table_trace_refs(table: dict[str, Any]) -> dict[str, list[str]]:
    refs = normalize_trace_refs(table.get("traceRefs"))
    rows = table.get("rows", []) if isinstance(table.get("rows"), list) else []
    buckets: dict[str, list[str]] = defaultdict(list)
    for key, values in refs.items():
        buckets[key].extend(values)
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_refs = normalize_trace_refs(row.get("traceRefs"))
        for key, values in row_refs.items():
            buckets[key].extend(values)
    return {key: _dedupe(values) for key, values in buckets.items() if _dedupe(values)}


def _empty_state_row(table_id: str, cells: dict[str, Any], *, limitation_ids: list[str]) -> dict[str, Any]:
    return {
        "rowId": f"{table_id}_empty",
        "cells": cells,
        "traceRefs": {"limitationIds": list(limitation_ids)},
        "emptyState": True,
    }


def _cell_text(row: dict[str, Any], key: str) -> str:
    cells = row.get("cells") if isinstance(row.get("cells"), dict) else {}
    return _clean_text(cells.get(key))


def _numeric_cell(row: dict[str, Any], key: str) -> float | None:
    cells = row.get("cells") if isinstance(row.get("cells"), dict) else {}
    value = cells.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _limitation_ids(limitations: list[str]) -> list[str]:
    return [f"limitation_{index:02d}" for index, item in enumerate(limitations, start=1) if _clean_text(item)]


def _parse_datetime(value: Any):
    from datetime import datetime

    text = _clean_text(value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime(1970, 1, 1)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return _dedupe(value)
    return []


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _clean_text(value)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _clean_text(value: Any) -> str:
    return str(value or "").strip()
