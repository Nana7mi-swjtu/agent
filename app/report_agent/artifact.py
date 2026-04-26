from __future__ import annotations

from typing import Any

from .contracts import REPORT_SOURCE_SNAPSHOT_SCHEMA_VERSION, as_dict, as_list, clean_text
from .renderers.html import render_bundle_html, render_bundle_markdown

REPORT_ARTIFACT_SCHEMA_VERSION = "analysis_report_artifact.v1"
REPORT_DOCUMENT_SCHEMA_VERSION = "analysis_report_document.v1"


def _old_block(block: dict[str, Any]) -> dict[str, Any]:
    block_type = clean_text(block.get("type"))
    if block_type == "metric_cards":
        return {"type": "stat_strip", "items": as_list(block.get("items"))}
    if block_type == "chart":
        return {
            "type": "visual_asset",
            "title": clean_text(block.get("title")) or clean_text(as_dict(block.get("chartSpec")).get("title")),
            "asset": {
                "assetId": clean_text(as_dict(block.get("chartSpec")).get("chartId")),
                "assetType": "chart",
                "title": clean_text(as_dict(block.get("chartSpec")).get("title")),
                "renderPayload": as_dict(block.get("chartSpec")),
            },
        }
    return block


def bundle_to_legacy_document(bundle: dict[str, Any]) -> dict[str, Any]:
    pages = []
    for page in as_list(bundle.get("pages")):
        if not isinstance(page, dict):
            continue
        page_type = clean_text(page.get("pageType"))
        if page_type == "table_of_contents":
            pages.append({"id": page.get("id"), "type": "table_of_contents", "title": page.get("title"), "items": as_list(page.get("items"))})
            continue
        if page_type == "cover":
            pages.append({"id": page.get("id"), "type": "cover", "title": page.get("title"), "blocks": [_old_block(block) for block in as_list(page.get("blocks")) if isinstance(block, dict)]})
            continue
        blocks = [_old_block(block) for block in as_list(page.get("blocks")) if isinstance(block, dict)]
        pages.append(
            {
                "id": page.get("id"),
                "type": "body",
                "title": page.get("title"),
                "sections": [
                    {
                        "id": page.get("id"),
                        "title": page.get("title"),
                        "intro": "",
                        "blocks": blocks,
                    }
                ],
            }
        )
    return {
        "schemaVersion": REPORT_DOCUMENT_SCHEMA_VERSION,
        "renderStyle": clean_text(as_dict(bundle.get("renderProfile")).get("style")) or "professional",
        "structureLocked": True,
        "chapterOutline": [
            {"id": page.get("id"), "title": page.get("title"), "origin": "paginated_bundle", "pageNumber": page.get("pageNumber")}
            for page in as_list(bundle.get("pages"))
            if isinstance(page, dict) and page.get("tocEntry")
        ],
        "pages": pages,
    }


def bundle_to_analysis_report_artifact(
    bundle: dict[str, Any],
    *,
    source_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    markdown_body = render_bundle_markdown(bundle)
    html_body = render_bundle_html(bundle)
    report_id = clean_text(bundle.get("reportId"))
    semantic_model = as_dict(bundle.get("semanticModel"))
    limitations = [
        clean_text(flag.get("code"))
        for flag in as_list(bundle.get("qualityFlags"))
        if isinstance(flag, dict) and clean_text(flag.get("severity")) in {"warning", "error"}
    ]
    visual_assets = []
    for chart in as_list(bundle.get("chartSpecs")):
        if isinstance(chart, dict):
            visual_assets.append(
                {
                    "assetId": clean_text(chart.get("chartId")),
                    "assetType": "chart",
                    "title": clean_text(chart.get("title")),
                    "contentType": "application/json",
                    "renderPayload": chart,
                }
            )
    return {
        "schemaVersion": REPORT_ARTIFACT_SCHEMA_VERSION,
        "reportId": report_id,
        "title": clean_text(bundle.get("title")) or "分析报告",
        "status": clean_text(bundle.get("status")) or "completed",
        "renderStyle": clean_text(as_dict(bundle.get("renderProfile")).get("style")) or "professional",
        "scope": {
            "analysisSessionId": "",
            "analysisSessionRevision": 0,
            "sourceDocumentCount": len(
                [
                    item
                    for item in as_list(as_dict(source_snapshot).get("documents"))
                    if isinstance(item, dict) and clean_text(item.get("content"))
                ]
            ),
        },
        "sourceSnapshot": source_snapshot
        or {
            "schemaVersion": REPORT_SOURCE_SNAPSHOT_SCHEMA_VERSION,
            "documents": [],
        },
        "semanticModel": semantic_model,
        "document": bundle_to_legacy_document(bundle),
        "paginatedReportBundle": bundle,
        "sections": [],
        "markdownBody": markdown_body,
        "htmlBody": html_body,
        "visualAssets": visual_assets,
        "attachments": as_list(bundle.get("assets")),
        "limitations": [{"message": item} for item in limitations if item],
        "exportManifest": as_dict(bundle.get("exportManifest")),
        "renderProfile": as_dict(bundle.get("renderProfile")),
    }
