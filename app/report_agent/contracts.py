from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION = "paginated_report_bundle.v1"
REPORT_MATERIAL_SCHEMA_VERSION = "report_material.v1"
NORMALIZED_MATERIAL_SCHEMA_VERSION = "normalized_report_material.v1"
REPORT_SOURCE_SNAPSHOT_SCHEMA_VERSION = "report_source_snapshot.v1"
DEFAULT_RENDER_STYLE = "professional"
DEFAULT_PROMPT_VERSION = "v1"

MATERIAL_TYPES = {
    "auto",
    "text",
    "markdown",
    "json",
    "table",
    "metric",
    "image",
    "evidence",
    "module_artifact",
    "mixed",
}
PAGE_TYPES = {
    "cover",
    "table_of_contents",
    "executive_summary",
    "insight",
    "chart_analysis",
    "table_analysis",
    "evidence",
    "recommendation",
    "appendix",
}
BLOCK_TYPES = {
    "hero",
    "subtitle",
    "meta_grid",
    "callout",
    "paragraph",
    "items",
    "metric_cards",
    "chart",
    "table_block",
    "evidence",
    "image",
}
APPROVED_COLOR_TOKENS = {
    "primary",
    "accent",
    "danger",
    "warning",
    "success",
    "text",
    "muted",
    "background",
}
APPROVED_TYPOGRAPHY_ROLES = {
    "coverTitle",
    "pageTitle",
    "sectionTitle",
    "body",
    "caption",
}
APPROVED_LAYOUTS = {
    "cover",
    "toc",
    "summary_cards",
    "title_text",
    "title_chart_notes",
    "title_table_notes",
    "evidence_list",
    "appendix_list",
}


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_report_id() -> str:
    return f"report_{uuid.uuid4().hex[:12]}"


def clean_text(value: Any, *, limit: int | None = None) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", "").strip()
    text = " ".join(text.split())
    if limit is not None and len(text) > limit:
        return text[: max(0, limit - 1)].rstrip() + "…"
    return text


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def string_list(value: Any) -> list[str]:
    return [item for item in (clean_text(item) for item in as_list(value)) if item]


def default_render_profile(render_style: str = DEFAULT_RENDER_STYLE) -> dict[str, Any]:
    style = clean_text(render_style) or DEFAULT_RENDER_STYLE
    palette = {
        "primary": "#1D4ED8",
        "accent": "#14B8A6",
        "danger": "#DC2626",
        "warning": "#D97706",
        "success": "#16A34A",
        "text": "#111827",
        "muted": "#6B7280",
        "background": "#FFFFFF",
    }
    if style == "dark_research":
        palette.update({"primary": "#60A5FA", "accent": "#2DD4BF", "text": "#F8FAFC", "muted": "#CBD5E1", "background": "#111827"})
    elif style == "brand_cover":
        palette.update({"primary": "#0F766E", "accent": "#14B8A6"})
    elif style == "chart_focus":
        palette.update({"primary": "#1D4ED8", "accent": "#F59E0B"})
    return {
        "style": style,
        "pageSize": "A4",
        "orientation": "portrait",
        "fontFamily": {
            "title": "Noto Sans CJK SC",
            "body": "Noto Sans CJK SC",
            "fallback": ["Microsoft YaHei", "SimSun", "Arial"],
        },
        "typography": {
            "coverTitle": 30,
            "pageTitle": 22,
            "sectionTitle": 14,
            "body": 10.5,
            "caption": 8.5,
        },
        "palette": palette,
        "layouts": sorted(APPROVED_LAYOUTS),
    }


def prompt_versions() -> dict[str, str]:
    return {
        "material_intake": DEFAULT_PROMPT_VERSION,
        "semantic_normalizer": DEFAULT_PROMPT_VERSION,
        "page_planner": DEFAULT_PROMPT_VERSION,
        "visual_designer": DEFAULT_PROMPT_VERSION,
        "narrative_writer": DEFAULT_PROMPT_VERSION,
        "quality_reviewer": DEFAULT_PROMPT_VERSION,
    }


def drop_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", [], {})}
