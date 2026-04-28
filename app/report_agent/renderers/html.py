from __future__ import annotations

import html
from typing import Any

from ..contracts import as_dict, as_list, clean_text

SCREEN_TARGET = "html"
PDF_TARGET = "pdf"

PAGE_KICKERS = {
    "cover": "正式分析报告",
    "table_of_contents": "目录",
    "executive_summary": "执行摘要",
    "insight": "关键发现",
    "chart_analysis": "图表",
    "table_analysis": "数据表",
    "evidence": "证据与来源",
    "recommendation": "建议与行动",
    "appendix": "边界说明",
}

DEFAULT_TOKEN_BY_PAGE = {
    "cover": "primary",
    "table_of_contents": "muted",
    "executive_summary": "primary",
    "insight": "accent",
    "chart_analysis": "primary",
    "table_analysis": "primary",
    "evidence": "muted",
    "recommendation": "success",
    "appendix": "warning",
}

TOKEN_COLORS = {
    "primary": {"accent": "#1D4ED8", "soft": "#EAF1FF", "panel": "#F7FAFF", "line": "#C8D8FF", "deep": "#0F3D99"},
    "accent": {"accent": "#14B8A6", "soft": "#E8FBF7", "panel": "#F5FEFC", "line": "#BDEEE8", "deep": "#0F766E"},
    "success": {"accent": "#16A34A", "soft": "#ECFDF3", "panel": "#F7FEF9", "line": "#BCECCB", "deep": "#166534"},
    "warning": {"accent": "#D97706", "soft": "#FFF6E8", "panel": "#FFFBF2", "line": "#F4D3A4", "deep": "#9A580A"},
    "danger": {"accent": "#DC2626", "soft": "#FFF1F1", "panel": "#FFF8F8", "line": "#F2C4C4", "deep": "#991B1B"},
    "muted": {"accent": "#64748B", "soft": "#F3F6FA", "panel": "#FAFBFC", "line": "#D5DFEA", "deep": "#334155"},
}


def _text(value: Any) -> str:
    return html.escape(clean_text(value))


def _folio(value: Any) -> str:
    text = clean_text(value)
    if text.isdigit():
        return f"{int(text):02d}"
    return text


def _font_stack(bundle: dict[str, Any]) -> str:
    profile = as_dict(bundle.get("renderProfile"))
    family = as_dict(profile.get("fontFamily"))
    names = []
    for item in [family.get("body"), *as_list(family.get("fallback"))]:
        text = clean_text(item)
        if text and text not in names:
            names.append(text)
    if not names:
        names = ["Noto Sans CJK SC", "Microsoft YaHei", "Arial"]
    return ",".join(f"'{item}'" if " " in item else item for item in names)


