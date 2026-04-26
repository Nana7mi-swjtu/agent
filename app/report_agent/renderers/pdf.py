from __future__ import annotations

from typing import Any

from .html import PDF_TARGET, build_bundle_render_package

PDF_PAGE_WIDTH = 595
PDF_PAGE_HEIGHT = 842
PDF_MARGIN_X = 30
PDF_MARGIN_Y = 24


def _render_page(page: Any, fragment: str, *, fitz_module: Any, css: str) -> None:
    rect = fitz_module.Rect(PDF_MARGIN_X, PDF_MARGIN_Y, PDF_PAGE_WIDTH - PDF_MARGIN_X, PDF_PAGE_HEIGHT - PDF_MARGIN_Y)
    spare_height, _ = page.insert_htmlbox(rect, fragment, css=css, scale_low=0.78)
    if spare_height == -1:
        spare_height, _ = page.insert_htmlbox(rect, fragment, css=css, scale_low=0.68)
    if spare_height == -1:
        raise RuntimeError("reviewed report page overflowed the PDF layout")


def _hex_to_rgb(value: Any) -> tuple[float, float, float]:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6:
        return (1.0, 1.0, 1.0)
    return tuple(int(text[index : index + 2], 16) / 255 for index in (0, 2, 4))


def _paint_page_background(page: Any, meta: dict[str, Any], *, fitz_module: Any) -> None:
    if meta.get("pageType") != "cover":
        return
    cover_fill = _hex_to_rgb("#D8ECFF")
    page.draw_rect(fitz_module.Rect(0, 0, PDF_PAGE_WIDTH, PDF_PAGE_HEIGHT), color=None, fill=cover_fill)


def render_bundle_pdf(bundle: dict[str, Any]) -> bytes:
    try:
        import fitz
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("PyMuPDF is required for PDF rendering") from exc

    package = build_bundle_render_package(bundle, target=PDF_TARGET)
    doc = fitz.open()
    try:
        for fragment, meta in zip(package["pages"], package.get("pageMeta", []), strict=False):
            page = doc.new_page(width=PDF_PAGE_WIDTH, height=PDF_PAGE_HEIGHT)
            _paint_page_background(page, meta, fitz_module=fitz)
            _render_page(page, fragment, fitz_module=fitz, css=package["css"])
        return doc.tobytes(deflate=True, garbage=3)
    finally:
        doc.close()
