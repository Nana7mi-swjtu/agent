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
    soft = theme["soft"]
    max_value = max(value for _, value in points) or 1.0
    chart_type = clean_text(chart_spec.get("type")).lower()
    step = usable_width / max(1, len(points))

    svg_parts = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{_text(chart_spec.get('title'))}'>",
        f"<rect x='1' y='1' width='{width - 2}' height='{height - 2}' rx='18' fill='{soft}' stroke='{grid_color}' stroke-width='1.4'/>",
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
        svg_parts.append(f"<polygon points='{' '.join(area_points)}' fill='{color}' opacity='0.12'/>")
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
            svg_parts.append(
                f"<rect x='{x:.1f}' y='{y + height_value * 0.28:.1f}' width='{bar_width:.1f}' height='{height_value * 0.72:.1f}' rx='10' fill='{deep}' opacity='0.16'/>"
            )
            svg_parts.append(f"<text x='{x + bar_width / 2:.1f}' y='{bottom + 18}' text-anchor='middle' font-size='11' fill='{deep}'>{html.escape(label)}</text>")
            svg_parts.append(f"<text x='{x + bar_width / 2:.1f}' y='{y - 8:.1f}' text-anchor='middle' font-size='11' fill='{deep}'>{value:g}</text>")
    svg_parts.append("</svg>")
    return "".join(svg_parts)


def _panel_style(theme: dict[str, str]) -> str:
    return f"border-color:{theme['line']};background:{theme['panel']};"


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
    if target == PDF_TARGET:
        rows = []
        for index, item in enumerate(valid_items, start=1):
            rows.append(
                "<tr>"
                f"<td class='report-item-ordinal' style='color:{theme['accent']};'>{index:02d}</td>"
                "<td class='report-item-main'>"
                f"<div class='report-item-head'>{_text(item.get('title'))}</div>"
                f"<div class='report-item-body'>{_text(item.get('summary') or item.get('value'))} {_text(item.get('unit'))}</div>"
                "</td></tr>"
            )
        return (
            f"<section class='report-panel {list_class}' style='{_panel_style(theme)}'>"
            f"{title_html}<table class='report-item-table'>{''.join(rows)}</table></section>"
        )
    cards = []
    for index, item in enumerate(valid_items, start=1):
        cards.append(
            "<li class='report-item-card'>"
            f"<div class='report-item-index' style='background:{theme['soft']};color:{theme['accent']};'>{index:02d}</div>"
            "<div class='report-item-copy'>"
            f"<h3>{_text(item.get('title'))}</h3>"
            f"<p>{_text(item.get('summary') or item.get('value'))} {_text(item.get('unit'))}</p>"
            "</div></li>"
        )
    return (
        f"<section class='report-panel {list_class}' style='{_panel_style(theme)}'>"
        f"{title_html}<ul class='report-item-list'>{''.join(cards)}</ul></section>"
    )


def _metric_cards_html(items: list[dict[str, Any]], *, target: str, theme: dict[str, str]) -> str:
    valid_items = [item for item in items if isinstance(item, dict)]
    if not valid_items:
        return ""
    if target == PDF_TARGET:
        cells = []
        for item in valid_items[:3]:
            cells.append(
                "<td class='report-metric-cell' style='border-color:"
                + theme["line"]
                + ";background:"
                + theme["soft"]
                + ";'>"
                + f"<div class='report-metric-label' style='color:{theme['deep']};'>{_text(item.get('title'))}</div>"
                + f"<div class='report-metric-value' style='color:{theme['accent']};'>{_text(item.get('value'))}</div>"
                + "</td>"
            )
        return f"<table class='report-metric-table'><tr>{''.join(cells)}</tr></table>"
    cards = "".join(
        "<li class='report-metric-card' style='border-color:"
        + theme["line"]
        + ";background:"
        + theme["soft"]
        + ";'>"
        + f"<span>{_text(item.get('title'))}</span>"
        + f"<strong style='color:{theme['accent']};'>{_text(item.get('value'))}</strong>"
        + "</li>"
        for item in valid_items[:3]
    )
    return f"<ul class='report-metrics'>{cards}</ul>"


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
        f"<section class='report-panel report-table-wrap' style='{_panel_style(theme)}'>"
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
            f"<h1 class='report-cover-pdf-title'>{_text(hero)}</h1>"
            "</div>"
            "</div></article>"
        )
    return (
        f"<article class='report-page report-page-cover' data-page-type='cover' data-page-number='{_text(page.get('pageNumber'))}'>"
        "<div class='report-page-surface'>"
        "<div class='report-cover-shell'>"
        "<div class='report-cover-wash report-cover-wash-a'></div><div class='report-cover-wash report-cover-wash-b'></div>"
        "<div class='report-cover-content'>"
        f"<h1 class='report-cover-title'>{_text(hero)}</h1>"
        "</div></div></div></article>"
    )