def _table_lookup(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    semantic_model = as_dict(bundle.get("semanticModel"))
    return {
        clean_text(item.get("tableId")): item
        for item in as_list(semantic_model.get("tables"))
        if isinstance(item, dict) and clean_text(item.get("tableId"))
    }


def _sample_chart_rows(rows: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return rows
    sampled: list[dict[str, Any]] = []
    last_index = -1
    for slot in range(limit):
        index = round(slot * (len(rows) - 1) / max(1, limit - 1))
        if index == last_index:
            continue
        sampled.append(rows[index])
        last_index = index
    return sampled


def _page_theme(page: dict[str, Any], palette: dict[str, Any]) -> dict[str, str]:
    page_type = clean_text(page.get("pageType") or page.get("type")).lower() or "insight"
    style_tokens = as_dict(page.get("styleTokens"))
    default_token = DEFAULT_TOKEN_BY_PAGE.get(page_type, "primary")
    token = clean_text(style_tokens.get("accentColor")).lower()
    if not token or (token == "primary" and default_token != "primary"):
        token = default_token
    base = TOKEN_COLORS.get(token, TOKEN_COLORS["primary"]).copy()
    accent = clean_text(palette.get(token))
    if accent:
        base["accent"] = accent
    base["token"] = token
    base["pageType"] = page_type
    base["kicker"] = PAGE_KICKERS.get(page_type, "Report Page")
    return base


def _chart_svg(chart_spec: dict[str, Any], *, table_lookup: dict[str, dict[str, Any]], theme: dict[str, str]) -> str:
    table = table_lookup.get(clean_text(chart_spec.get("dataRef")))
    if not isinstance(table, dict):
        return "<div class='chart-empty'>缺少图表数据。</div>"
    rows = _sample_chart_rows([row for row in as_list(table.get("rows")) if isinstance(row, dict)], limit=12)
    x_field = clean_text(chart_spec.get("xField"))
    y_field = clean_text(chart_spec.get("yField"))
    points: list[tuple[str, float]] = []
    for row in rows:
        try:
            numeric = float(row.get(y_field))
        except (TypeError, ValueError):
            continue
        points.append((clean_text(row.get(x_field), limit=16), numeric))
    if not points:
        return "<div class='chart-empty'>图表数据不足。</div>"

    width = 640
    height = 290
    left = 58
    top = 28
    bottom = 228
    usable_width = 538
    usable_height = 160
    grid_color = theme["line"]
    color = theme["accent"]
    deep = theme["deep"]
    chart_fill = "#FFFFFF"
    max_value = max(value for _, value in points) or 1.0
    chart_type = clean_text(chart_spec.get("type")).lower()
    step = usable_width / max(1, len(points))

    svg_parts = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{_text(chart_spec.get('title'))}'>",
        f"<rect x='1' y='1' width='{width - 2}' height='{height - 2}' rx='18' fill='{chart_fill}' stroke='{grid_color}' stroke-width='1.4'/>",
    ]
    for index in range(5):
        y = top + (usable_height / 4) * index
        svg_parts.append(
            f"<line x1='{left}' y1='{y:.1f}' x2='{left + usable_width}' y2='{y:.1f}' stroke='{grid_color}' stroke-width='1' stroke-dasharray='4 5'/>"
        )
    svg_parts.append(
        f"<line x1='{left}' y1='{bottom}' x2='{left + usable_width}' y2='{bottom}' stroke='{deep}' stroke-width='1.3'/>"
    )
    svg_parts.append(f"<line x1='{left}' y1='{top}' x2='{left}' y2='{bottom}' stroke='{deep}' stroke-width='1.3'/>")

    if chart_type in {"line_chart", "line", "trend"}:
        polyline: list[str] = []
        area_points: list[str] = [f"{left},{bottom}"]
        for index, (label, value) in enumerate(points):
            x = left + step * index + step / 2
            y = bottom - (value / max_value) * usable_height
            polyline.append(f"{x:.1f},{y:.1f}")
            area_points.append(f"{x:.1f},{y:.1f}")
            svg_parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='4.8' fill='{color}' stroke='white' stroke-width='2'/>")
            svg_parts.append(f"<text x='{x:.1f}' y='{bottom + 18}' text-anchor='middle' font-size='11' fill='{deep}'>{html.escape(label)}</text>")
            svg_parts.append(f"<text x='{x:.1f}' y='{y - 9:.1f}' text-anchor='middle' font-size='11' fill='{deep}'>{value:g}</text>")
        area_points.append(f"{left + step * (len(points) - 1) + step / 2:.1f},{bottom}")
        svg_parts.append(
            f"<polyline points='{' '.join(polyline)}' fill='none' stroke='{color}' stroke-width='3.8' stroke-linecap='round' stroke-linejoin='round'/>"
        )
    else:
        bar_width = min(44, step * 0.56)
        for index, (label, value) in enumerate(points):
            x = left + step * index + (step - bar_width) / 2
            height_value = (value / max_value) * usable_height
            y = bottom - height_value
            svg_parts.append(
                f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_width:.1f}' height='{height_value:.1f}' rx='10' fill='{color}' opacity='0.95'/>"
            )
            svg_parts.append(f"<text x='{x + bar_width / 2:.1f}' y='{bottom + 18}' text-anchor='middle' font-size='11' fill='{deep}'>{html.escape(label)}</text>")
            svg_parts.append(f"<text x='{x + bar_width / 2:.1f}' y='{y - 8:.1f}' text-anchor='middle' font-size='11' fill='{deep}'>{value:g}</text>")
    svg_parts.append("</svg>")
    return "".join(svg_parts)


def _panel_style(theme: dict[str, str]) -> str:
    return f"border-color:{theme['line']};background:{theme['panel']};"


