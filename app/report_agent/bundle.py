from __future__ import annotations

import json
import re
from typing import Any

from .contracts import (
    APPROVED_LAYOUTS,
    MATERIAL_TYPES,
    PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION,
    PAGE_TYPES,
    as_dict,
    as_list,
    clean_text,
    default_render_profile,
    drop_empty,
    new_report_id,
    prompt_versions,
    string_list,
    utc_now_iso,
)
from .intake import intake_materials
from .publication import validate_published_report
from .normalization import normalize_materials
from .prompts import load_default_prompts
from .runtime import ReportRuntimeError, get_report_writer
from .stage import STAGES
from .validation import has_blocking_errors, validate_bundle
from .visual_planning import build_chart_specs, enforce_visual_tokens, looks_temporal_chart_axis
from .writing import write_pages

ALLOWED_SECTION_IDS = {
    "report_scope",
    "executive_judgement",
    "key_findings",
    "model_visual_interpretation",
    "recommendations",
}
PAGE_TYPE_LAYOUTS = {
    "executive_summary": "title_text",
    "insight": "title_text",
    "chart_analysis": "title_chart_notes",
    "table_analysis": "title_table_notes",
    "evidence": "evidence_list",
    "recommendation": "title_text",
    "appendix": "appendix_list",
}
PAGE_TYPE_ACCENTS = {
    "executive_summary": "primary",
    "insight": "accent",
    "chart_analysis": "primary",
    "table_analysis": "accent",
    "evidence": "muted",
    "recommendation": "success",
    "appendix": "warning",
}
LEGACY_CHAPTER_BLUEPRINTS = {
    "executive_summary": {
        "title": "执行摘要",
        "pageType": "executive_summary",
        "layout": "title_text",
        "sectionIds": ["executive_judgement"],
    },
    "key_findings": {
        "title": "关键发现",
        "pageType": "insight",
        "layout": "title_text",
        "sectionIds": ["key_findings"],
    },
    "visuals": {
        "title": "趋势与结构观察",
        "pageType": "chart_analysis",
        "layout": "title_chart_notes",
        "sectionIds": ["model_visual_interpretation"],
    },
    "tables": {
        "title": "关键数据摘录",
        "pageType": "table_analysis",
        "layout": "title_table_notes",
        "sectionIds": ["model_visual_interpretation"],
    },
    "evidence": {
        "title": "证据与来源",
        "pageType": "evidence",
        "layout": "evidence_list",
        "sectionIds": ["evidence_verification"],
    },
    "recommendations": {
        "title": "建议与行动",
        "pageType": "recommendation",
        "layout": "title_text",
        "sectionIds": ["recommendations"],
    },
}
META_PARAGRAPH_TITLES = {
    "执行摘要",
    "关键发现",
    "证据与来源",
    "建议与行动",
    "风险与机会评估",
    "图表",
    "数据表",
    "趋势与结构观察",
    "关键数据摘录",
}
VISUAL_BASIS_TITLES = {"判断依据", "关键依据", "依据说明", "数据依据", "来源说明"}
VISUAL_BOUNDARY_TITLES = {"解读边界", "表格边界", "解释边界", "使用边界", "边界说明", "限制说明"}
META_ONLY_ITEM_TITLES = {*VISUAL_BASIS_TITLES, *VISUAL_BOUNDARY_TITLES, "图表解读", "视觉解读"}
FORBIDDEN_TAIL_CHAPTER_TITLES = {"逻辑拆解", "边界与限制", "来源与核验"}


class ReportGenerationError(RuntimeError):
    pass


def _flag(code: str, *, severity: str = "warning", message: str = "", **extra: Any) -> dict[str, Any]:
    return drop_empty(
        {
            "code": clean_text(code, limit=80) or "report_flag",
            "severity": clean_text(severity, limit=16) or "warning",
            "message": clean_text(message, limit=240),
            **extra,
        }
    )


def _content_preview(value: Any, *, limit: int = 4000) -> str:
    if isinstance(value, str):
        text = value.replace("\x00", "").strip()
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value or "").replace("\x00", "").strip()
    if len(text) > limit:
        return text[: max(0, limit - 1)].rstrip() + "…"
    return text


def _extract_json_payload(response: Any) -> dict[str, Any] | None:
    if isinstance(response, dict):
        return response
    content = getattr(response, "content", response)
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = clean_text(value).lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off", ""}:
        return False
    return bool(value)


def _normalize_stage_flags(value: Any, *, stage_id: str) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for item in as_list(value):
        if not isinstance(item, dict):
            continue
        flag = _flag(
            clean_text(item.get("code")) or f"{stage_id}_flag",
            severity=clean_text(item.get("severity")) or "warning",
            message=clean_text(item.get("message") or item.get("summary") or item.get("detail")),
            stageId=stage_id,
        )
        if flag:
            flags.append(flag)
    return flags


def _invoke_stage(
    *,
    stage_key: str,
    prompt_text: str,
    prompt_id: str,
    prompt_version: str,
    report_writer: Any,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    stage = STAGES[stage_key]
    system_prompt = (
        f"[report_stage:{stage.id}] [prompt:{prompt_id}@{prompt_version}]\n"
        f"{prompt_text.strip()}\n\n"
        "只返回一个 JSON 对象。不要输出 Markdown、代码块标记或额外解释。"
    )
    stage_input = {
        "stageId": stage.id,
        "promptId": prompt_id,
        "promptVersion": prompt_version,
        **payload,
    }
    try:
        response = report_writer.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(stage_input, ensure_ascii=False)},
            ]
        )
    except Exception as exc:
        raise ReportGenerationError(f"{stage.id} stage invocation failed: {exc}") from exc
    parsed = _extract_json_payload(response)
    if not isinstance(parsed, dict):
        raise ReportGenerationError(f"{stage.id} stage returned non-JSON output")
    trace = {
        "stageId": stage.id,
        "promptId": prompt_id,
        "promptVersion": prompt_version,
        "status": "completed",
        "outputKeys": sorted(parsed.keys()),
    }
    return parsed, trace


def _material_focus_default(material: dict[str, Any], *, index: int) -> str:
    detected_type = clean_text(material.get("detectedType")).lower()
    if detected_type in {"table", "metric"}:
        return "primary"
    if index == 0:
        return "primary"
    return "supporting"


def _normalize_intake_stage(
    raw_output: dict[str, Any],
    *,
    seed: dict[str, Any],
    fallback_title: str,
) -> dict[str, Any]:
    materials = [item for item in as_list(seed.get("materials")) if isinstance(item, dict)]
    if not materials:
        raise ReportGenerationError("report intake produced no usable materials")
    overlays = {
        clean_text(item.get("materialId")): item
        for item in as_list(raw_output.get("materials"))
        if isinstance(item, dict) and clean_text(item.get("materialId"))
    }
    merged_materials: list[dict[str, Any]] = []
    merged_flags = _normalize_stage_flags(raw_output.get("qualityFlags"), stage_id="intake")
    for index, material in enumerate(materials):
        overlay = overlays.get(clean_text(material.get("materialId")), {})
        detected_type = clean_text(overlay.get("detectedType")).lower()
        if detected_type not in MATERIAL_TYPES or detected_type == "auto":
            detected_type = clean_text(material.get("detectedType")).lower() or "text"
        report_use = clean_text(overlay.get("reportUse")).lower()
        if report_use not in {"primary", "supporting", "context"}:
            report_use = _material_focus_default(material, index=index)
        quality_flags = [
            *[flag for flag in as_list(material.get("qualityFlags")) if isinstance(flag, dict)],
            *_normalize_stage_flags(overlay.get("qualityFlags"), stage_id="intake"),
        ]
        merged_materials.append(
            drop_empty(
                {
                    **material,
                    "title": clean_text(overlay.get("title"), limit=160) or clean_text(material.get("title"), limit=160),
                    "detectedType": detected_type,
                    "summary": clean_text(overlay.get("summary"), limit=240),
                    "reportUse": report_use,
                    "qualityFlags": quality_flags,
                }
            )
        )
    title = clean_text(raw_output.get("title"), limit=160) or fallback_title
    return {
        "title": title or "分析报告",
        "materials": merged_materials,
        "qualityFlags": [*seed.get("qualityFlags", []), *merged_flags],
    }


