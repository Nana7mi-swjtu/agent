from __future__ import annotations

from typing import Any

from .contracts import as_list, clean_text


def _page_intro(page_type: str, title: str) -> str:
    if page_type == "executive_summary":
        return "本页汇总输入材料中最适合进入正式报告的关键信息。"
    if page_type == "insight":
        return "本页列出由材料支持的进一步发现。"
    if page_type == "chart_analysis":
        return "本页使用结构化数据生成可视化表达。"
    if page_type == "table_analysis":
        return "本页保留关键表格数据，便于复核。"
    if page_type == "evidence":
        return "本页列出支撑报告结论的主要材料来源。"
    if page_type == "recommendation":
        return "本页给出基于现有材料的使用建议和解释边界。"
    return clean_text(title)


def write_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    written = []
    for page in pages:
        page = dict(page)
        if page.get("pageType") not in {"cover", "table_of_contents"}:
            blocks = as_list(page.get("blocks"))
            if not blocks or clean_text(blocks[0].get("type") if isinstance(blocks[0], dict) else "") != "section_intro":
                blocks = [{"type": "section_intro", "text": _page_intro(clean_text(page.get("pageType")), clean_text(page.get("title")))}] + [b for b in blocks if isinstance(b, dict)]
            page["blocks"] = blocks
        written.append(page)
    return written