def _chinese_section_number(value: int) -> str:
    digits = {0: "零", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
    if value <= 10:
        return digits.get(value, str(value))
    if value < 20:
        return "十" + digits.get(value % 10, "")
    tens, ones = divmod(value, 10)
    prefix = digits.get(tens, str(tens)) + "十"
    return prefix + (digits.get(ones, "") if ones else "")


def _numbered_title(index: int, title: Any) -> str:
    text = clean_text(title)
    if not text:
        return ""
    return f"{_chinese_section_number(index)}、{text}"


def _bundle_toc_index_map(bundle: dict[str, Any]) -> dict[str, int]:
    for page in as_list(bundle.get("pages")):
        if not isinstance(page, dict):
            continue
        if clean_text(page.get("pageType") or page.get("type")).lower() != "table_of_contents":
            continue
        items = [item for item in as_list(page.get("items")) if isinstance(item, dict)]
        return {clean_text(item.get("id")): index for index, item in enumerate(items, start=1) if clean_text(item.get("id"))}
    return {}


def _page_display_title(page: dict[str, Any], *, toc_index_map: dict[str, int]) -> str:
    page_id = clean_text(page.get("id"))
    title = clean_text(page.get("tocTitle") or page.get("title"))
    index = toc_index_map.get(page_id)
    if index and title:
        return _numbered_title(index, title)
    return title


def _section_label_html(title: Any, *, theme: dict[str, str]) -> str:
    text = clean_text(title)
    if not text:
        return ""
    return f"<div class='report-panel-title' style='color:{theme['deep']};'>{_text(text)}</div>"


def _meta_grid_html(items: list[dict[str, Any]], *, target: str, theme: dict[str, str]) -> str:
    if not items:
        return ""
    if target == PDF_TARGET:
        rows = []
        pairs = [items[index : index + 2] for index in range(0, len(items), 2)]
        for pair in pairs:
            left = pair[0]
            right = pair[1] if len(pair) > 1 else {}
            rows.append(
                "<tr>"
                + _meta_grid_cell_html(left, theme=theme)
                + _meta_grid_cell_html(right, theme=theme)
                + "</tr>"
            )
        return f"<table class='report-meta-table'>{''.join(rows)}</table>"
    cells = "".join(
        f"<li class='report-meta-card'><span>{_text(item.get('label'))}</span><strong>{_text(item.get('value'))}</strong></li>"
        for item in items
        if isinstance(item, dict)
    )
    return f"<ul class='report-meta-grid'>{cells}</ul>"


def _meta_grid_cell_html(item: dict[str, Any], *, theme: dict[str, str]) -> str:
    if not isinstance(item, dict) or not clean_text(item.get("label")):
        return "<td class='report-meta-cell report-meta-cell-empty'></td>"
    return (
        "<td class='report-meta-cell'>"
        f"<div class='report-meta-label' style='color:{theme['deep']};'>{_text(item.get('label'))}</div>"
        f"<div class='report-meta-value'>{_text(item.get('value'))}</div>"
        "</td>"
    )


def _items_html(
    items: list[dict[str, Any]],
    *,
    title: Any,
    target: str,
    theme: dict[str, str],
    list_class: str,
) -> str:
    valid_items = [item for item in items if isinstance(item, dict)]
    if not valid_items:
        return ""
    title_html = _section_label_html(title, theme=theme)
    title_html = f"<h3 class='report-section-title' style='color:{theme['deep']};'>{_text(title)}</h3>" if clean_text(title) else ""
    rows = []
    for index, item in enumerate(valid_items, start=1):
        rows.append(
            "<tr>"
            f"<td class='report-item-ordinal' style='color:{theme['accent']};'>{index:02d}</td>"
            f"<td class='report-item-head'>{_text(item.get('title'))}</td>"
            f"<td class='report-item-body'>{_text(item.get('summary') or item.get('value'))} {_text(item.get('unit'))}</td>"
            "</tr>"
        )
    return (
        f"<section class='report-flow-section {list_class}'>"
        f"{title_html}<table class='report-item-table'>{''.join(rows)}</table></section>"
    )


def _metric_cards_html(items: list[dict[str, Any]], *, target: str, theme: dict[str, str]) -> str:
    valid_items = [item for item in items if isinstance(item, dict)]
    if not valid_items:
        return ""
    entries = "".join(
        "<span class='report-metric-inline'>"
        f"<span>{_text(item.get('title'))}</span>"
        f"<strong style='color:{theme['accent']};'>{_text(item.get('value'))}</strong>"
        f"<em>{_text(item.get('unit'))}</em>"
        "</span>"
        for item in valid_items[:4]
    )
    return f"<div class='report-metric-strip'>{entries}</div>"


def _table_block_html(block: dict[str, Any], *, theme: dict[str, str]) -> str:
    table = as_dict(block.get("table"))
    columns = [col for col in as_list(table.get("columns")) if isinstance(col, dict)]
    rows = [row for row in as_list(table.get("rows")) if isinstance(row, dict)]
    if not columns:
        return ""
    header = "".join(f"<th>{_text(col.get('label') or col.get('key'))}</th>" for col in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_text(row.get(clean_text(col.get('key'))))}</td>" for col in columns) + "</tr>"
        for row in rows
    )
    return (
        "<section class='report-flow-section report-table-wrap'>"
        f"{_section_label_html(block.get('title'), theme=theme)}"
        f"<div class='report-table-shell'><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>"
        "</section>"
    )


def _callout_html(block: dict[str, Any], *, theme: dict[str, str]) -> str:
    return (
        f"<aside class='report-callout' style='border-left-color:{theme['accent']};background:{theme['soft']};'>"
        f"<strong style='color:{theme['deep']};'>{_text(block.get('title'))}</strong>"
        f"<p>{_text(block.get('text'))}</p>"
        "</aside>"
    )


def _cover_html(page: dict[str, Any], *, target: str) -> str:
    hero = ""
    for block in as_list(page.get("blocks")):
        if not isinstance(block, dict):
            continue
        block_type = clean_text(block.get("type"))
        if block_type == "hero":
            hero = clean_text(block.get("title"))
    if target == PDF_TARGET:
        return (
            f"<article class='report-page report-page-cover report-page-pdf' data-page-type='cover' data-page-number='{_text(page.get('pageNumber'))}'>"
            "<div class='report-page-surface'>"
            "<div class='report-cover-pdf-shell'>"
            "<div class='report-cover-mark'>ANALYSIS REPORT</div>"
            "<div class='report-cover-rule'></div>"
            f"<h1 class='report-cover-pdf-title'>{_text(hero)}</h1>"
            "<p class='report-cover-pdf-subtitle'>基于材料证据生成的结构化分析报告</p>"
            "<div class='report-cover-pdf-footer'>STRATEGIC INTELLIGENCE · PDF EDITION</div>"
            "</div>"
            "</div></article>"
        )
    return (
        f"<article class='report-page report-page-cover' data-page-type='cover' data-page-number='{_text(page.get('pageNumber'))}'>"
        "<div class='report-page-surface'>"
        "<div class='report-cover-shell'>"
        "<div class='report-cover-grid'></div>"
        "<div class='report-cover-band'></div>"
        "<div class='report-cover-orb report-cover-orb-a'></div><div class='report-cover-orb report-cover-orb-b'></div>"
        "<div class='report-cover-content'>"
        "<div class='report-cover-mark'>ANALYSIS REPORT</div>"
        "<div class='report-cover-rule'></div>"
        f"<h1 class='report-cover-title'>{_text(hero)}</h1>"
        "<p class='report-cover-subtitle'>基于材料证据生成的结构化分析报告</p>"
        "</div><div class='report-cover-footer'><span>STRATEGIC INTELLIGENCE</span><span>PDF READY</span></div></div></div></article>"
    )