def _normalize_reader_items(value: Any, *, prefix: str, default_title: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, item in enumerate(as_list(value), start=1):
        if not isinstance(item, dict):
            continue
        title = clean_text(
            item.get("title") or item.get("claim") or item.get("name") or item.get("action"),
            limit=100,
        ) or f"{default_title}{index}"
        summary = clean_text(
            item.get("summary")
            or item.get("readerSummary")
            or item.get("description")
            or item.get("basisSummary")
            or item.get("caption")
            or item.get("text"),
            limit=320,
        )
        if _looks_like_serialized_payload(summary):
            summary = f"{title}包含结构化数据，适合在表格或图表页中核对关键字段、数值变化与结构差异。"
        if not summary:
            continue
        items.append(
            drop_empty(
                {
                    "id": clean_text(item.get("id")) or f"{prefix}_{index}",
                    "title": title,
                    "summary": summary,
                    "rationale": clean_text(item.get("rationale"), limit=240),
                    "expectedBenefit": clean_text(item.get("expectedBenefit"), limit=200),
                    "riskNote": clean_text(item.get("riskNote"), limit=200),
                    "interpretationBoundary": clean_text(item.get("interpretationBoundary"), limit=220),
                    "basisSummary": clean_text(item.get("basisSummary"), limit=220),
                    "sourceDescription": clean_text(item.get("sourceDescription"), limit=200),
                    "verificationStatus": clean_text(item.get("verificationStatus"), limit=60),
                    "supportRelationship": clean_text(item.get("supportRelationship"), limit=200),
                    "evidenceRefs": string_list(item.get("evidenceRefs")),
                    "confidence": item.get("confidence"),
                    "chartId": clean_text(item.get("chartId")),
                    "dataRef": clean_text(item.get("dataRef")),
                }
            )
        )
    return items[:8]


def _sanitize_report_prose(value: Any, *, limit: int = 320) -> str:
    text = clean_text(value, limit=limit)
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(判断依据|关键依据|解读边界|表格边界|图表解读|视觉解读)\s*[:：]\s*", "", text)
    text = re.sub(r"^(本页|此页|这一页)[^。！？!?]{0,80}[。！？!?]\s*", "", text)
    return text.strip()


def _is_meta_paragraph(text: str) -> bool:
    normalized = clean_text(text, limit=220)
    if not normalized:
        return True
    if normalized in META_PARAGRAPH_TITLES:
        return True
    return bool(re.fullmatch(r"(本页|此页|这一页)[^。！？!?]{0,80}[。！？!?]?", normalized))


def _sanitize_item_title(value: Any) -> str:
    title = clean_text(value, limit=100)
    if title in META_ONLY_ITEM_TITLES:
        return ""
    return title


def _visual_item_role(item: dict[str, Any]) -> str:
    title = clean_text(item.get("title"), limit=100)
    if title in VISUAL_BASIS_TITLES:
        return "basis"
    if title in VISUAL_BOUNDARY_TITLES:
        return "boundary"
    return "narrative"


def _semantic_seed_story(title: str, seed_semantic: dict[str, Any]) -> dict[str, Any]:
    findings = _normalize_reader_items(seed_semantic.get("findings"), prefix="finding", default_title="关键发现")
    findings = findings or [
        {
            "id": "finding_1",
            "title": "材料概览",
            "summary": "当前材料可形成初步报告，但支撑结论的证据密度仍有限。",
            "interpretationBoundary": "仅基于本次提交的原文材料。",
        }
    ]
    time_ranges = string_list(seed_semantic.get("timeRanges"))
    visuals = build_chart_specs(seed_semantic)
    recommendations = [
        {
            "id": f"recommendation_{index}",
            "title": f"建议 {index}",
            "summary": f"优先围绕“{item.get('title') or '关键线索'}”补充原始数据、业务上下文或后续跟踪信息，再将其用于正式决策。",
            "basisSummary": item.get("summary"),
            "interpretationBoundary": "建议只对应当前材料可验证的范围。",
        }
        for index, item in enumerate(findings[:3], start=1)
    ]
    visual_narratives = [
        {
            "id": f"visual_{index}",
            "title": clean_text(chart.get("title"), limit=100) or f"图表 {index}",
            "summary": f"建议以 {clean_text(chart.get('type')) or '图表'} 方式呈现 {clean_text(chart.get('yField'))} 与 {clean_text(chart.get('xField'))} 的关系。",
            "chartId": clean_text(chart.get("chartId")),
            "dataRef": clean_text(chart.get("dataRef")),
            "interpretationBoundary": "图表只反映已提交结构化表格中的数据。",
        }
        for index, chart in enumerate(visuals[:3], start=1)
    ]
    return {
        "title": title,
        "presentationDecisions": {"exposeEvidencePage": False},
        "executiveJudgements": [
            {
                "id": "judgement_1",
                "title": "核心判断",
                "summary": findings[0]["summary"],
                "basisSummary": findings[0]["summary"],
                "interpretationBoundary": f"时间范围：{'、'.join(time_ranges[:2])}" if time_ranges else "仅基于当前输入材料。",
                "evidenceRefs": string_list(findings[0].get("evidenceRefs")),
            }
        ],
        "keyFindings": findings,
        "recommendations": recommendations,
        "visualNarratives": visual_narratives,
    }


def _subject_name_from_title(title: str) -> str:
    subject = clean_text(title)
    for suffix in ("分析报告", "机会报告", "风险报告", "报告", "分析"):
        if subject.endswith(suffix):
            subject = subject[: -len(suffix)].strip()
            break
    return subject


def _normalize_visual_opportunities(value: Any, *, tables: list[dict[str, Any]], fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table_ids = {clean_text(item.get("tableId")) for item in tables if isinstance(item, dict)}
    if not table_ids:
        return []
    items: list[dict[str, Any]] = []
    for index, item in enumerate(as_list(value), start=1):
        if not isinstance(item, dict):
            continue
        data_ref = clean_text(item.get("dataRef"))
        if not data_ref or data_ref not in table_ids:
            continue
        items.append(
            drop_empty(
                {
                    "opportunityId": clean_text(item.get("opportunityId")) or f"visual_{index}",
                    "type": clean_text(item.get("type")) or "bar_chart",
                    "title": clean_text(item.get("title"), limit=100) or f"图表机会 {index}",
                    "dataRef": data_ref,
                    "reason": clean_text(item.get("reason"), limit=180) or "grounded_table_selected",
                    "sourceMaterialId": clean_text(item.get("sourceMaterialId")),
                }
            )
        )
    return items or [dict(item) for item in fallback if isinstance(item, dict)]


def _normalize_semantic_stage(
    raw_output: dict[str, Any],
    *,
    seed: dict[str, Any],
    title: str,
    goal: str,
    audience: str,
) -> dict[str, Any]:
    seed_semantic = as_dict(seed.get("semanticModel"))
    if not seed_semantic:
        raise ReportGenerationError("semantic normalization seed is unavailable")
    semantic_payload = as_dict(raw_output.get("semanticModel"))
    if not semantic_payload:
        raise ReportGenerationError("semantic normalization stage returned no semantic model")
    seed_story = _semantic_seed_story(title, seed_semantic)
    tables = [item for item in as_list(seed_semantic.get("tables")) if isinstance(item, dict)]
    metrics = [item for item in as_list(seed_semantic.get("metrics")) if isinstance(item, dict)]
    evidence_refs = [item for item in as_list(seed_semantic.get("evidenceRefs")) if isinstance(item, dict)]
    visual_opportunities = _normalize_visual_opportunities(
        semantic_payload.get("visualOpportunities"),
        tables=tables,
        fallback=[item for item in as_list(seed_semantic.get("visualOpportunities")) if isinstance(item, dict)],
    )
    time_ranges = string_list(semantic_payload.get("timeRanges")) or string_list(seed_semantic.get("timeRanges"))
    seed_presentation = as_dict(seed_story.get("presentationDecisions"))
    raw_presentation = as_dict(semantic_payload.get("presentationDecisions"))
    key_findings = _normalize_reader_items(
        semantic_payload.get("keyFindings") or semantic_payload.get("findings") or seed_story["keyFindings"],
        prefix="finding",
        default_title="关键发现",
    )
    semantic_model = drop_empty(
        {
            "schemaVersion": "paginated_report_semantic_model.v2",
            "createdAt": utc_now_iso(),
            "title": clean_text(semantic_payload.get("title"), limit=160) or title,
            "reportIntent": {
                "goal": clean_text(semantic_payload.get("goal"), limit=220) or clean_text(goal, limit=220),
                "audience": clean_text(semantic_payload.get("audience"), limit=120) or clean_text(audience, limit=120),
                "language": "zh-CN",
                "outputStyle": "decision_report",
            },
            "subject": {
                "name": clean_text(as_dict(semantic_payload.get("subject")).get("name"), limit=120)
                or _subject_name_from_title(title),
                "stockCode": clean_text(as_dict(semantic_payload.get("subject")).get("stockCode"), limit=40),
            },
            "scope": {
                "timeRange": clean_text(as_dict(semantic_payload.get("scope")).get("timeRange"), limit=120)
                or "、".join(time_ranges[:2]),
                "analysisFocus": clean_text(as_dict(semantic_payload.get("scope")).get("analysisFocus"), limit=180)
                or clean_text(goal, limit=180),
                "status": "grounded",
            },
            "presentationDecisions": {
                "exposeEvidencePage": _as_bool(
                    raw_presentation.get("exposeEvidencePage")
                    if "exposeEvidencePage" in raw_presentation
                    else seed_presentation.get("exposeEvidencePage")
                ),
            },
            "executiveJudgements": _normalize_reader_items(
                semantic_payload.get("executiveJudgements") or seed_story["executiveJudgements"],
                prefix="judgement",
                default_title="核心判断",
            ),
            "keyFindings": key_findings,
            "findings": key_findings,
            "recommendations": _normalize_reader_items(
                semantic_payload.get("recommendations") or seed_story["recommendations"],
                prefix="recommendation",
                default_title="建议",
            ),
            "visualNarratives": _normalize_reader_items(
                semantic_payload.get("visualNarratives") or seed_story["visualNarratives"],
                prefix="visual",
                default_title="图表解读",
            ),
            "metrics": metrics,
            "tables": tables,
            "evidenceRefs": evidence_refs,
            "visualOpportunities": visual_opportunities,
            "entities": string_list(semantic_payload.get("entities")) or string_list(seed_semantic.get("entities")),
            "timeRanges": time_ranges,
            "qualityFlags": [
                *[flag for flag in as_list(seed_semantic.get("qualityFlags")) if isinstance(flag, dict)],
                *_normalize_stage_flags(raw_output.get("qualityFlags"), stage_id="normalization"),
                *_normalize_stage_flags(semantic_payload.get("qualityFlags"), stage_id="normalization"),
            ],
        }
    )
    if not semantic_model.get("executiveJudgements") or not semantic_model.get("keyFindings"):
        raise ReportGenerationError("semantic normalization stage did not yield enough grounded findings")
    return {
        "semanticModel": semantic_model,
        "qualityFlags": [*seed.get("qualityFlags", []), *as_list(semantic_model.get("qualityFlags"))],
    }


def _normalize_chapter_id(value: Any, *, index: int) -> str:
    chapter_id = clean_text(value, limit=40).lower()
    chapter_id = re.sub(r"[^a-z0-9_]+", "_", chapter_id).strip("_")
    return chapter_id or f"chapter_{index}"


def _should_include_evidence_chapter(semantic_model: dict[str, Any]) -> bool:
    decisions = as_dict(semantic_model.get("presentationDecisions"))
    if not _as_bool(decisions.get("exposeEvidencePage")):
        return False
    return bool([item for item in as_list(semantic_model.get("evidenceRefs")) if isinstance(item, dict)])


def _default_page_type(*, section_ids: list[str], chart_refs: list[str], table_refs: list[str]) -> str:
    if chart_refs:
        return "chart_analysis"
    if table_refs:
        return "table_analysis"
    if "executive_judgement" in section_ids:
        return "executive_summary"
    if "recommendations" in section_ids:
        return "recommendation"
    return "insight"


def _safe_page_type(value: Any, *, section_ids: list[str], chart_refs: list[str], table_refs: list[str]) -> str:
    page_type = clean_text(value, limit=40)
    if page_type not in PAGE_TYPES:
        page_type = _default_page_type(section_ids=section_ids, chart_refs=chart_refs, table_refs=table_refs)
    return page_type


def _default_layout_for_page_type(page_type: str) -> str:
    return PAGE_TYPE_LAYOUTS.get(page_type, "title_text")


def _safe_layout(value: Any, *, page_type: str) -> str:
    layout = clean_text(value, limit=60)
    if layout not in APPROVED_LAYOUTS:
        layout = _default_layout_for_page_type(page_type)
    return layout


def _legacy_chapter_blueprint(
    chapter_id: str,
    *,
    chart_refs: list[str],
    table_refs: list[str],
) -> dict[str, Any]:
    blueprint = dict(LEGACY_CHAPTER_BLUEPRINTS.get(chapter_id) or {})
    if not blueprint:
        return {}
    if chapter_id == "visuals":
        blueprint["chartRefs"] = list(chart_refs)
    if chapter_id == "tables":
        blueprint["tableRefs"] = list(table_refs)
    return blueprint


def _suggested_chapter_plan(semantic_model: dict[str, Any]) -> list[dict[str, Any]]:
    chart_refs = [
        clean_text(item.get("chartId"))
        for item in build_chart_specs(semantic_model)
        if isinstance(item, dict) and clean_text(item.get("chartId"))
    ]
    table_refs = [
        clean_text(item.get("tableId"))
        for item in as_list(semantic_model.get("tables"))
        if isinstance(item, dict) and clean_text(item.get("tableId"))
    ]
    plan: list[dict[str, Any]] = []
    if as_list(semantic_model.get("executiveJudgements")):
        plan.append(
            {
                "chapterId": "chapter_summary",
                "title": "执行摘要",
                "pageType": "executive_summary",
                "layout": "title_text",
                "sectionIds": ["executive_judgement"],
            }
        )
    combined_sections: list[str] = []
    if as_list(semantic_model.get("keyFindings")):
        combined_sections.append("key_findings")
    if combined_sections:
        plan.append(
            {
                "chapterId": "chapter_findings",
                "title": "关键发现",
                "pageType": "insight",
                "layout": "title_text",
                "sectionIds": combined_sections,
            }
        )
    if chart_refs or table_refs:
        plan.append(
            {
                "chapterId": "chapter_data",
                "title": "趋势与结构观察" if chart_refs else "关键数据摘录",
                "pageType": "chart_analysis" if chart_refs else "table_analysis",
                "layout": "title_chart_notes" if chart_refs else "title_table_notes",
                "sectionIds": ["model_visual_interpretation"],
                "chartRefs": chart_refs,
                "tableRefs": table_refs,
            }
        )
    if _should_include_evidence_chapter(semantic_model):
        plan.append(
            {
                "chapterId": "chapter_evidence",
                "title": "证据与来源",
                "pageType": "evidence",
                "layout": "evidence_list",
                "sectionIds": ["evidence_verification"],
            }
        )
    if as_list(semantic_model.get("recommendations")):
        plan.append(
            {
                "chapterId": "chapter_recommendations",
                "title": "建议与行动",
                "pageType": "recommendation",
                "layout": "title_text",
                "sectionIds": ["recommendations"],
            }
        )
    return plan


def _normalize_chapter_plan(raw_output: dict[str, Any], *, semantic_model: dict[str, Any]) -> dict[str, Any]:
    suggested_plan = _suggested_chapter_plan(semantic_model)
    allow_evidence_chapter = _should_include_evidence_chapter(semantic_model)
    chart_specs = [item for item in build_chart_specs(semantic_model) if isinstance(item, dict)]
    chart_refs = [
        clean_text(item.get("chartId"))
        for item in chart_specs
        if clean_text(item.get("chartId"))
    ]
    chart_id_by_data_ref = {
        clean_text(item.get("dataRef")): clean_text(item.get("chartId"))
        for item in chart_specs
        if clean_text(item.get("dataRef")) and clean_text(item.get("chartId"))
    }
    chart_ref_aliases = {ref: ref for ref in chart_refs}
    for item in as_list(semantic_model.get("visualOpportunities")):
        if not isinstance(item, dict):
            continue
        opportunity_id = clean_text(item.get("opportunityId"))
        mapped_chart_id = chart_id_by_data_ref.get(clean_text(item.get("dataRef")), "")
        if opportunity_id and mapped_chart_id:
            chart_ref_aliases[opportunity_id] = mapped_chart_id
    table_refs = [
        clean_text(item.get("tableId"))
        for item in as_list(semantic_model.get("tables"))
        if isinstance(item, dict) and clean_text(item.get("tableId"))
    ]
    chapters: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(as_list(raw_output.get("chapters")), start=1):
        if not isinstance(item, dict):
            continue
        legacy = _legacy_chapter_blueprint(clean_text(item.get("chapterId")), chart_refs=chart_refs, table_refs=table_refs)
        section_ids = [section_id for section_id in string_list(item.get("sectionIds")) if section_id in ALLOWED_SECTION_IDS]
        if not section_ids:
            section_ids = [section_id for section_id in string_list(legacy.get("sectionIds")) if section_id in ALLOWED_SECTION_IDS]
        if not allow_evidence_chapter:
            section_ids = [section_id for section_id in section_ids if section_id != "evidence_verification"]
        chapter_chart_refs: list[str] = []
        for ref in string_list(item.get("chartRefs")) or string_list(legacy.get("chartRefs")):
            mapped_ref = chart_ref_aliases.get(ref, "")
            if mapped_ref and mapped_ref not in chapter_chart_refs:
                chapter_chart_refs.append(mapped_ref)
        chapter_table_refs = [ref for ref in string_list(item.get("tableRefs")) or string_list(legacy.get("tableRefs")) if ref in table_refs]
        if not (section_ids or chapter_chart_refs or chapter_table_refs):
            continue
        if (chapter_chart_refs or chapter_table_refs) and "model_visual_interpretation" not in section_ids:
            section_ids.append("model_visual_interpretation")
        chapter_id = _normalize_chapter_id(item.get("chapterId"), index=index)
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        page_type = _safe_page_type(
            item.get("pageType") or legacy.get("pageType"),
            section_ids=section_ids,
            chart_refs=chapter_chart_refs,
            table_refs=chapter_table_refs,
        )
        if chapter_chart_refs:
            page_type = "chart_analysis"
        elif chapter_table_refs:
            page_type = "table_analysis"
        layout = _safe_layout(item.get("layout") or legacy.get("layout"), page_type=page_type)
        title = clean_text(item.get("title"), limit=80) or clean_text(legacy.get("title"), limit=80)
        if not title:
            title = f"章节 {len(chapters) + 1}"
        if title in FORBIDDEN_TAIL_CHAPTER_TITLES:
            continue
        chapters.append(
            drop_empty(
                {
                    "chapterId": chapter_id,
                    "title": title,
                    "pageType": page_type,
                    "layout": layout,
                    "notes": clean_text(item.get("notes"), limit=240),
                    "sectionIds": section_ids,
                    "chartRefs": chapter_chart_refs,
                    "tableRefs": chapter_table_refs,
                }
            )
        )
    if not chapters:
        chapters = [dict(item) for item in suggested_plan]
    if not chapters:
        raise ReportGenerationError("page planning stage returned no usable chapters")
    chapter_outline = [
        {
            "id": chapter["chapterId"],
            "title": chapter["title"],
            "pageType": chapter["pageType"],
        }
        for chapter in chapters
    ]
    return {
        "chapterPlan": chapters,
        "chapterOutline": chapter_outline,
        "qualityFlags": _normalize_stage_flags(raw_output.get("qualityFlags"), stage_id="page_planning"),
    }


def _default_page_designs(chapter_plan: list[dict[str, Any]], *, chart_specs: list[dict[str, Any]], tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table_ids = {clean_text(item.get("tableId")) for item in tables if isinstance(item, dict) and clean_text(item.get("tableId"))}
    chart_ids = {clean_text(item.get("chartId")) for item in chart_specs if isinstance(item, dict) and clean_text(item.get("chartId"))}
    designs: list[dict[str, Any]] = []
    for chapter in chapter_plan:
        chapter_id = clean_text(chapter.get("chapterId"))
        page_type = clean_text(chapter.get("pageType"), limit=40)
        design = drop_empty(
            {
                "chapterId": chapter_id,
                "layout": clean_text(chapter.get("layout"), limit=60),
                "styleTokens": {"accentColor": PAGE_TYPE_ACCENTS.get(page_type, "primary")},
                "chartRefs": [ref for ref in string_list(chapter.get("chartRefs")) if ref in chart_ids],
                "tableRefs": [ref for ref in string_list(chapter.get("tableRefs")) if ref in table_ids],
            }
        )
        designs.append(design)
    return designs


def _normalize_chart_specs(raw_output: dict[str, Any], *, semantic_model: dict[str, Any]) -> list[dict[str, Any]]:
    default_specs = build_chart_specs(semantic_model)
    if not default_specs:
        return []
    default_by_ref = {clean_text(item.get("dataRef")): item for item in default_specs if isinstance(item, dict)}
    tables_by_ref = {
        clean_text(item.get("tableId")): item
        for item in as_list(semantic_model.get("tables"))
        if isinstance(item, dict) and clean_text(item.get("tableId"))
    }
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(as_list(raw_output.get("chartSpecs")), start=1):
        if not isinstance(item, dict):
            continue
        data_ref = clean_text(item.get("dataRef"))
        base = dict(default_by_ref.get(data_ref) or {})
        if not base:
            continue
        x_field = clean_text(item.get("xField")) or clean_text(base.get("xField"))
        y_field = clean_text(item.get("yField")) or clean_text(base.get("yField"))
        rows = [row for row in as_list(as_dict(tables_by_ref.get(data_ref)).get("rows")) if isinstance(row, dict)]
        chart_type = clean_text(item.get("type")) or clean_text(base.get("type")) or "bar_chart"
        if looks_temporal_chart_axis(x_field, rows):
            chart_type = "line_chart"
        normalized.append(
            drop_empty(
                {
                    **base,
                    "chartId": clean_text(item.get("chartId")) or clean_text(base.get("chartId")) or f"chart_{index}",
                    "type": chart_type,
                    "title": clean_text(item.get("title"), limit=100) or clean_text(base.get("title"), limit=100),
                    "xField": x_field,
                    "yField": y_field,
                    "styleTokens": as_dict(item.get("styleTokens")) or as_dict(base.get("styleTokens")),
                }
            )
        )
    return normalized or default_specs


def _normalize_visual_stage(
    raw_output: dict[str, Any],
    *,
    chapter_plan: list[dict[str, Any]],
    semantic_model: dict[str, Any],
) -> dict[str, Any]:
    chart_specs = _normalize_chart_specs(raw_output, semantic_model=semantic_model)
    tables = [item for item in as_list(semantic_model.get("tables")) if isinstance(item, dict)]
    default_designs = _default_page_designs(chapter_plan, chart_specs=chart_specs, tables=tables)
    default_lookup = {clean_text(item.get("chapterId")): item for item in default_designs}
    chart_ids = {clean_text(item.get("chartId")) for item in chart_specs if isinstance(item, dict)}
    table_ids = {clean_text(item.get("tableId")) for item in tables if isinstance(item, dict)}
    page_designs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in as_list(raw_output.get("pageDesigns")):
        if not isinstance(item, dict):
            continue
        chapter_id = clean_text(item.get("chapterId"))
        base = dict(default_lookup.get(chapter_id) or {})
        if not base or chapter_id in seen:
            continue
        seen.add(chapter_id)
        style_tokens = as_dict(item.get("styleTokens")) or as_dict(base.get("styleTokens"))
        page_designs.append(
            drop_empty(
                {
                    **base,
                    "layout": _safe_layout(item.get("layout") or base.get("layout"), page_type=clean_text(base.get("pageType"), limit=40) or "insight"),
                    "styleTokens": style_tokens,
                    "chartRefs": [
                        ref for ref in string_list(item.get("chartRefs")) if ref in chart_ids
                    ]
                    or [ref for ref in string_list(base.get("chartRefs")) if ref in chart_ids],
                    "tableRefs": [
                        ref for ref in string_list(item.get("tableRefs")) if ref in table_ids
                    ]
                    or [ref for ref in string_list(base.get("tableRefs")) if ref in table_ids],
                    "lead": clean_text(item.get("lead"), limit=220),
                    "caption": clean_text(item.get("caption"), limit=220),
                }
            )
        )
    for item in default_designs:
        chapter_id = clean_text(item.get("chapterId"))
        if chapter_id not in seen:
            page_designs.append(item)
    return {
        "chartSpecs": chart_specs,
        "pageDesigns": page_designs,
        "qualityFlags": _normalize_stage_flags(raw_output.get("qualityFlags"), stage_id="visual_design"),
    }


def _normalize_writer_item(item: dict[str, Any]) -> dict[str, Any]:
    return drop_empty(
        {
            "title": _sanitize_item_title(item.get("title") or item.get("claim") or item.get("name") or item.get("action")),
            "readerSummary": _sanitize_report_prose(
                item.get("readerSummary")
                or item.get("summary")
                or item.get("description")
                or item.get("basisSummary")
                or item.get("caption")
                or item.get("text"),
                limit=300,
            ),
            "basisSummary": _sanitize_report_prose(item.get("basisSummary"), limit=220),
            "rationale": _sanitize_report_prose(item.get("rationale"), limit=220),
            "expectedBenefit": _sanitize_report_prose(item.get("expectedBenefit"), limit=220),
            "riskNote": _sanitize_report_prose(item.get("riskNote"), limit=220),
            "interpretationBoundary": _sanitize_report_prose(item.get("interpretationBoundary"), limit=220),
            "verificationStatus": clean_text(item.get("verificationStatus"), limit=80),
            "sourceDescription": _sanitize_report_prose(item.get("sourceDescription"), limit=220),
            "supportRelationship": _sanitize_report_prose(item.get("supportRelationship"), limit=220),
            "chartId": clean_text(item.get("chartId")),
            "dataRef": clean_text(item.get("dataRef")),
        }
    )


def _normalize_writer_blocks(value: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for item in as_list(value):
        if not isinstance(item, dict):
            continue
        block_type = clean_text(item.get("type"))
        if block_type == "paragraph":
            text = _sanitize_report_prose(item.get("text"), limit=900)
            if text and not _is_meta_paragraph(text):
                blocks.append({"type": "paragraph", "text": text})
            continue
        if block_type in {"items", "evidence", "visuals"}:
            normalized_items = [_normalize_writer_item(entry) for entry in as_list(item.get("items")) if isinstance(entry, dict)]
            normalized_items = [entry for entry in normalized_items if entry]
            if normalized_items:
                blocks.append({"type": block_type, "items": normalized_items})
    return blocks


def _normalize_writer_sections(raw_output: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    title = clean_text(raw_output.get("title"), limit=160)
    flags = _normalize_stage_flags(raw_output.get("qualityFlags"), stage_id="writing")
    sections: list[dict[str, Any]] = []
    for section in as_list(raw_output.get("sections")):
        if not isinstance(section, dict):
            continue
        section_id = clean_text(section.get("id"))
        section_title = clean_text(section.get("title"), limit=100)
        if section_id not in ALLOWED_SECTION_IDS or not section_title:
            continue
        blocks = _normalize_writer_blocks(section.get("blocks"))
        if not blocks:
            continue
        sections.append({"id": section_id, "title": section_title, "blocks": blocks})
    return title, sections, flags


def _sections_markdown(title: str, sections: list[dict[str, Any]]) -> str:
    lines = [f"# {title}", ""]
    for section in sections:
        lines.extend([f"## {clean_text(section.get('title'))}", ""])
        for block in as_list(section.get("blocks")):
            if not isinstance(block, dict):
                continue
            block_type = clean_text(block.get("type"))
            if block_type == "paragraph":
                lines.extend([clean_text(block.get("text")), ""])
            elif block_type in {"items", "evidence", "visuals"}:
                for item in as_list(block.get("items")):
                    if not isinstance(item, dict):
                        continue
                    summary = clean_text(item.get("readerSummary") or item.get("basisSummary"))
                    lines.append(f"- {clean_text(item.get('title'))}: {summary}".rstrip(": "))
                lines.append("")
    return "\n".join(lines).strip() + "\n"


def _forbidden_values(materials: list[dict[str, Any]], source_context: dict[str, Any]) -> list[str]:
    values: set[str] = set()
    for material in materials:
        if not isinstance(material, dict):
            continue
        values.add(clean_text(material.get("materialId")))
        values.add(clean_text(as_dict(material.get("source")).get("id")))
        metadata = as_dict(material.get("metadata"))
        for key in ("moduleId", "moduleRunId", "analysisSessionId", "conversationId", "artifactId"):
            values.add(clean_text(metadata.get(key)))
    for key in ("sourceReportId", "analysisSessionId", "conversationId"):
        values.add(clean_text(source_context.get(key)))
    return [item for item in values if len(item) >= 4]


def _section_has_paragraph(section: dict[str, Any]) -> bool:
    return any(
        isinstance(block, dict) and clean_text(block.get("type")) == "paragraph" and clean_text(block.get("text"), limit=900)
        for block in as_list(section.get("blocks"))
    )


def _visual_section_items(section: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for block in as_list(section.get("blocks")):
        if not isinstance(block, dict):
            continue
        if clean_text(block.get("type")) not in {"visuals", "items"}:
            continue
        for entry in as_list(block.get("items")):
            if not isinstance(entry, dict):
                continue
            normalized = _normalize_writer_item(entry)
            summary = _sanitize_report_prose(normalized.get("readerSummary"), limit=260)
            basis = _sanitize_report_prose(normalized.get("basisSummary"), limit=220)
            boundary = _sanitize_report_prose(normalized.get("interpretationBoundary"), limit=220)
            role = _visual_item_role(normalized)
            lead = summary if role == "narrative" else ""
            follow_up = _join_report_sentences(
                summary if role in {"basis", "boundary"} else "",
                basis,
                boundary,
            )
            if not lead and not follow_up:
                continue
            items.append(
                {
                    "title": _sanitize_item_title(normalized.get("title")) or "图表",
                    "chartId": clean_text(normalized.get("chartId")),
                    "dataRef": clean_text(normalized.get("dataRef")),
                    "summary": lead,
                    "followUp": follow_up,
                }
            )
    return items


def _looks_like_serialized_payload(value: str) -> bool:
    text = clean_text(value, limit=500)
    if not text:
        return False
    if (text.startswith("[") or text.startswith("{")) and any(marker in text for marker in ('":', "':")):
        return True
    return text.count('{"') >= 2 or text.count("}, {") >= 1


def _validate_written_output(
    title: str,
    sections: list[dict[str, Any]],
    *,
    chapter_plan: list[dict[str, Any]],
    materials: list[dict[str, Any]],
    source_context: dict[str, Any],
) -> None:
    if not any(section.get("id") == "executive_judgement" for section in sections):
        raise ReportGenerationError("narrative writing stage omitted executive judgement")
    if not any(section.get("id") in {"key_findings", "recommendations", "model_visual_interpretation"} for section in sections):
        raise ReportGenerationError("narrative writing stage omitted key reader-facing sections")
    sections_by_id = _section_lookup(sections)
    required_paragraph_sections = {"executive_judgement", "key_findings", "model_visual_interpretation", "recommendations"}
    referenced_section_ids = {
        section_id
        for chapter in chapter_plan
        if isinstance(chapter, dict)
        for section_id in string_list(chapter.get("sectionIds"))
        if section_id in required_paragraph_sections
    }
    for section_id in sorted(referenced_section_ids):
        section = sections_by_id.get(section_id)
        if not section or not _section_has_paragraph(section):
            raise ReportGenerationError(f"narrative writing stage omitted prose paragraphs for {section_id}")
    referenced_chart_refs: list[str] = []
    referenced_table_refs: list[str] = []
    for chapter in chapter_plan:
        if not isinstance(chapter, dict):
            continue
        for ref in string_list(chapter.get("chartRefs")):
            if ref not in referenced_chart_refs:
                referenced_chart_refs.append(ref)
        for ref in string_list(chapter.get("tableRefs")):
            if ref not in referenced_table_refs:
                referenced_table_refs.append(ref)
    if referenced_chart_refs or referenced_table_refs:
        visual_items = _visual_section_items(sections_by_id.get("model_visual_interpretation") or {})
        covered_chart_refs = {
            clean_text(item.get("chartId"))
            for item in visual_items
            if clean_text(item.get("chartId"))
        }
        covered_table_refs = {
            clean_text(item.get("dataRef"))
            for item in visual_items
            if clean_text(item.get("dataRef")) and not clean_text(item.get("chartId"))
        }
        missing_chart_refs = [ref for ref in referenced_chart_refs if ref not in covered_chart_refs]
        missing_table_refs = [ref for ref in referenced_table_refs if ref not in covered_table_refs]
        if missing_chart_refs:
            raise ReportGenerationError(
                "narrative writing stage omitted chart-bound prose for refs: " + ", ".join(missing_chart_refs[:5])
            )
        if missing_table_refs:
            raise ReportGenerationError(
                "narrative writing stage omitted table-bound prose for refs: " + ", ".join(missing_table_refs[:5])
            )
    errors = validate_published_report(
        _sections_markdown(title, sections),
        forbidden_values=_forbidden_values(materials, source_context),
    )
    if errors:
        raise ReportGenerationError("narrative writing stage failed publication validation: " + "；".join(errors[:5]))


def _chapter_packet(chapter_plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        drop_empty(
            {
                "chapterId": clean_text(item.get("chapterId")),
                "title": clean_text(item.get("title"), limit=80),
                "pageType": clean_text(item.get("pageType"), limit=40),
                "layout": clean_text(item.get("layout"), limit=40),
                "notes": clean_text(item.get("notes"), limit=220),
                "sectionIds": [section_id for section_id in string_list(item.get("sectionIds")) if section_id in ALLOWED_SECTION_IDS],
                "chartRefs": string_list(item.get("chartRefs")),
                "tableRefs": string_list(item.get("tableRefs")),
            }
        )
        for item in chapter_plan
        if isinstance(item, dict)
    ]


def _build_writing_packet(semantic_model: dict[str, Any]) -> dict[str, Any]:
    subject = as_dict(semantic_model.get("subject"))
    scope = as_dict(semantic_model.get("scope"))
    intent = as_dict(semantic_model.get("reportIntent"))
    return drop_empty(
        {
            "报告标题": clean_text(semantic_model.get("title"), limit=160),
            "主体": {
                "名称": clean_text(subject.get("name"), limit=120),
                "股票代码": clean_text(subject.get("stockCode"), limit=40),
            },
            "范围": {
                "时间范围": clean_text(scope.get("timeRange"), limit=120),
                "分析重点": clean_text(scope.get("analysisFocus"), limit=180),
                "报告目标": clean_text(intent.get("goal"), limit=220),
                "读者对象": clean_text(intent.get("audience"), limit=120),
            },
            "核心判断": _normalize_reader_items(
                semantic_model.get("executiveJudgements"), prefix="judgement", default_title="核心判断"
            ),
            "关键发现": _normalize_reader_items(
                semantic_model.get("keyFindings"), prefix="finding", default_title="关键发现"
            ),
            "来源与核验": _normalize_reader_items(
                semantic_model.get("evidenceRefs"), prefix="evidence", default_title="证据来源"
            ),
            "图表解读": _normalize_reader_items(
                semantic_model.get("visualNarratives"), prefix="visual", default_title="图表解读"
            ),
            "图表规划": [
                drop_empty(
                    {
                        "chartId": clean_text(item.get("chartId")),
                        "title": clean_text(item.get("title"), limit=100),
                        "dataRef": clean_text(item.get("dataRef")),
                        "type": clean_text(item.get("type"), limit=40),
                        "xField": clean_text(item.get("xField"), limit=60),
                        "yField": clean_text(item.get("yField"), limit=60),
                    }
                )
                for item in build_chart_specs(semantic_model)
                if isinstance(item, dict)
            ],
            "数据表": [
                drop_empty(
                    {
                        "tableId": clean_text(item.get("tableId")),
                        "title": clean_text(item.get("title"), limit=100),
                        "rowCount": len([row for row in as_list(item.get("rows")) if isinstance(row, dict)]),
                        "columns": [
                            clean_text(column.get("label") or column.get("key"), limit=60)
                            for column in as_list(item.get("columns"))
                            if isinstance(column, dict) and clean_text(column.get("label") or column.get("key"), limit=60)
                        ][:8],
                    }
                )
                for item in as_list(semantic_model.get("tables"))
                if isinstance(item, dict)
            ],
            "建议": _normalize_reader_items(
                semantic_model.get("recommendations"), prefix="recommendation", default_title="建议"
            ),
        }
    )


def _section_lookup(sections: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {clean_text(item.get("id")): item for item in sections if isinstance(item, dict)}


def _section_evidence_refs(section: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for block in as_list(section.get("blocks")):
        if not isinstance(block, dict):
            continue
        for item in as_list(block.get("items")):
            if not isinstance(item, dict):
                continue
            for ref in string_list(item.get("evidenceRefs")):
                if ref not in refs:
                    refs.append(ref)
    return refs


def _writer_blocks_to_page_blocks(section: dict[str, Any], *, title_hint: str = "") -> list[dict[str, Any]]:
    page_blocks: list[dict[str, Any]] = []
    for block in as_list(section.get("blocks")):
        if not isinstance(block, dict):
            continue
        block_type = clean_text(block.get("type"))
        if block_type == "paragraph":
            text = _sanitize_report_prose(block.get("text"), limit=900)
            if text and not _is_meta_paragraph(text):
                page_blocks.append({"type": "paragraph", "text": text})
            continue
        if block_type == "items":
            items = [
                drop_empty(
                    {
                        "title": _sanitize_item_title(item.get("title")),
                        "summary": _sanitize_report_prose(item.get("readerSummary"), limit=260),
                    }
                )
                for item in as_list(block.get("items"))
                if isinstance(item, dict) and _sanitize_report_prose(item.get("readerSummary"), limit=260)
            ]
            if items:
                page_blocks.append(drop_empty({"type": "items", "title": title_hint, "items": items}))
            continue
        if block_type == "evidence":
            items = [
                drop_empty(
                    {
                        "title": _sanitize_item_title(item.get("title")),
                        "summary": _sanitize_report_prose(item.get("readerSummary") or item.get("sourceDescription"), limit=260),
                    }
                )
                for item in as_list(block.get("items"))
                if isinstance(item, dict)
            ]
            if items:
                page_blocks.append({"type": "evidence", "items": items})
            continue
        if block_type == "visuals":
            items = [
                drop_empty(
                    {
                        "title": _sanitize_item_title(item.get("title")),
                        "summary": _sanitize_report_prose(item.get("readerSummary") or item.get("caption"), limit=260),
                    }
                )
                for item in as_list(block.get("items"))
                if isinstance(item, dict)
            ]
            if items:
                page_blocks.append(drop_empty({"type": "items", "title": title_hint or "视觉解读", "items": items}))
    return page_blocks


def _ensure_chapter_narrative(page_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return page_blocks


def _section_paragraph_blocks(section: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in as_list(section.get("blocks")):
        if not isinstance(block, dict):
            continue
        if clean_text(block.get("type")) != "paragraph":
            continue
        text = _sanitize_report_prose(block.get("text"), limit=900)
        if text and not _is_meta_paragraph(text):
            blocks.append({"type": "paragraph", "text": text})
    return blocks


def _visual_insights(section: dict[str, Any]) -> list[dict[str, str]]:
    return _visual_section_items(section)


def _join_report_sentences(*parts: str) -> str:
    sentences = [clean_text(part, limit=260).rstrip("。；;，, ") for part in parts if clean_text(part, limit=260)]
    if not sentences:
        return ""
    return "。".join(sentences) + "。"


def _batched(items: list[Any], size: int) -> list[list[Any]]:
    if size <= 0:
        return [items]
    return [items[index : index + size] for index in range(0, len(items), size)]


def _batched_tables(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_rows = 0
    for item in items:
        row_count = min(len([row for row in as_list(item.get("rows")) if isinstance(row, dict)]), 8)
        if current and (len(current) >= 2 or current_rows + row_count > 8):
            batches.append(current)
            current = []
            current_rows = 0
        current.append(item)
        current_rows += row_count
    if current:
        batches.append(current)
    return batches


def _page_style_tokens(design: dict[str, Any], *, page_type: str) -> dict[str, Any]:
    tokens = as_dict(design.get("styleTokens"))
    if not clean_text(tokens.get("accentColor")):
        tokens["accentColor"] = PAGE_TYPE_ACCENTS.get(page_type, "primary")
    return tokens


def _compose_cover_page(
    *,
    title: str,
    render_style: str,
    semantic_model: dict[str, Any],
    materials: list[dict[str, Any]],
    executive_section: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "id": "page_cover",
        "pageNumber": 1,
        "pageType": "cover",
        "type": "cover",
        "title": "封面",
        "tocEntry": False,
        "layout": "cover",
        "blocks": [{"type": "hero", "title": title}],
        "styleTokens": {"accentColor": "primary"},
    }


def _compose_body_pages(
    *,
    chapter_plan: list[dict[str, Any]],
    page_designs: list[dict[str, Any]],
    chart_specs: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    semantic_model: dict[str, Any],
) -> list[dict[str, Any]]:
    designs_by_chapter = {clean_text(item.get("chapterId")): item for item in page_designs if isinstance(item, dict)}
    sections_by_id = _section_lookup(sections)
    visual_section = sections_by_id.get("model_visual_interpretation") or {}
    evidence_items = [item for item in as_list(semantic_model.get("evidenceRefs")) if isinstance(item, dict)]
    evidence_by_source = {
        clean_text(item.get("sourceMaterialId")): clean_text(item.get("evidenceId"))
        for item in evidence_items
        if clean_text(item.get("sourceMaterialId")) and clean_text(item.get("evidenceId"))
    }
    tables = [item for item in as_list(semantic_model.get("tables")) if isinstance(item, dict)]
    metrics = [item for item in as_list(semantic_model.get("metrics")) if isinstance(item, dict)]
    visual_insights = _visual_insights(visual_section)
    charts_by_id = {
        clean_text(item.get("chartId")): item for item in chart_specs if isinstance(item, dict) and clean_text(item.get("chartId"))
    }
    tables_by_id = {
        clean_text(item.get("tableId")): item for item in tables if isinstance(item, dict) and clean_text(item.get("tableId"))
    }
    body_pages: list[dict[str, Any]] = []
    visual_intro_consumed = False
    data_chapter_count = sum(
        1
        for chapter in chapter_plan
        if isinstance(chapter, dict) and (string_list(chapter.get("chartRefs")) or string_list(chapter.get("tableRefs")))
    )

    def chapter_sections(chapter: dict[str, Any]) -> list[str]:
        return [section_id for section_id in string_list(chapter.get("sectionIds")) if section_id in ALLOWED_SECTION_IDS]

    def chapter_intro_blocks(chapter: dict[str, Any], *, include_visual_section: bool = False) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        if include_visual_section:
            section = sections_by_id.get("model_visual_interpretation") or {}
            if not visual_intro_consumed:
                visual_blocks = _section_paragraph_blocks(section)
                if data_chapter_count > 1:
                    visual_blocks = visual_blocks[:1]
                blocks.extend(visual_blocks)
            return _ensure_chapter_narrative(blocks)
        for section_id in chapter_sections(chapter):
            section = sections_by_id.get(section_id) or {}
            if section_id == "model_visual_interpretation":
                continue
            blocks.extend(_writer_blocks_to_page_blocks(section, title_hint=clean_text(chapter.get("title"))))
        return _ensure_chapter_narrative(blocks)

    def match_chart_insight(*, chart_id: str, data_ref: str = "") -> dict[str, str]:
        for item in visual_insights:
            if chart_id and clean_text(item.get("chartId")) == chart_id:
                return item
        for item in visual_insights:
            if clean_text(item.get("chartId")):
                continue
            if data_ref and clean_text(item.get("dataRef")) == data_ref:
                return item
        return {}

    def match_table_insight(*, table_ref: str) -> dict[str, str]:
        for item in visual_insights:
            if clean_text(item.get("dataRef")) == table_ref and not clean_text(item.get("chartId")):
                return item
        return {}

    for chapter in chapter_plan:
        chapter_id = clean_text(chapter.get("chapterId"))
        design = as_dict(designs_by_chapter.get(chapter_id))
        chapter_title = clean_text(chapter.get("title"), limit=80) or "章节"
        default_page_type = clean_text(chapter.get("pageType")) or "insight"
        base_page = {
            "type": "body",
            "chapterId": chapter_id,
            "title": chapter_title,
            "tocEntry": False,
            "layout": clean_text(design.get("layout")) or clean_text(chapter.get("layout")) or "title_text",
            "styleTokens": _page_style_tokens(design, page_type=default_page_type),
        }
        chart_refs = string_list(design.get("chartRefs")) or string_list(chapter.get("chartRefs"))
        table_refs = string_list(design.get("tableRefs")) or string_list(chapter.get("tableRefs"))
        selected_charts = [charts_by_id[ref] for ref in chart_refs if ref in charts_by_id]
        selected_tables = [tables_by_id[ref] for ref in table_refs if ref in tables_by_id]
        if not selected_charts and default_page_type == "chart_analysis":
            selected_charts = [item for item in chart_specs if isinstance(item, dict)]
        if not selected_tables and default_page_type == "table_analysis":
            selected_tables = [item for item in tables if isinstance(item, dict)]
        intro_blocks = chapter_intro_blocks(chapter, include_visual_section=bool(selected_charts or selected_tables))
        chapter_pages: list[dict[str, Any]] = []

        if selected_charts:
            for batch_index, chart_batch in enumerate(_batched(selected_charts, 2), start=1):
                blocks = [dict(block) for block in intro_blocks] if batch_index == 1 else []
                evidence_refs: list[str] = []
                for chart in chart_batch:
                    chart_id = clean_text(chart.get("chartId"))
                    data_ref = clean_text(chart.get("dataRef"))
                    insight = match_chart_insight(chart_id=chart_id, data_ref=data_ref)
                    note = clean_text(insight.get("summary"), limit=260) or clean_text(design.get("caption"), limit=220) or "图表呈现了当前材料中最关键的数据关系。"
                    follow_up = clean_text(insight.get("followUp"), limit=260)
                    blocks.append({"type": "chart", "title": clean_text(chart.get("title")), "chartSpec": chart})
                    blocks.append({"type": "paragraph", "text": note})
                    if follow_up:
                        blocks.append({"type": "paragraph", "text": follow_up})
                    source_ref = clean_text(chart.get("sourceMaterialId"))
                    if source_ref in evidence_by_source and evidence_by_source[source_ref] not in evidence_refs:
                        evidence_refs.append(evidence_by_source[source_ref])
                chapter_pages.append(
                    {
                        **base_page,
                        "id": f"{chapter_id}_chart_{batch_index}",
                        "pageType": "chart_analysis",
                        "title": chapter_title if batch_index == 1 else f"{chapter_title}（续）",
                        "tocEntry": batch_index == 1,
                        "tocTitle": chapter_title,
                        "blocks": _ensure_chapter_narrative(blocks),
                        "evidenceRefs": evidence_refs,
                    }
                )
            if intro_blocks:
                visual_intro_consumed = True

        if selected_tables:
            for batch_index, table_batch in enumerate(_batched_tables(selected_tables), start=1):
                blocks = [dict(block) for block in intro_blocks] if batch_index == 1 and not chapter_pages else []
                evidence_refs: list[str] = []
                for table in table_batch:
                    rows = [row for row in as_list(table.get("rows")) if isinstance(row, dict)][:8]
                    table_ref = clean_text(table.get("tableId"))
                    insight = match_table_insight(table_ref=table_ref)
                    note = clean_text(insight.get("summary"), limit=260)
                    if not note:
                        note = "下表摘录了与当前判断直接相关的关键数据行，可用于核对结构差异和变化幅度。"
                        if len(as_list(table.get("rows"))) <= len(rows):
                            note = "下表保留了与当前判断直接相关的关键数据行，便于读者快速核对核心数字。"
                    follow_up = clean_text(insight.get("followUp"), limit=260)
                    blocks.extend(
                        [
                            {"type": "table_block", "title": clean_text(table.get("title")), "table": {**table, "rows": rows}},
                            {"type": "paragraph", "text": note},
                        ]
                    )
                    if follow_up:
                        blocks.append({"type": "paragraph", "text": follow_up})
                    source_ref = clean_text(table.get("sourceMaterialId"))
                    if source_ref in evidence_by_source and evidence_by_source[source_ref] not in evidence_refs:
                        evidence_refs.append(evidence_by_source[source_ref])
                chapter_pages.append(
                    {
                        **base_page,
                        "id": f"{chapter_id}_table_{batch_index}",
                        "pageType": "table_analysis",
                        "title": chapter_title if not chapter_pages else f"{chapter_title}（续）",
                        "tocEntry": not chapter_pages,
                        "tocTitle": chapter_title,
                        "blocks": _ensure_chapter_narrative(blocks),
                        "evidenceRefs": evidence_refs,
                    }
                )
            if intro_blocks:
                visual_intro_consumed = True

        if chapter_pages:
            body_pages.extend(chapter_pages)
            continue

        section_ids = chapter_sections(chapter)
        blocks = intro_blocks
        evidence_refs = []
        if default_page_type == "evidence" and not blocks:
            blocks = [
                {
                    "type": "evidence",
                    "items": [
                        {
                            "title": clean_text(item.get("title"), limit=100) or "来源材料",
                            "summary": clean_text(item.get("summary"), limit=220),
                        }
                        for item in evidence_items[:6]
                    ],
                }
            ]
            evidence_refs = [clean_text(item.get("evidenceId")) for item in evidence_items[:6] if clean_text(item.get("evidenceId"))]
        else:
            for section_id in section_ids:
                section = sections_by_id.get(section_id) or {}
                for ref in _section_evidence_refs(section):
                    if ref not in evidence_refs:
                        evidence_refs.append(ref)
        blocks = _ensure_chapter_narrative(blocks)
        if not blocks:
            continue
        body_pages.append(
            {
                **base_page,
                "id": f"page_{chapter_id}",
                "pageType": default_page_type,
                "title": chapter_title,
                "tocEntry": True,
                "tocTitle": chapter_title,
                "blocks": blocks,
                "evidenceRefs": evidence_refs,
            }
        )

    for offset, page in enumerate(body_pages, start=3):
        page["pageNumber"] = offset
        enforce_visual_tokens(page)
    return write_pages(body_pages)


def _compose_bundle(
    *,
    report_id: str,
    title: str,
    goal: str,
    audience: str,
    render_profile: dict[str, Any],
    source_context: dict[str, Any],
    materials: list[dict[str, Any]],
    semantic_model: dict[str, Any],
    chapter_plan: list[dict[str, Any]],
    page_designs: list[dict[str, Any]],
    chart_specs: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    prompt_meta: dict[str, dict[str, str]],
    stage_trace: list[dict[str, Any]],
    quality_flags: list[dict[str, Any]],
    quality_review: dict[str, Any],
) -> dict[str, Any]:
    sections_by_id = _section_lookup(sections)
    cover_page = _compose_cover_page(
        title=title,
        render_style=clean_text(render_profile.get("style")) or "professional",
        semantic_model=semantic_model,
        materials=materials,
        executive_section=sections_by_id.get("executive_judgement"),
    )
    body_pages = _compose_body_pages(
        chapter_plan=chapter_plan,
        page_designs=page_designs,
        chart_specs=chart_specs,
        sections=sections,
        semantic_model=semantic_model,
    )
    toc_page = {
        "id": "page_toc",
        "pageNumber": 2,
        "pageType": "table_of_contents",
        "type": "table_of_contents",
        "title": "目录",
        "tocEntry": False,
        "layout": "toc",
        "items": [
            {
                "id": page.get("id"),
                "title": clean_text(page.get("tocTitle"), limit=80) or clean_text(page.get("title")),
                "pageNumber": page.get("pageNumber"),
            }
            for page in body_pages
            if isinstance(page, dict) and page.get("tocEntry") and (clean_text(page.get("tocTitle"), limit=80) or clean_text(page.get("title")))
        ],
    }
    bundle = drop_empty(
        {
            "schemaVersion": PAGINATED_REPORT_BUNDLE_SCHEMA_VERSION,
            "reportId": report_id,
            "title": clean_text(title, limit=160) or "分析报告",
            "status": "completed",
            "createdAt": utc_now_iso(),
            "reviewedAt": utc_now_iso(),
            "metadata": {
                "goal": clean_text(goal, limit=300),
                "audience": clean_text(audience, limit=120),
                "sourceContext": source_context,
            },
            "inputSummary": {
                "materialCount": len(materials),
                "detectedTypes": sorted(
                    {
                        clean_text(item.get("detectedType"))
                        for item in materials
                        if isinstance(item, dict) and clean_text(item.get("detectedType"))
                    }
                ),
            },
            "materials": materials,
            "semanticModel": {
                **semantic_model,
                "chapterOutline": [
                    {"id": clean_text(item.get("chapterId")), "title": clean_text(item.get("title")), "origin": "chapter_plan"}
                    for item in chapter_plan
                    if isinstance(item, dict)
                ],
            },
            "chapterPlan": chapter_plan,
            "pages": [cover_page, toc_page, *body_pages],
            "chartSpecs": chart_specs,
            "assets": [],
            "evidenceRefs": semantic_model.get("evidenceRefs", []),
            "renderProfile": render_profile,
            "promptVersions": {**prompt_versions(), **{stage: value["version"] for stage, value in prompt_meta.items()}},
            "prompts": prompt_meta,
            "stageTrace": stage_trace,
            "qualityFlags": quality_flags,
            "qualityReview": quality_review,
            "exportManifest": {
                "availableFormats": ["pdf", "html", "bundle"],
                "primaryFormat": "pdf",
                "rendererInput": "PaginatedReportBundle",
            },
        }
    )
    return bundle


def _review_packet(bundle: dict[str, Any]) -> dict[str, Any]:
    semantic_model = as_dict(bundle.get("semanticModel"))
    return {
        "title": clean_text(bundle.get("title"), limit=160),
        "pageCount": len([item for item in as_list(bundle.get("pages")) if isinstance(item, dict)]),
        "inputSummary": as_dict(bundle.get("inputSummary")),
        "pages": [
            drop_empty(
                {
                    "id": clean_text(page.get("id")),
                    "pageType": clean_text(page.get("pageType")),
                    "title": clean_text(page.get("title"), limit=80),
                    "layout": clean_text(page.get("layout"), limit=60),
                    "contentRefs": _page_content_refs(page),
                    "evidenceRefCount": len([ref for ref in as_list(page.get("evidenceRefs")) if clean_text(ref)]),
                    "blockTypes": [
                        clean_text(block.get("type"))
                        for block in as_list(page.get("blocks"))
                        if isinstance(block, dict) and clean_text(block.get("type"))
                    ],
                    "blocks": [
                        _review_block_snapshot(block)
                        for block in as_list(page.get("blocks"))
                        if isinstance(block, dict)
                    ],
                }
            )
            for page in as_list(bundle.get("pages"))
            if isinstance(page, dict)
        ],
        "chartSpecs": [
            drop_empty(
                {
                    "chartId": clean_text(item.get("chartId")),
                    "title": clean_text(item.get("title"), limit=100),
                    "dataRef": clean_text(item.get("dataRef")),
                }
            )
            for item in as_list(bundle.get("chartSpecs"))
            if isinstance(item, dict)
        ],
        "tables": [
            drop_empty(
                {
                    "tableId": clean_text(item.get("tableId")),
                    "title": clean_text(item.get("title"), limit=100),
                    "sourceMaterialId": clean_text(item.get("sourceMaterialId")),
                    "rowCount": len([row for row in as_list(item.get("rows")) if isinstance(row, dict)]),
                    "columnCount": len([col for col in as_list(item.get("columns")) if isinstance(col, dict)]),
                }
            )
            for item in as_list(semantic_model.get("tables"))
            if isinstance(item, dict)
        ],
        "evidenceSummary": {
            "count": len([item for item in as_list(bundle.get("evidenceRefs")) if isinstance(item, dict)]),
            "titles": [
                clean_text(item.get("title"), limit=100)
                for item in as_list(bundle.get("evidenceRefs"))
                if isinstance(item, dict) and clean_text(item.get("title"), limit=100)
            ][:6],
        },
        "qualityFlags": [item for item in as_list(bundle.get("qualityFlags")) if isinstance(item, dict)],
    }


def _normalize_quality_review(raw_output: dict[str, Any]) -> dict[str, Any]:
    approved = bool(raw_output.get("approved", False))
    summary = clean_text(raw_output.get("summary"), limit=240)
    flags = _normalize_stage_flags(raw_output.get("qualityFlags"), stage_id="quality_review")
    return {"approved": approved, "summary": summary, "qualityFlags": flags}


def _page_content_refs(page: dict[str, Any]) -> dict[str, Any]:
    chart_data_refs: list[str] = []
    table_refs: list[str] = []
    for block in as_list(page.get("blocks")):
        if not isinstance(block, dict):
            continue
        block_type = clean_text(block.get("type"))
        if block_type == "chart":
            data_ref = clean_text(as_dict(block.get("chartSpec")).get("dataRef"))
            if data_ref and data_ref not in chart_data_refs:
                chart_data_refs.append(data_ref)
        elif block_type == "table_block":
            table_ref = clean_text(as_dict(block.get("table")).get("tableId"))
            if table_ref and table_ref not in table_refs:
                table_refs.append(table_ref)
    return drop_empty({"chartDataRefs": chart_data_refs, "tableRefs": table_refs})


def _review_block_snapshot(block: dict[str, Any]) -> dict[str, Any]:
    block_type = clean_text(block.get("type"))
    if block_type == "paragraph":
        return drop_empty({"type": block_type, "text": clean_text(block.get("text"), limit=220)})
    if block_type in {"items", "evidence", "metric_cards"}:
        items = [item for item in as_list(block.get("items")) if isinstance(item, dict)]
        title_limit = 8 if block_type == "evidence" else 4
        sample_limit = 5 if block_type == "evidence" else 3
        return drop_empty(
            {
                "type": block_type,
                "itemCount": len(items),
                "itemTitles": [
                    clean_text(item.get("title"), limit=80)
                    for item in items[:title_limit]
                    if clean_text(item.get("title"), limit=80)
                ],
                "sampleText": [
                    clean_text(item.get("summary") or item.get("value"), limit=140)
                    for item in items[:sample_limit]
                    if clean_text(item.get("summary") or item.get("value"), limit=140)
                ],
            }
        )
    if block_type == "chart":
        chart = as_dict(block.get("chartSpec"))
        return drop_empty(
            {
                "type": block_type,
                "title": clean_text(chart.get("title"), limit=100),
                "chartId": clean_text(chart.get("chartId")),
                "dataRef": clean_text(chart.get("dataRef")),
                "xField": clean_text(chart.get("xField")),
                "yField": clean_text(chart.get("yField")),
            }
        )
    if block_type == "table_block":
        table = as_dict(block.get("table"))
        return drop_empty(
            {
                "type": block_type,
                "title": clean_text(block.get("title") or table.get("title"), limit=100),
                "tableId": clean_text(table.get("tableId")),
                "rowCount": len([row for row in as_list(table.get("rows")) if isinstance(row, dict)]),
                "columnCount": len([col for col in as_list(table.get("columns")) if isinstance(col, dict)]),
            }
        )
    return drop_empty({"type": block_type})


def generate_paginated_report(
    *,
    materials: list[Any],
    title: str = "分析报告",
    goal: str = "",
    audience: str = "",
    render_style: str = "professional",
    source_context: dict[str, Any] | None = None,
    report_writer: Any | None = None,
) -> dict[str, Any]:
    report_id = new_report_id()
    clean_title = clean_text(title, limit=160) or "分析报告"
    render_profile = default_render_profile(render_style)
    source_context_payload = source_context or {}
    prompts = load_default_prompts()
    prompt_meta = {stage: {"id": data["id"], "version": data["version"]} for stage, data in prompts.items()}
    try:
        writer = get_report_writer(report_writer)
    except ReportRuntimeError as exc:
        raise ReportGenerationError(str(exc)) from exc

    stage_trace: list[dict[str, Any]] = []
    aggregated_flags: list[dict[str, Any]] = []

    intake_seed = intake_materials(materials)
    intake_output, trace = _invoke_stage(
        stage_key="intake",
        prompt_text=prompts["material_intake"]["text"],
        prompt_id=prompts["material_intake"]["id"],
        prompt_version=prompts["material_intake"]["version"],
        report_writer=writer,
        payload={
            "context": {"title": clean_title, "goal": clean_text(goal, limit=220), "audience": clean_text(audience, limit=120)},
            "materials": [
                drop_empty(
                    {
                        "materialId": clean_text(item.get("materialId")),
                        "title": clean_text(item.get("title"), limit=160),
                        "contentType": clean_text(item.get("contentType")),
                        "detectedType": clean_text(item.get("detectedType")),
                        "contentPreview": _content_preview(item.get("content")),
                    }
                )
                for item in as_list(intake_seed.get("materials"))
                if isinstance(item, dict)
            ],
            "qualityFlags": intake_seed.get("qualityFlags", []),
        },
    )
    intake_result = _normalize_intake_stage(intake_output, seed=intake_seed, fallback_title=clean_title)
    stage_trace.append(trace)
    aggregated_flags.extend(_normalize_stage_flags(intake_result.get("qualityFlags"), stage_id="intake"))

    normalization_seed = normalize_materials(intake_result["materials"])
    semantic_output, trace = _invoke_stage(
        stage_key="normalization",
        prompt_text=prompts["semantic_normalizer"]["text"],
        prompt_id=prompts["semantic_normalizer"]["id"],
        prompt_version=prompts["semantic_normalizer"]["version"],
        report_writer=writer,
        payload={
            "context": {"title": intake_result["title"], "goal": clean_text(goal, limit=220), "audience": clean_text(audience, limit=120)},
            "materials": [
                drop_empty(
                    {
                        "materialId": clean_text(item.get("materialId")),
                        "title": clean_text(item.get("title"), limit=160),
                        "detectedType": clean_text(item.get("detectedType")),
                        "reportUse": clean_text(item.get("reportUse")),
                        "summary": clean_text(item.get("summary"), limit=220),
                        "contentPreview": _content_preview(item.get("content"), limit=2500),
                    }
                )
                for item in intake_result["materials"]
            ],
            "seed": {"semanticModel": normalization_seed.get("semanticModel", {})},
        },
    )
    semantic_result = _normalize_semantic_stage(
        semantic_output,
        seed=normalization_seed,
        title=intake_result["title"],
        goal=goal,
        audience=audience,
    )
    stage_trace.append(trace)
    aggregated_flags.extend(_normalize_stage_flags(semantic_result.get("qualityFlags"), stage_id="normalization"))
    planning_chart_specs = build_chart_specs(semantic_result["semanticModel"])

    planning_output, trace = _invoke_stage(
        stage_key="page_planning",
        prompt_text=prompts["page_planner"]["text"],
        prompt_id=prompts["page_planner"]["id"],
        prompt_version=prompts["page_planner"]["version"],
        report_writer=writer,
        payload={
            "context": {"title": intake_result["title"], "renderStyle": clean_text(render_profile.get("style"))},
            "semanticModel": semantic_result["semanticModel"],
            "suggestedChapterPlan": _chapter_packet(_suggested_chapter_plan(semantic_result["semanticModel"])),
            "seed": {
                "chartSpecs": planning_chart_specs,
                "tables": [
                    {
                        "tableId": clean_text(item.get("tableId")),
                        "title": clean_text(item.get("title"), limit=100),
                    }
                    for item in as_list(semantic_result["semanticModel"].get("tables"))
                    if isinstance(item, dict) and clean_text(item.get("tableId"))
                ],
            },
        },
    )
    planning_result = _normalize_chapter_plan(planning_output, semantic_model=semantic_result["semanticModel"])
    stage_trace.append(trace)
    aggregated_flags.extend(planning_result["qualityFlags"])

    visual_output, trace = _invoke_stage(
        stage_key="visual_design",
        prompt_text=prompts["visual_designer"]["text"],
        prompt_id=prompts["visual_designer"]["id"],
        prompt_version=prompts["visual_designer"]["version"],
        report_writer=writer,
        payload={
            "context": {"title": intake_result["title"], "renderProfile": render_profile},
            "semanticModel": semantic_result["semanticModel"],
            "chapterPlan": _chapter_packet(planning_result["chapterPlan"]),
            "seed": {"chartSpecs": planning_chart_specs},
        },
    )
    visual_result = _normalize_visual_stage(
        visual_output,
        chapter_plan=planning_result["chapterPlan"],
        semantic_model=semantic_result["semanticModel"],
    )
    stage_trace.append(trace)
    aggregated_flags.extend(visual_result["qualityFlags"])

    writing_payload = {
        "context": {"title": intake_result["title"], "goal": clean_text(goal, limit=220), "audience": clean_text(audience, limit=120)},
        "chapterPlan": _chapter_packet(planning_result["chapterPlan"]),
        "pageDesigns": visual_result["pageDesigns"],
        "writingPacket": _build_writing_packet(semantic_result["semanticModel"]),
    }
    final_title = intake_result["title"]
    written_sections: list[dict[str, Any]] = []
    writing_flags: list[dict[str, Any]] = []
    last_writing_error: ReportGenerationError | None = None
    for attempt in range(2):
        payload = dict(writing_payload)
        if attempt and last_writing_error is not None:
            payload["retryAttempt"] = attempt + 1
            payload["validationFeedback"] = str(last_writing_error)
        writing_output, trace = _invoke_stage(
            stage_key="writing",
            prompt_text=prompts["narrative_writer"]["text"],
            prompt_id=prompts["narrative_writer"]["id"],
            prompt_version=prompts["narrative_writer"]["version"],
            report_writer=writer,
            payload=payload,
        )
        current_title, current_sections, current_flags = _normalize_writer_sections(writing_output)
        current_final_title = current_title or intake_result["title"]
        try:
            _validate_written_output(
                current_final_title,
                current_sections,
                chapter_plan=planning_result["chapterPlan"],
                materials=intake_result["materials"],
                source_context=source_context_payload,
            )
        except ReportGenerationError as exc:
            stage_trace.append({**trace, "status": "retry", "validationError": str(exc)})
            last_writing_error = exc
            if attempt == 0:
                continue
            raise
        final_title = current_final_title
        written_sections = current_sections
        writing_flags = current_flags
        stage_trace.append(trace)
        aggregated_flags.extend(writing_flags)
        break

    draft_bundle = _compose_bundle(
        report_id=report_id,
        title=final_title,
        goal=goal,
        audience=audience,
        render_profile=render_profile,
        source_context=source_context_payload,
        materials=intake_result["materials"],
        semantic_model=semantic_result["semanticModel"],
        chapter_plan=planning_result["chapterPlan"],
        page_designs=visual_result["pageDesigns"],
        chart_specs=visual_result["chartSpecs"],
        sections=written_sections,
        prompt_meta=prompt_meta,
        stage_trace=stage_trace,
        quality_flags=aggregated_flags,
        quality_review={"approved": False, "summary": "", "qualityFlags": []},
    )

    review_output, trace = _invoke_stage(
        stage_key="quality_review",
        prompt_text=prompts["quality_reviewer"]["text"],
        prompt_id=prompts["quality_reviewer"]["id"],
        prompt_version=prompts["quality_reviewer"]["version"],
        report_writer=writer,
        payload={"bundle": _review_packet(draft_bundle)},
    )
    review_result = _normalize_quality_review(review_output)
    stage_trace.append(trace)
    aggregated_flags.extend(review_result["qualityFlags"])
    if not review_result["approved"]:
        raise ReportGenerationError(review_result["summary"] or "quality review rejected the report")

    final_bundle = _compose_bundle(
        report_id=report_id,
        title=final_title,
        goal=goal,
        audience=audience,
        render_profile=render_profile,
        source_context=source_context_payload,
        materials=intake_result["materials"],
        semantic_model=semantic_result["semanticModel"],
        chapter_plan=planning_result["chapterPlan"],
        page_designs=visual_result["pageDesigns"],
        chart_specs=visual_result["chartSpecs"],
        sections=written_sections,
        prompt_meta=prompt_meta,
        stage_trace=stage_trace,
        quality_flags=aggregated_flags,
        quality_review=review_result,
    )

    validation_flags = validate_bundle(final_bundle)
    final_bundle["qualityFlags"] = [*final_bundle.get("qualityFlags", []), *validation_flags]
    if has_blocking_errors(validation_flags):
        raise ReportGenerationError("reviewed bundle failed structural validation")

    from .renderers import render_bundle_html, render_bundle_markdown

    markdown = render_bundle_markdown(final_bundle)
    html = render_bundle_html(final_bundle)
    publication_errors = validate_published_report(
        markdown,
        html,
        forbidden_values=_forbidden_values(intake_result["materials"], source_context_payload),
    )
    if publication_errors:
        raise ReportGenerationError("reviewed bundle failed publication validation: " + "；".join(publication_errors[:5]))
    return final_bundle
