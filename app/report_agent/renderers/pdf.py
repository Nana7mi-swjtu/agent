from __future__ import annotations

from typing import Any

from .html import render_bundle_markdown


def render_bundle_pdf(bundle: dict[str, Any]) -> bytes:
    try:
        import fitz
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("PyMuPDF is required for PDF rendering") from exc
    markdown = render_bundle_markdown(bundle)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    cursor_y = 48
    for line in markdown.splitlines():
        if cursor_y > 790:
            page = doc.new_page(width=595, height=842)
            cursor_y = 48
        fontsize = 18 if line.startswith("# ") else 14 if line.startswith("## ") else 10.5
        text = line.lstrip("# ").strip() or " "
        page.insert_textbox(fitz.Rect(48, cursor_y, 548, cursor_y + 32), text, fontsize=fontsize, fontname="helv", color=(0.05, 0.09, 0.16))
        cursor_y += 34 if fontsize >= 14 else 22
    return doc.tobytes()