def _body_header_html(page: dict[str, Any], *, target: str, theme: dict[str, str]) -> str:
    display_title = clean_text(page.get("displayTitle") or page.get("title"))
    title = html.escape(display_title)
    if target == PDF_TARGET:
        return (
            "<section class='report-page-header'>"
            f"<div class='report-page-title'>{title}</div>"
            "</section>"
        )
    return (
        "<header class='report-page-header'>"
        "<div class='report-page-header-main'>"
        f"<h2 class='report-page-title'>{title}</h2>"
        "</div>"
        "</header>"
    )


def _body_footer_html(page: dict[str, Any], *, theme: dict[str, str]) -> str:
    folio = _folio(page.get("pageNumber"))
    return (
        "<footer class='report-page-footer'>"
        f"<span class='report-page-footer-rule' style='background:{theme['accent']};'></span>"
        "<span class='report-page-footer-label'>PAGINATED REPORT</span>"
        f"<span class='report-page-folio'>{folio}</span>"
        "</footer>"
    )


def _toc_html(page: dict[str, Any], *, target: str, theme: dict[str, str]) -> str:
    header = _body_header_html(page, target=target, theme=theme)
    items = [item for item in as_list(page.get("items")) if isinstance(item, dict)]
    rows = []
    for index, item in enumerate(items, start=1):
        title = _numbered_title(index, item.get("title"))
        rows.append(
            "<tr>"
            f"<td class='report-toc-ordinal' style='color:{theme['accent']};'>{index}.</td>"
            f"<td class='report-toc-title'>{html.escape(title)}</td>"
            "<td class='report-toc-dots'></td>"
            f"<td class='report-toc-page'>{_text(item.get('pageNumber'))}</td>"
            "</tr>"
        )
    classes = "report-page report-page-table_of_contents report-page-pdf" if target == PDF_TARGET else "report-page report-page-table_of_contents"
    return (
        f"<article class='{classes}' data-page-type='table_of_contents' data-page-number='{_text(page.get('pageNumber'))}'>"
        "<div class='report-page-surface'>"
        f"{header}<section class='report-panel report-panel-toc' style='{_panel_style(theme)}'><table class='report-toc-table'>{''.join(rows)}</table></section>{_body_footer_html(page, theme=theme)}"
        "</div></article>"
    )


def _block_html(
    block: dict[str, Any],
    *,
    table_lookup: dict[str, dict[str, Any]],
    theme: dict[str, str],
    target: str,
) -> str:
    block_type = clean_text(block.get("type"))
    if block_type == "section_intro":
        return f"<p class='report-intro' style='border-color:{theme['line']};background:{theme['soft']};'>{_text(block.get('text'))}</p>"
    if block_type == "paragraph":
        return f"<p class='report-paragraph'>{_text(block.get('text'))}</p>"
    if block_type == "callout":
        return _callout_html(block, theme=theme)
    if block_type == "meta_grid":
        items = [item for item in as_list(block.get("items")) if isinstance(item, dict)]
        return _meta_grid_html(items, target=target, theme=theme)
    if block_type == "metric_cards":
        items = [item for item in as_list(block.get("items")) if isinstance(item, dict)]
        return _metric_cards_html(items, target=target, theme=theme)
    if block_type in {"items", "evidence"}:
        items = [item for item in as_list(block.get("items")) if isinstance(item, dict)]
        list_class = "report-evidence-list" if block_type == "evidence" else "report-items-list"
        return _items_html(items, title=block.get("title") or ("证据与来源" if block_type == "evidence" else ""), target=target, theme=theme, list_class=list_class)
    if block_type == "chart":
        chart = as_dict(block.get("chartSpec"))
        svg = _chart_svg(chart, table_lookup=table_lookup, theme=theme)
        return (
            "<section class='report-flow-section report-chart-wrap'>"
            f"{_section_label_html(chart.get('title') or block.get('title') or '图表分析', theme=theme)}"
            f"<figure class='report-chart'>{svg}</figure></section>"
        )
    if block_type == "table_block":
        return _table_block_html(block, theme=theme)
    return ""


