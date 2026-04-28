from __future__ import annotations

from typing import Any

from .html import PDF_TARGET, build_bundle_render_package

PDF_PAGE_WIDTH = 595
PDF_PAGE_HEIGHT = 842
PDF_MARGIN_X = 30
PDF_MARGIN_Y = 24


def _draw_polygon(page: Any, points: list[tuple[float, float]], *, fitz_module: Any, fill: tuple[float, float, float], opacity: float) -> None:
    shape = page.new_shape()
    shape.draw_polyline([fitz_module.Point(x, y) for x, y in points])
    shape.finish(color=None, fill=fill, closePath=True, fill_opacity=opacity, stroke_opacity=0)
    shape.commit()


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
    cover_fill = _hex_to_rgb("#06111F")
    page.draw_rect(fitz_module.Rect(0, 0, PDF_PAGE_WIDTH, PDF_PAGE_HEIGHT), color=None, fill=cover_fill)
    grid_color = _hex_to_rgb("#16304A")
    for x in range(42, PDF_PAGE_WIDTH, 42):
        page.draw_line((x, 0), (x, PDF_PAGE_HEIGHT), color=grid_color, width=0.45, stroke_opacity=0.22)
    for y in range(42, PDF_PAGE_HEIGHT, 42):
        page.draw_line((0, y), (PDF_PAGE_WIDTH, y), color=grid_color, width=0.45, stroke_opacity=0.22)
    page.draw_circle((458, 150), 76, color=None, fill=_hex_to_rgb("#60A5FA"), fill_opacity=0.22)
    page.draw_circle((-42, 820), 128, color=None, fill=_hex_to_rgb("#14B8A6"), fill_opacity=0.14)
    _draw_polygon(
        page,
        [(498, 128), (626, 128), (556, 842), (392, 842)],
        fitz_module=fitz_module,
        fill=_hex_to_rgb("#14B8A6"),
        opacity=0.62,
    )
    _draw_polygon(
        page,
        [(466, 128), (498, 128), (392, 842), (356, 842)],
        fitz_module=fitz_module,
        fill=_hex_to_rgb("#1D4ED8"),
        opacity=0.22,
    )
    page.draw_line((64, 736), (531, 736), color=_hex_to_rgb("#334155"), width=0.8, stroke_opacity=0.9)


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
