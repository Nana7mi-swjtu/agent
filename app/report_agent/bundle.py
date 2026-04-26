from __future__ import annotations

from typing import Any

from .contracts import PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION, clean_text, default_render_profile, drop_empty, new_report_id, prompt_versions, utc_now_iso
from .intake import intake_materials
from .normalization import normalize_materials
from .page_planning import plan_pages
from .prompts import load_default_prompts
from .validation import validate_bundle
from .writing import write_pages


def generate_paginated_report(
    *,
    materials: list[Any],
    title: str = "分析报告",
    goal: str = "",
    audience: str = "",
    render_style: str = "professional",
    source_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report_id = new_report_id()
    clean_title = clean_text(title, limit=160) or "分析报告"
    render_profile = default_render_profile(render_style)
    intake = intake_materials(materials)
    normalized = normalize_materials(intake["materials"])
    semantic_model = normalized["semanticModel"]
    page_plan = plan_pages(title=clean_title, semantic_model=semantic_model, render_profile=render_profile)
    pages = write_pages(page_plan["pages"])
    prompts = load_default_prompts()
    prompt_meta = {stage: {"id": data["id"], "version": data["version"]} for stage, data in prompts.items()}
    bundle = drop_empty(
        {
            "schemaVersion": PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION,
            "reportId": report_id,
            "title": clean_title,
            "status": "completed",
            "createdAt": utc_now_iso(),
            "metadata": {
                "goal": clean_text(goal, limit=300),
                "audience": clean_text(audience, limit=120),
                "sourceContext": source_context or {},
            },
            "inputSummary": {
                "materialCount": len(intake["materials"]),
                "detectedTypes": sorted({clean_text(item.get("detectedType")) for item in intake["materials"] if clean_text(item.get("detectedType"))}),
            },
            "materials": intake["materials"],
            "semanticModel": semantic_model,
            "pages": pages,
            "chartSpecs": page_plan["chartSpecs"],
            "assets": [],
            "evidenceRefs": semantic_model.get("evidenceRefs", []),
            "renderProfile": render_profile,
            "promptVersions": {**prompt_versions(), **{stage: value["version"] for stage, value in prompt_meta.items()}},
            "prompts": prompt_meta,
            "qualityFlags": [*intake.get("qualityFlags", []), *normalized.get("qualityFlags", [])],
            "exportManifest": {
                "availableFormats": ["pdf", "html", "bundle"],
                "primaryFormat": "pdf",
                "rendererInput": "PaginatedReportBundle",
            },
        }
    )
    validation_flags = validate_bundle(bundle)
    if validation_flags:
        bundle["qualityFlags"] = [*bundle.get("qualityFlags", []), *validation_flags]
        if any(flag.get("severity") == "error" for flag in validation_flags):
            bundle["status"] = "degraded"
    return bundle