def _body_page_html(
    page: dict[str, Any],
    *,
    table_lookup: dict[str, dict[str, Any]],
    theme: dict[str, str],
    target: str,
) -> str:
    page_type = clean_text(page.get("pageType") or page.get("type")) or "body"
    blocks_html = []
    for block in as_list(page.get("blocks")):
        if isinstance(block, dict):
            rendered = _block_html(block, table_lookup=table_lookup, theme=theme, target=target)
            if rendered:
                blocks_html.append(rendered)
    classes = "report-page report-page-pdf" if target == PDF_TARGET else "report-page"
    return (
        f"<article class='{classes} report-page-{html.escape(page_type)}' data-page-type='{html.escape(page_type)}' data-page-number='{_text(page.get('pageNumber'))}'>"
        "<div class='report-page-surface'>"
        f"{_body_header_html(page, target=target, theme=theme)}"
        f"<div class='report-page-content'>{''.join(blocks_html)}</div>"
        f"{_body_footer_html(page, theme=theme)}"
        "</div></article>"
    )


def _page_html(
    page: dict[str, Any],
    *,
    bundle: dict[str, Any],
    table_lookup: dict[str, dict[str, Any]],
    palette: dict[str, Any],
    target: str,
    toc_index_map: dict[str, int],
) -> tuple[str, dict[str, Any]]:
    page = {**page, "displayTitle": _page_display_title(page, toc_index_map=toc_index_map)}
    page_type = clean_text(page.get("pageType") or page.get("type")).lower() or "insight"
    theme = _page_theme(page, palette)
    if page_type == "cover":
        return _cover_html(page, target=target), {"pageType": "cover", "theme": theme}
    if page_type == "table_of_contents":
        return _toc_html(page, target=target, theme=theme), {"pageType": "table_of_contents", "theme": theme}
    return _body_page_html(page, table_lookup=table_lookup, theme=theme, target=target), {"pageType": page_type, "theme": theme}