def _body_header_html(page: dict[str, Any], *, target: str, theme: dict[str, str]) -> str:
    title = _text(page.get("title"))
    kicker = html.escape(theme["kicker"])
    folio = _folio(page.get("pageNumber"))
    if target == PDF_TARGET:
        return (
            f"<div class='report-band' style='background:{theme['accent']};'></div>"
            "<table class='report-header-table'><tr>"
            "<td class='report-header-main'>"
            f"<div class='report-page-kicker' style='color:{theme['accent']};'>{kicker}</div>"
            f"<div class='report-page-title'>{title}</div>"
            "</td>"
            f"<td class='report-page-folio'>{folio}</td>"
            "</tr></table>"
        )
    return (
        f"<div class='report-band' style='background:{theme['accent']};'></div>"
        "<header class='report-page-header'>"
        "<div class='report-page-header-main'>"
        f"<span class='report-page-kicker' style='color:{theme['accent']};'>{kicker}</span>"
        f"<h2 class='report-page-title'>{title}</h2>"
        "</div>"
        f"<div class='report-page-folio'>{folio}</div>"
        "</header>"
    )


def _toc_html(page: dict[str, Any], *, target: str, theme: dict[str, str]) -> str:
    header = _body_header_html(page, target=target, theme=theme)
    items = [item for item in as_list(page.get("items")) if isinstance(item, dict)]
    if target == PDF_TARGET:
        rows = []
        for index, item in enumerate(items, start=1):
            rows.append(
                "<tr>"
                f"<td class='report-toc-ordinal' style='color:{theme['accent']};'>{index:02d}</td>"
                f"<td class='report-toc-title'>{_text(item.get('title'))}</td>"
                f"<td class='report-toc-page'>{_text(item.get('pageNumber'))}</td>"
                "</tr>"
            )
        return (
            f"<article class='report-page report-page-table_of_contents report-page-pdf' data-page-type='table_of_contents' data-page-number='{_text(page.get('pageNumber'))}'>"
            "<div class='report-page-surface'>"
            f"{header}<section class='report-panel report-panel-toc' style='{_panel_style(theme)}'>"
            f"<table class='report-toc-table'>{''.join(rows)}</table>"
            "</section></div></article>"
        )
    rows = []
    for index, item in enumerate(items, start=1):
        rows.append(
            "<li class='report-toc-row'>"
            f"<span class='report-toc-ordinal' style='color:{theme['accent']};'>{index:02d}</span>"
            f"<span class='report-toc-title'>{_text(item.get('title'))}</span>"
            "<span class='report-toc-dots'></span>"
            f"<strong class='report-toc-page'>{_text(item.get('pageNumber'))}</strong>"
            "</li>"
        )
    return (
        f"<article class='report-page report-page-table_of_contents' data-page-type='table_of_contents' data-page-number='{_text(page.get('pageNumber'))}'>"
        "<div class='report-page-surface'>"
        f"{header}<section class='report-panel report-panel-toc' style='{_panel_style(theme)}'><ol class='report-toc-list'>{''.join(rows)}</ol></section>"
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
        return f"<section class='report-panel report-copy' style='{_panel_style(theme)}'><p class='report-paragraph'>{_text(block.get('text'))}</p></section>"
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
            f"<section class='report-panel report-chart-wrap' style='{_panel_style(theme)}'>"
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
        "</div></article>"
    )


