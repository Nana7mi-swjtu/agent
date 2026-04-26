from __future__ import annotations

import html
from typing import Any

from ..contracts import as_dict, as_list, clean_text


def _text(value: Any) -> str:
    return html.escape(clean_text(value))


def _block_html(block: dict[str, Any]) -> str:
    block_type = clean_text(block.get("type"))
    if block_type == "hero":
        return f"<h1>{_text(block.get('title'))}</h1>"
    if block_type in {"subtitle", "section_intro", "paragraph"}:
        return f"<p>{_text(block.get('text'))}</p>"
    if block_type == "callout":
        return f"<aside><strong>{_text(block.get('title'))}</strong><p>{_text(block.get('text'))}</p></aside>"
    if block_type == "meta_grid":
        items = "".join(f"<li><strong>{_text(item.get('label'))}</strong>: {_text(item.get('value'))}</li>" for item in as_list(block.get("items")) if isinstance(item, dict))
        return f"<ul class=\"meta-grid\">{items}</ul>"
    if block_type in {"items", "metric_cards"}:
        items = "".join(f"<li><strong>{_text(item.get('title'))}</strong> {_text(item.get('summary') or item.get('value'))} {_text(item.get('unit'))}</li>" for item in as_list(block.get("items")) if isinstance(item, dict))
        title = _text(block.get("title"))
        return f"<section>{f'<h3>{title}</h3>' if title else ''}<ul>{items}</ul></section>"
    if block_type == "evidence":
        items = "".join(f"<li><strong>{_text(item.get('title'))}</strong> {_text(item.get('summary'))}</li>" for item in as_list(block.get("items")) if isinstance(item, dict))
        return f"<section><h3>证据</h3><ul>{items}</ul></section>"
    if block_type == "chart":
        chart = as_dict(block.get("chartSpec"))
        return f"<figure class=\"chart-placeholder\"><figcaption>{_text(chart.get('title') or block.get('title'))}</figcaption><pre>{_text(chart)}</pre></figure>"
    if block_type == "table_block":
        table = as_dict(block.get("table"))
        columns = [col for col in as_list(table.get("columns")) if isinstance(col, dict)]
        rows = [row for row in as_list(table.get("rows")) if isinstance(row, dict)]
        header = "".join(f"<th>{_text(col.get('label') or col.get('key'))}</th>" for col in columns)
        body = "".join("<tr>" + "".join(f"<td>{_text(row.get(clean_text(col.get('key'))))}</td>" for col in columns) + "</tr>" for row in rows)
        return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"
    return ""


def render_bundle_html(bundle: dict[str, Any]) -> str:
    profile = as_dict(bundle.get("renderProfile"))
    palette = as_dict(profile.get("palette"))
    css = f"body{{font-family:system-ui,'Microsoft YaHei',sans-serif;color:{palette.get('text','#111827')};background:{palette.get('background','#fff')};line-height:1.65;margin:32px;}} .report-page{{page-break-after:always;border-bottom:1px solid #e5e7eb;padding:24px 0;}} table{{border-collapse:collapse;width:100%;}} th,td{{border:1px solid #e5e7eb;padding:6px 8px;}} aside{{border-left:4px solid {palette.get('accent','#14B8A6')};padding:8px 12px;background:#f8fafc;}}"
    parts = ["<!doctype html><html><head><meta charset='utf-8'>", f"<title>{_text(bundle.get('title'))}</title><style>{css}</style></head><body>"]
    for page in as_list(bundle.get("pages")):
        if not isinstance(page, dict):
            continue
        parts.append(f"<article class='report-page' data-page='{_text(page.get('pageNumber'))}' data-type='{_text(page.get('pageType'))}'>")
        title = clean_text(page.get("title"))
        if title and page.get("pageType") != "cover":
            parts.append(f"<h2>{_text(title)}</h2>")
        if page.get("pageType") == "table_of_contents":
            items = "".join(f"<li>{_text(item.get('title'))}<span> {item.get('pageNumber','')}</span></li>" for item in as_list(page.get("items")) if isinstance(item, dict))
            parts.append(f"<ol>{items}</ol>")
        for block in as_list(page.get("blocks")):
            if isinstance(block, dict):
                parts.append(_block_html(block))
        parts.append("</article>")
    parts.append("</body></html>")
    return "".join(parts)


def _block_markdown(lines: list[str], block: dict[str, Any]) -> None:
    block_type = clean_text(block.get("type"))
    if block_type == "hero":
        lines.extend([f"# {clean_text(block.get('title'))}", ""])
    elif block_type in {"subtitle", "section_intro", "paragraph"}:
        lines.extend([clean_text(block.get("text")), ""])
    elif block_type == "callout":
        lines.extend([f"> **{clean_text(block.get('title'))}** {clean_text(block.get('text'))}", ""])
    elif block_type in {"items", "metric_cards", "evidence"}:
        for item in as_list(block.get("items")):
            if isinstance(item, dict):
                lines.append(f"- **{clean_text(item.get('title'))}** {clean_text(item.get('summary') or item.get('value'))} {clean_text(item.get('unit'))}")
        lines.append("")
    elif block_type == "chart":
        chart = as_dict(block.get("chartSpec"))
        lines.extend([f"![{clean_text(chart.get('title'))}](chart:{clean_text(chart.get('chartId'))})", ""])
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
        if page.get("pageType") == "table_of_contents":
            for item in as_list(page.get("items")):
                if isinstance(item, dict):
                    lines.append(f"- {clean_text(item.get('title'))} ...... {item.get('pageNumber', '')}")
            lines.append("")
        for block in as_list(page.get("blocks")):
            if isinstance(block, dict):
                _block_markdown(lines, block)
    return "\n".join(lines).strip() + "\n"