def _screen_css(bundle: dict[str, Any]) -> str:
    profile = as_dict(bundle.get("renderProfile"))
    palette = as_dict(profile.get("palette"))
    font_stack = _font_stack(bundle)
    background = clean_text(palette.get("background")) or "#FFFFFF"
    text = clean_text(palette.get("text")) or "#111827"
    primary = clean_text(palette.get("primary")) or TOKEN_COLORS["primary"]["accent"]
    accent = clean_text(palette.get("accent")) or TOKEN_COLORS["accent"]["accent"]
    return f"""
body{{
  font-family:{font_stack};
  background:linear-gradient(180deg,#f7f9fc 0%,#eef3f8 100%);
  color:{text};
  margin:0;
  padding:28px 24px 36px;
  line-height:1.72;
}}
.report-page{{width:210mm;min-height:297mm;margin:0 auto 26px;background:{background};box-shadow:0 26px 70px rgba(15,23,42,.14);border-radius:26px;overflow:hidden;page-break-after:always;break-after:page}}
.report-page:last-child{{page-break-after:auto;break-after:auto}}
.report-page-surface{{position:relative;min-height:261mm;padding:18mm 16mm 19mm}}
.report-page-cover .report-page-surface{{padding:0;min-height:297mm}}
.report-cover-shell{{position:relative;min-height:297mm;padding:30mm 24mm;background:radial-gradient(circle at 82% 16%,rgba(45,212,191,.28),transparent 24%),linear-gradient(135deg,#06111f 0%,#0f2747 48%,#082f49 100%);color:#f8fafc;overflow:hidden}}
.report-cover-grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.07) 1px,transparent 1px);background-size:34px 34px;mask-image:linear-gradient(90deg,transparent 0%,#000 18%,#000 72%,transparent 100%);opacity:.42}}
.report-cover-band{{position:absolute;right:-18mm;top:34mm;width:72mm;height:238mm;background:linear-gradient(180deg,rgba(20,184,166,.9),rgba(29,78,216,.28));transform:skewX(-14deg);box-shadow:0 34px 90px rgba(20,184,166,.18)}}
.report-cover-orb{{position:absolute;border-radius:999px;filter:blur(2px)}}
.report-cover-orb-a{{width:210px;height:210px;right:36px;top:54px;background:rgba(96,165,250,.22)}}
.report-cover-orb-b{{width:280px;height:280px;left:-120px;bottom:-120px;background:rgba(20,184,166,.16)}}
.report-cover-content{{position:relative;z-index:2;display:flex;min-height:218mm;max-width:78%;flex-direction:column;justify-content:center}}
.report-cover-mark{{display:inline-block;width:max-content;margin-bottom:18px;padding:7px 11px;border:1px solid rgba(125,211,252,.36);border-radius:999px;background:rgba(15,23,42,.34);color:#a7f3d0;font-size:11px;font-weight:700;letter-spacing:.18em}}
.report-cover-rule{{width:72px;height:3px;margin-bottom:24px;background:linear-gradient(90deg,#2dd4bf,#60a5fa);border-radius:999px}}
.report-cover-title{{font-size:54px;line-height:1.06;margin:0;color:#ffffff;letter-spacing:-.035em;text-shadow:0 18px 44px rgba(0,0,0,.28)}}
.report-cover-subtitle{{max-width:520px;margin:24px 0 0;color:#cbd5e1;font-size:18px;line-height:1.7}}
.report-cover-footer{{position:absolute;z-index:2;left:24mm;right:24mm;bottom:22mm;display:flex;justify-content:space-between;border-top:1px solid rgba(226,232,240,.22);padding-top:14px;color:#93c5fd;font-size:11px;font-weight:700;letter-spacing:.16em}}
.report-meta-grid{{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
.report-meta-card{{background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.2);border-radius:18px;padding:14px 16px;backdrop-filter:blur(10px)}}
.report-meta-card span{{display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;opacity:.8;margin-bottom:6px}}
.report-meta-card strong{{font-size:15px;line-height:1.45}}
.report-page-header{{position:relative;margin-bottom:22px;padding:0 0 16px;border-bottom:1px solid #d7e1ec}}
.report-page-header:after{{content:"";position:absolute;left:0;bottom:-1px;width:76px;height:3px;background:linear-gradient(90deg,{primary},{accent});border-radius:999px}}
.report-page-kicker{{display:block;font-size:11px;font-weight:800;letter-spacing:.16em;text-transform:uppercase;margin-bottom:9px}}
.report-page-title{{margin:0;max-width:86%;font-size:34px;line-height:1.13;color:#0f2747;letter-spacing:-.025em}}
.report-page-footer{{position:absolute;left:16mm;right:16mm;bottom:9mm;display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;color:#64748b;font-size:10px;font-weight:800;letter-spacing:.14em}}
.report-page-footer-rule{{width:34px;height:2px;border-radius:999px}}
.report-page-footer-label{{color:#94a3b8}}
.report-page-folio{{font-size:13px;line-height:1;font-weight:800;color:#0f2747;letter-spacing:.08em}}
.report-page-content>*+*{{margin-top:16px}}
.report-intro{{margin:0;padding:14px 16px;border:0;border-left:4px solid {accent};border-radius:14px;font-size:15px;color:#334155;background:linear-gradient(90deg,#eefcff 0%,#f8fbff 100%)}}
.report-panel{{border:1px solid #e3eaf3;border-radius:12px;padding:16px 18px;background:#ffffff}}
.report-flow-section{{margin:0;padding:0}}
.report-section-title,.report-panel-title{{font-size:17px;font-weight:800;letter-spacing:-.01em;margin:0 0 9px;color:#0f2747}}
.report-paragraph{{margin:0;font-size:15px;line-height:1.82;color:#1f2937}}
.report-callout{{margin:0;padding:15px 17px;border:1px solid #cde7ef;border-left:5px solid {primary};border-radius:16px;background:linear-gradient(135deg,#f8fbff 0%,#effdff 100%);box-shadow:0 12px 30px rgba(15,39,71,.05)}}
.report-callout strong{{display:block;margin-bottom:6px}}
.report-callout p{{margin:0;color:#334155}}
.report-metric-strip{{display:flex;flex-wrap:wrap;gap:8px 18px;margin:0;padding:10px 0;border-top:1px solid #d7e1ec;border-bottom:1px solid #d7e1ec}}
.report-metric-inline{{display:inline-flex;align-items:baseline;gap:6px;color:#475569}}
.report-metric-inline span{{font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}}
.report-metric-inline strong{{font-size:22px;line-height:1;letter-spacing:-.03em}}
.report-metric-inline em{{font-style:normal;font-size:11px;color:#64748b}}
.report-item-table{{width:100%;border-collapse:collapse;table-layout:auto}}
.report-item-table td{{padding:9px 10px;vertical-align:top;border:0;border-bottom:1px solid #e2e8f0;background:transparent}}
.report-item-ordinal{{width:44px;font-size:12px;font-weight:800;text-align:center}}
.report-item-head{{width:138px;min-width:138px;font-size:15px;font-weight:800;line-height:1.42;color:#0f2747;word-break:keep-all;white-space:normal}}
.report-item-body{{font-size:14px;line-height:1.7;color:#334155;word-break:break-word}}
.report-chart{{margin:0}}
.report-chart svg{{display:block;width:100%;height:auto}}
.chart-empty{{padding:26px 0;color:#64748b}}
.report-table-shell{{overflow:hidden;border-radius:14px;border:1px solid #d7e1ec;background:#fff}}
.report-table-shell table{{width:100%;border-collapse:collapse;font-size:12px}}
.report-table-shell th,.report-table-shell td{{padding:9px 11px;text-align:left;vertical-align:top;border:0;border-bottom:1px solid #e2e8f0}}
.report-table-shell th{{background:#0f2747;font-weight:800;color:#f8fafc}}
.report-table-shell tbody tr:last-child td{{border-bottom:0}}
.report-panel-toc{{padding:18px}}
.report-toc-table{{width:100%;border-collapse:collapse;table-layout:fixed}}
.report-toc-table td{{padding:8px 0;vertical-align:top;border:0}}
.report-toc-ordinal{{width:42px;font-size:14px;font-weight:700}}
.report-toc-title{{font-size:16px;font-weight:600;color:#111827;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.report-toc-dots{{border-bottom:2px dotted #94a3b8;transform:translateY(-6px)}}
.report-toc-page{{width:40px;font-size:15px;color:#475569;text-align:right}}
""".strip()