def _page_html(
    page: dict[str, Any],
    *,
    bundle: dict[str, Any],
    table_lookup: dict[str, dict[str, Any]],
    palette: dict[str, Any],
    target: str,
) -> tuple[str, dict[str, Any]]:
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
  background:radial-gradient(circle at top,#f6f9fc 0%,#eaf0f6 52%,#dde6f0 100%);
  color:{text};
  margin:0;
  padding:28px 24px 36px;
  line-height:1.68;
}}
.report-page{{width:210mm;min-height:297mm;margin:0 auto 26px;background:{background};box-shadow:0 26px 70px rgba(15,23,42,.14);border-radius:26px;overflow:hidden;page-break-after:always;break-after:page}}
.report-page:last-child{{page-break-after:auto;break-after:auto}}
.report-page-surface{{position:relative;min-height:261mm;padding:18mm 16mm 16mm}}
.report-page-cover .report-page-surface{{padding:0;min-height:297mm}}
.report-cover-shell{{position:relative;min-height:297mm;padding:28mm 22mm;background:linear-gradient(160deg,#dff0ff 0%,#c9e4ff 58%,#b8d9fb 100%);color:#14324d;overflow:hidden}}
.report-cover-wash{{position:absolute;border-radius:999px;opacity:.8}}
.report-cover-wash-a{{width:320px;height:320px;right:-70px;top:-90px;background:rgba(255,255,255,.72)}}
.report-cover-wash-b{{width:280px;height:280px;left:-90px;bottom:-120px;background:rgba(191,220,246,.65)}}
.report-cover-content{{position:relative;z-index:2;display:flex;align-items:center;min-height:241mm;max-width:72%}}
.report-cover-title{{font-size:48px;line-height:1.08;margin:0;color:#14324d;letter-spacing:.01em}}
.report-meta-grid{{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
.report-meta-card{{background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.2);border-radius:18px;padding:14px 16px;backdrop-filter:blur(10px)}}
.report-meta-card span{{display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;opacity:.8;margin-bottom:6px}}
.report-meta-card strong{{font-size:15px;line-height:1.45}}
.report-band{{width:84px;height:8px;border-radius:999px;margin-bottom:16px}}
.report-page-header{{display:grid;grid-template-columns:1fr auto;gap:18px;align-items:end;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid #d9e2ec}}
.report-page-kicker{{display:block;font-size:11px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;margin-bottom:8px}}
.report-page-title{{margin:0;font-size:30px;line-height:1.18;color:#0f172a}}
.report-page-folio{{font-size:40px;line-height:1;font-weight:700;color:#9aacbf}}
.report-page-content>*+*{{margin-top:14px}}
.report-intro{{margin:0;padding:14px 16px;border:1px solid #dbe6f0;border-radius:16px;font-size:15px;color:#334155}}
.report-panel{{border:1px solid #dbe6f0;border-radius:18px;padding:16px 18px}}
.report-panel-title{{font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;margin-bottom:12px}}
.report-copy p,.report-paragraph{{margin:0;font-size:14px;color:#1f2937}}
.report-callout{{margin:0;padding:14px 16px;border-left:4px solid {accent};border-radius:16px}}
.report-callout strong{{display:block;margin-bottom:6px}}
.report-callout p{{margin:0;color:#334155}}
.report-metrics{{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}
.report-metric-card{{padding:16px;border:1px solid #dbe6f0;border-radius:18px}}
.report-metric-card span{{display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#475569;margin-bottom:10px}}
.report-metric-card strong{{display:block;font-size:34px;line-height:1.1}}
.report-item-list{{list-style:none;padding:0;margin:0;display:grid;gap:12px}}
.report-item-card{{display:grid;grid-template-columns:42px 1fr;gap:14px;align-items:start;padding-top:12px;border-top:1px solid rgba(148,163,184,.22)}}
.report-item-card:first-child{{padding-top:0;border-top:0}}
.report-item-index{{width:34px;height:34px;border-radius:999px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700}}
.report-item-copy h3{{margin:0 0 6px 0;font-size:17px;line-height:1.3;color:#0f172a}}
.report-item-copy p{{margin:0;font-size:14px;color:#475569}}
.report-chart{{margin:0}}
.report-chart svg{{display:block;width:100%;height:auto}}
.chart-empty{{padding:26px 0;color:#64748b}}
.report-table-shell{{overflow:hidden;border-radius:14px;border:1px solid rgba(148,163,184,.22);background:#fff}}
.report-table-shell table{{width:100%;border-collapse:collapse;font-size:12px}}
.report-table-shell th,.report-table-shell td{{padding:9px 10px;text-align:left;vertical-align:top;border-bottom:1px solid #e5edf5}}
.report-table-shell th{{background:#f8fafc;font-weight:700;color:#334155}}
.report-table-shell tbody tr:last-child td{{border-bottom:0}}
.report-panel-toc{{padding:18px}}
.report-toc-list{{list-style:none;padding:0;margin:0;display:grid;gap:12px}}
.report-toc-row{{display:grid;grid-template-columns:auto auto 1fr auto;gap:12px;align-items:center;padding:12px 14px;border-radius:16px;background:#f8fbff;border:1px solid #dbe6f0}}
.report-toc-ordinal{{font-size:12px;font-weight:700}}
.report-toc-title{{font-size:15px;font-weight:600;color:#0f172a}}
.report-toc-dots{{border-bottom:1px dashed #c1cedd;transform:translateY(1px)}}
.report-toc-page{{font-size:15px;color:#475569}}
""".strip()


def _pdf_css(bundle: dict[str, Any]) -> str:
    profile = as_dict(bundle.get("renderProfile"))
    palette = as_dict(profile.get("palette"))
    font_stack = _font_stack(bundle)
    text = clean_text(palette.get("text")) or "#111827"
    return f"""
body{{font-family:{font_stack};color:{text};margin:0;padding:0;line-height:1.54;font-size:11pt}}
.report-page{{page-break-after:always;break-after:page}}
.report-page:last-child{{page-break-after:auto;break-after:auto}}
.report-page-surface{{padding:0}}
.report-page-pdf .report-band{{height:8px;margin:0 0 14px 0;border-radius:999px}}
.report-header-table{{width:100%;border-collapse:collapse;margin:0 0 14px 0}}
.report-header-main{{vertical-align:bottom}}
.report-page-kicker{{font-size:9pt;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:6px}}
.report-page-title{{font-size:22pt;font-weight:700;line-height:1.2;color:#0f172a}}
.report-page-folio{{width:58px;text-align:right;vertical-align:bottom;font-size:28pt;font-weight:700;color:#94a3b8}}
.report-intro{{margin:0 0 12px 0;padding:12px 14px;border:1px solid #dbe6f0;border-radius:10px;font-size:11pt}}
.report-panel{{border:1px solid #dbe6f0;border-radius:10px;padding:12px 14px;margin:0 0 12px 0}}
.report-panel-title{{font-size:9pt;font-weight:700;letter-spacing:1.1px;text-transform:uppercase;margin:0 0 8px 0}}
.report-paragraph{{margin:0;font-size:11pt}}
.report-callout{{margin:0 0 12px 0;padding:12px 14px;border-left:4px solid #1D4ED8;border-radius:10px}}
.report-callout strong{{display:block;margin-bottom:4px}}
.report-callout p{{margin:0}}
.report-metric-table{{width:100%;border-collapse:separate;border-spacing:0;margin:0 0 12px 0}}
.report-metric-cell{{width:33.33%;padding:10px 12px;border:1px solid #dbe6f0;vertical-align:top}}
.report-metric-label{{font-size:9pt;font-weight:700;line-height:1.45}}
.report-metric-value{{margin-top:8px;font-size:22pt;font-weight:700;line-height:1}}
.report-item-table{{width:100%;border-collapse:collapse}}
.report-item-table td{{padding:10px 0;vertical-align:top;border-top:1px solid #e5edf5}}
.report-item-table tr:first-child td{{border-top:0;padding-top:0}}
.report-item-ordinal{{width:42px;font-size:10pt;font-weight:700}}
.report-item-head{{font-size:12pt;font-weight:700;line-height:1.3;color:#0f172a;margin:0 0 4px 0}}
.report-item-body{{font-size:11pt;line-height:1.56;color:#334155}}
.report-chart{{margin:0}}
.report-chart svg{{width:100%;height:auto;display:block}}
.chart-empty{{padding:22px 0;color:#64748b}}
.report-table-shell table{{width:100%;border-collapse:collapse;font-size:9pt}}
.report-table-shell th,.report-table-shell td{{padding:7px 8px;text-align:left;vertical-align:top;border:1px solid #dbe6f0}}
.report-table-shell th{{background:#f8fafc;color:#334155}}
.report-toc-table{{width:100%;border-collapse:collapse}}
.report-toc-table td{{padding:10px 0;border-top:1px solid #e5edf5;vertical-align:top}}
.report-toc-table tr:first-child td{{border-top:0;padding-top:0}}
.report-toc-ordinal{{width:42px;font-size:10pt;font-weight:700}}
.report-toc-title{{font-size:12pt;font-weight:700;color:#0f172a}}
.report-toc-page{{width:36px;text-align:right;font-size:11pt;color:#475569}}
.report-meta-table{{width:100%;border-collapse:separate;border-spacing:0;margin:0 0 14px 0}}
.report-meta-cell{{width:50%;padding:10px 12px;border:1px solid #314761;background:#13233f;vertical-align:top}}
.report-meta-cell-empty{{background:transparent;border:0}}
.report-meta-label{{font-size:8.5pt;font-weight:700;letter-spacing:.7px;text-transform:uppercase;margin-bottom:5px;color:#cbd5e1}}
.report-meta-value{{font-size:11pt;line-height:1.55;color:#f8fafc}}
.report-page-cover.report-page-pdf .report-page-surface{{padding:0}}
.report-cover-pdf-shell{{padding:92px 16px 0 18px}}
.report-cover-pdf-title{{margin:0;font-size:28pt;line-height:1.18;font-weight:700;color:#14324d}}
""".strip()


def _bundle_css(bundle: dict[str, Any], *, target: str) -> str:
    return _pdf_css(bundle) if target == PDF_TARGET else _screen_css(bundle)


def build_bundle_render_package(bundle: dict[str, Any], *, target: str = SCREEN_TARGET) -> dict[str, Any]:
    table_lookup = _table_lookup(bundle)
    palette = as_dict(as_dict(bundle.get("renderProfile")).get("palette"))
    page_entries = []
    for page in as_list(bundle.get("pages")):
        if not isinstance(page, dict):
            continue
        page_html, meta = _page_html(page, bundle=bundle, table_lookup=table_lookup, palette=palette, target=target)
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