def _pdf_css(bundle: dict[str, Any]) -> str:
    profile = as_dict(bundle.get("renderProfile"))
    palette = as_dict(profile.get("palette"))
    font_stack = _font_stack(bundle)
    background = clean_text(palette.get("background")) or "#FFFFFF"
    text = clean_text(palette.get("text")) or "#111827"
    primary = clean_text(palette.get("primary")) or TOKEN_COLORS["primary"]["accent"]
    accent = clean_text(palette.get("accent")) or TOKEN_COLORS["accent"]["accent"]
    return f"""
body{{font-family:{font_stack};color:{text};margin:0;padding:0;line-height:1.7;font-size:10.5pt}}
.report-page{{page-break-after:always;break-after:page}}
.report-page:last-child{{page-break-after:auto;break-after:auto}}
.report-page-surface{{position:relative;padding:34px 30px 38px 30px;min-height:742px;background:{background}}}
.report-page-header{{position:relative;margin:0 0 22px 0;padding:0 0 14px 0;border-bottom:1px solid #d7e1ec}}
.report-page-header:after{{content:"";position:absolute;left:0;bottom:-1px;width:76px;height:3px;background:{primary};border-radius:999px}}
.report-page-title{{font-size:28pt;font-weight:800;line-height:1.14;color:#0f2747;letter-spacing:-.5px}}
.report-page-footer{{position:absolute;left:30px;right:30px;bottom:16px;border-top:1px solid #d7e1ec;padding-top:7px;color:#64748b;font-size:7.8pt;font-weight:800;letter-spacing:1.1px}}
.report-page-footer-rule{{display:inline-block;width:34px;height:2px;margin-right:8px;vertical-align:middle}}
.report-page-footer-label{{display:inline-block;color:#94a3b8}}
.report-page-folio{{float:right;color:#0f2747;font-size:9pt;font-weight:700;letter-spacing:.8px}}
.report-page-content>*+*{{margin-top:16px}}
.report-intro{{margin:0;padding:14px 16px;border:0;border-left:4px solid {accent};border-radius:14px;font-size:10.5pt;background:#f4fbff;color:#334155}}
.report-panel{{border:1px solid #e3eaf3;border-radius:12px;padding:16px 18px;margin:0 0 12px 0;background:#fff}}
.report-flow-section{{margin:0 0 12px 0;padding:0}}
.report-section-title,.report-panel-title{{font-size:13.5pt;font-weight:800;margin:0 0 9px 0;color:#0f2747}}
.report-paragraph{{margin:0;font-size:10.8pt;line-height:1.72;color:#1f2937}}
.report-callout{{margin:0 0 12px 0;padding:12px 14px;border:1px solid #cde7ef;border-left:5px solid {primary};border-radius:14px;background:#f6fbff}}
.report-callout strong{{display:block;margin-bottom:4px}}
.report-callout p{{margin:0}}
.report-metric-strip{{margin:0 0 12px 0;padding:7px 0;border-top:1px solid #d7e1ec;border-bottom:1px solid #d7e1ec}}
.report-metric-inline{{display:inline-block;margin-right:16px;color:#475569}}
.report-metric-inline span{{font-size:8pt;font-weight:700;letter-spacing:.8px;text-transform:uppercase;margin-right:5px}}
.report-metric-inline strong{{font-size:14pt;font-weight:700;margin-right:3px}}
.report-metric-inline em{{font-style:normal;font-size:8pt;color:#64748b}}
.report-item-table{{width:100%;border-collapse:collapse;table-layout:auto}}
.report-item-table td{{padding:8px 9px;vertical-align:top;border:0;border-bottom:1px solid #e2e8f0;background:#fbfdff}}
.report-item-ordinal{{width:38px;font-size:9.5pt;font-weight:700;text-align:center;color:#1d4ed8}}
.report-item-head{{width:112px;min-width:112px;font-size:10.5pt;font-weight:700;line-height:1.4;color:#0f2747;word-break:keep-all;white-space:normal}}
.report-item-body{{font-size:10.4pt;line-height:1.52;color:#334155;word-break:break-word}}
.report-chart{{margin:0}}
.report-chart svg{{width:100%;height:auto;display:block}}
.chart-empty{{padding:22px 0;color:#64748b}}
.report-table-shell{{overflow:hidden;border-radius:12px;border:1px solid #d7e1ec;background:#fff}}
.report-table-shell table{{width:100%;border-collapse:collapse;font-size:9pt}}
.report-table-shell th,.report-table-shell td{{padding:7px 8px;text-align:left;vertical-align:top;border:0;border-bottom:1px solid #e2e8f0}}
.report-table-shell th{{background:#0f2747;color:#f8fafc}}
.report-toc-table{{width:100%;border-collapse:collapse;table-layout:fixed}}
.report-toc-table td{{padding:6px 0;vertical-align:top;border:0}}
.report-toc-ordinal{{width:34px;font-size:9.5pt;font-weight:700}}
.report-toc-title{{font-size:11pt;font-weight:700;color:#111827}}
.report-toc-dots{{border-bottom:1px dotted #94a3b8;transform:translateY(-4px)}}
.report-toc-page{{width:28px;text-align:right;font-size:10pt;color:#475569}}
.report-meta-table{{width:100%;border-collapse:collapse;margin:0 0 14px 0;table-layout:fixed}}
.report-meta-cell{{width:50%;padding:8px 10px;border:1px solid #d5dde8;vertical-align:top;background:#fff}}
.report-meta-cell-empty{{background:#fff;border:1px solid #d5dde8}}
.report-meta-label{{font-size:8.5pt;font-weight:700;margin-bottom:4px;color:#475569}}
.report-meta-value{{font-size:10.5pt;line-height:1.5;color:#111827}}
.report-page-cover.report-page-pdf .report-page-surface{{padding:0;background:transparent}}
.report-cover-pdf-shell{{position:relative;padding:178px 64px 0 64px;background:transparent;min-height:790px;color:#f8fafc;overflow:hidden}}
.report-cover-mark{{position:relative;z-index:2;display:inline-block;width:max-content;margin-bottom:16px;padding:6px 10px;border:1px solid #3a7196;border-radius:999px;color:#a7f3d0;font-size:8.5pt;font-weight:800;letter-spacing:1.7px}}
.report-cover-rule{{position:relative;z-index:2;width:72px;height:3px;margin-bottom:24px;background:{accent};border-radius:999px}}
.report-cover-pdf-title{{position:relative;z-index:2;margin:0;max-width:430px;font-size:38pt;line-height:1.08;font-weight:800;color:#ffffff;letter-spacing:-.8px}}
.report-cover-pdf-subtitle{{position:relative;z-index:2;max-width:380px;margin:20px 0 0;font-size:12pt;line-height:1.7;color:#cbd5e1}}
.report-cover-pdf-footer{{position:absolute;z-index:2;left:64px;right:64px;bottom:44px;border-top:1px solid #334155;padding-top:13px;font-size:8.5pt;font-weight:800;letter-spacing:1.6px;color:#93c5fd}}
""".strip()


def _bundle_css(bundle: dict[str, Any], *, target: str) -> str:
    return _pdf_css(bundle) if target == PDF_TARGET else _screen_css(bundle)


def build_bundle_render_package(bundle: dict[str, Any], *, target: str = SCREEN_TARGET) -> dict[str, Any]:
    table_lookup = _table_lookup(bundle)
    palette = as_dict(as_dict(bundle.get("renderProfile")).get("palette"))
    toc_index_map = _bundle_toc_index_map(bundle)
    page_entries = []
    for page in as_list(bundle.get("pages")):
        if not isinstance(page, dict):
            continue
        page_html, meta = _page_html(page, bundle=bundle, table_lookup=table_lookup, palette=palette, target=target, toc_index_map=toc_index_map)
        page_entries.append({"html": page_html, **meta})
    return {
        "title": clean_text(bundle.get("title")) or "分析报告",
        "css": _bundle_css(bundle, target=target),
        "pages": [item["html"] for item in page_entries],
        "pageMeta": [{"pageType": item["pageType"], "theme": item["theme"]} for item in page_entries],
    }


def render_bundle_html(bundle: dict[str, Any]) -> str:
    package = build_bundle_render_package(bundle, target=SCREEN_TARGET)
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<title>{_text(package['title'])}</title><style>{package['css']}</style></head><body>"
        + "".join(package["pages"])
        + "</body></html>"
    )


def _block_markdown(lines: list[str], block: dict[str, Any]) -> None:
    block_type = clean_text(block.get("type"))
    if block_type == "hero":
        lines.extend([f"# {clean_text(block.get('title'))}", ""])
    elif block_type in {"subtitle", "section_intro", "paragraph"}:
        lines.extend([clean_text(block.get("text")), ""])
    elif block_type == "callout":
        lines.extend([f"> **{clean_text(block.get('title'))}** {clean_text(block.get('text'))}", ""])
    elif block_type == "meta_grid":
        for item in as_list(block.get("items")):
            if isinstance(item, dict):
                lines.append(f"- **{clean_text(item.get('label'))}** {clean_text(item.get('value'))}")
        lines.append("")
    elif block_type in {"items", "metric_cards", "evidence"}:
        for item in as_list(block.get("items")):
            if isinstance(item, dict):
                lines.append(f"- **{clean_text(item.get('title'))}** {clean_text(item.get('summary') or item.get('value'))} {clean_text(item.get('unit'))}")
        lines.append("")
    elif block_type == "chart":
        chart = as_dict(block.get("chartSpec"))
        lines.extend([f"图表：{clean_text(chart.get('title'))}", ""])
    elif block_type == "table_block":
        lines.extend([f"表格：{clean_text(block.get('title'))}", ""])


def render_bundle_markdown(bundle: dict[str, Any]) -> str:
    lines = [f"# {clean_text(bundle.get('title'))}", ""]
    for page in as_list(bundle.get("pages")):
        if not isinstance(page, dict):
            continue
        title = clean_text(page.get("title"))
        if title:
            lines.extend([f"## {title}", ""])
        if clean_text(page.get("pageType")) == "table_of_contents":
            for item in as_list(page.get("items")):
                if isinstance(item, dict):
                    lines.append(f"- {clean_text(item.get('title'))} ...... {item.get('pageNumber', '')}")
            lines.append("")
            continue
        for block in as_list(page.get("blocks")):
            if isinstance(block, dict):
                _block_markdown(lines, block)
    return "\n".join(lines).strip() + "\n"
