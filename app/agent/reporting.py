from __future__ import annotations

import base64
import html
import json
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AnalysisModuleArtifact, AnalysisReport

REPORT_ARTIFACT_SCHEMA_VERSION = "analysis_report_artifact.v1"
REPORT_CONTRIBUTION_SCHEMA_VERSION = "analysis_report_contribution.v1"
DOMAIN_ANALYSIS_SCHEMA_VERSION = "analysis_domain_analysis.v1"
REPORT_SEMANTIC_MODEL_SCHEMA_VERSION = "report_semantic_model.v1"
REPORT_SEMANTIC_CONTRIBUTION_PROFILE_VERSION = "report_semantic_contribution.v1"
VISUAL_ASSET_SCHEMA_VERSION = "analysis_report_visual_asset.v1"
REPORT_PREVIEW_LIMIT = 1200
REPORT_DOWNLOAD_FORMAT = "pdf"
SUPPORTED_REPORT_DOWNLOAD_FORMATS = {REPORT_DOWNLOAD_FORMAT}
REPORT_PREVIEW_FORMAT = "pdf"
REPORT_RENDER_STYLES = (
    {"id": "professional", "label": "专业白底"},
    {"id": "dark_research", "label": "深色投研"},
    {"id": "brand_cover", "label": "品牌封面"},
    {"id": "chart_focus", "label": "图表强化"},
)
DEFAULT_REPORT_RENDER_STYLE = "professional"
VISUAL_ASSET_TYPES = {"image", "chart", "table", "graph", "timeline", "heatmap"}
REPORT_PDF_PAGE_WIDTH = 595
REPORT_PDF_PAGE_HEIGHT = 842
REPORT_PDF_MARGIN_X = 40
REPORT_PDF_MARGIN_TOP = 44
REPORT_PDF_MARGIN_BOTTOM = 44
REPORT_PDF_SEGMENT_GAP = 10
REPORT_PDF_CSS = (
    "body{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
    "font-size:11pt;line-height:1.6;color:#17202a;}"
    "h1{font-size:18pt;line-height:1.3;margin:0 0 14px 0;}"
    "h2{font-size:14pt;line-height:1.35;margin:16px 0 8px 0;}"
    "h3{font-size:12pt;line-height:1.4;margin:12px 0 6px 0;}"
    "p{margin:0 0 10px 0;}"
    "ul{margin:0 0 10px 18px;padding:0;}"
    "li{margin:0 0 6px 0;}"
    "figure{margin:0 0 12px 0;}"
    "img{max-width:100%;height:auto;display:block;margin:0 auto 6px auto;}"
    "figcaption{font-size:9.5pt;color:#52606d;}"
    ".pdf-visual-fallback{border:1px solid #d8dee8;padding:10px 12px;border-radius:4px;background:#f7f9fc;}"
)
REPORT_PDF_STYLE_CSS = {
    "professional": "",
    "dark_research": (
        "body{color:#edf2f7;background:#111827;}"
        "h1,h2,h3{color:#f8fafc;}"
        "figcaption{color:#cbd5e1;}"
        ".pdf-visual-fallback{border-color:#334155;background:#1f2937;}"
    ),
    "brand_cover": (
        "h1{color:#0f766e;border-bottom:2px solid #14b8a6;padding-bottom:8px;}"
        "h2{color:#115e59;}"
        ".pdf-visual-fallback{border-color:#99f6e4;background:#f0fdfa;}"
    ),
    "chart_focus": (
        "h1{color:#1d4ed8;}"
        "h2{color:#1e40af;border-bottom:1px solid #bfdbfe;padding-bottom:4px;}"
        "figure{border:1px solid #dbeafe;padding:8px;background:#f8fbff;}"
    ),
}
PUBLISHED_REPORT_FORBIDDEN_LABELS = {
    "moduleId",
    "displayName",
    "runId",
    "moduleRunIds",
    "enabledModules",
    "analysisSessionId",
    "analysisSessionRevision",
    "traceRefs",
    "sourceIds",
    "eventIds",
    "domainOutputIds",
    "findingIds",
    "modelOutputIds",
    "assetId",
    "storageRef",
    "rawResult",
    "artifact_json",
    "analysis_reports",
}


class ReportContributionValidationError(ValueError):
    pass


class PublishedReportValidationError(ValueError):
    pass


def normalize_report_contribution(value: Any, *, module_id: str, display_name: str = "", status: str = "") -> dict[str, Any]:
    payload = dict(value or {}) if isinstance(value, dict) else {}
    return _drop_empty(
        {
            "schemaVersion": REPORT_CONTRIBUTION_SCHEMA_VERSION,
            "moduleId": _clean_text(payload.get("moduleId") or module_id),
            "displayName": _clean_text(payload.get("displayName") or display_name),
            "status": _clean_text(payload.get("status") or status),
            "findings": _normalize_contribution_items(payload.get("findings"), "finding", module_id=module_id),
            "evidence": _normalize_contribution_items(payload.get("evidence"), "evidence", module_id=module_id),
            "attributionInputs": _normalize_contribution_items(
                payload.get("attributionInputs") or payload.get("attribution_inputs"),
                "attribution",
                module_id=module_id,
            ),
            "logicInputs": _normalize_contribution_items(
                payload.get("logicInputs") or payload.get("logic_inputs"),
                "logic",
                module_id=module_id,
            ),
            "recommendationInputs": _normalize_contribution_items(
                payload.get("recommendationInputs") or payload.get("recommendation_inputs"),
                "recommendation",
                module_id=module_id,
            ),
            "modelOutputs": _normalize_contribution_items(
                payload.get("modelOutputs") or payload.get("model_outputs"),
                "model_output",
                module_id=module_id,
            ),
            "visualAssets": [
                normalize_visual_asset(item, module_id=module_id)
                for item in _list_of_dicts(payload.get("visualAssets") or payload.get("visual_assets"))
            ],
            "attachments": _normalize_contribution_items(payload.get("attachments"), "attachment", module_id=module_id),
            "limitations": _normalize_limitations(payload.get("limitations"), module_id=module_id),
        }
    )


def normalize_visual_asset(value: Any, *, module_id: str) -> dict[str, Any]:
    payload = dict(value or {}) if isinstance(value, dict) else {}
    asset_id = _clean_text(payload.get("assetId") or payload.get("asset_id") or payload.get("id"))
    asset_type = _clean_text(payload.get("type") or payload.get("assetType") or payload.get("asset_type")).lower()
    render_payload = payload.get("renderPayload") or payload.get("render_payload") or payload.get("structuredPayload")
    if not isinstance(render_payload, dict):
        render_payload = {}
    content_type = _clean_text(payload.get("contentType") or payload.get("content_type"))
    if not asset_id:
        asset_id = f"{module_id}_asset_{uuid.uuid4().hex[:12]}"
    if asset_type not in VISUAL_ASSET_TYPES:
        asset_type = "image" if content_type.startswith("image/") else "chart"

    normalized = _drop_empty(
        {
            "schemaVersion": VISUAL_ASSET_SCHEMA_VERSION,
            "assetId": asset_id,
            "moduleId": _clean_text(payload.get("moduleId") or module_id),
            "type": asset_type,
            "subtype": _clean_text(payload.get("subtype")),
            "title": _clean_text(payload.get("title")) or "分析图表",
            "description": _clean_text(payload.get("description")),
            "caption": _clean_text(payload.get("caption")),
            "altText": _clean_text(payload.get("altText") or payload.get("alt_text") or payload.get("accessibilityText"))
            or _clean_text(payload.get("title"))
            or "分析图表",
            "contentType": content_type or _content_type_for_visual_type(asset_type),
            "storageRef": _clean_text(payload.get("storageRef") or payload.get("storage_ref") or payload.get("storagePath")),
            "downloadUrl": _clean_text(payload.get("downloadUrl") or payload.get("download_url")),
            "renderPayload": render_payload,
            "traceRefs": _normalize_trace_refs(payload.get("traceRefs") or payload.get("trace_refs")),
            "limitations": _normalize_limitations(payload.get("limitations"), module_id=module_id),
            "createdAt": _clean_text(payload.get("createdAt") or payload.get("created_at")),
            "filename": _clean_filename(payload.get("filename") or payload.get("fileName") or f"{asset_id}.json"),
            "inlineContent": _clean_text(payload.get("inlineContent") or payload.get("textContent")),
        }
    )
    if not normalized.get("storageRef") and not normalized.get("downloadUrl") and not normalized.get("renderPayload") and not normalized.get("inlineContent"):
        normalized["renderPayload"] = {"text": normalized["altText"]}
    return normalized


def validate_report_contribution_traceability(contribution: dict[str, Any], domain_analysis: dict[str, Any] | None = None) -> list[str]:
    domain_analysis = dict(domain_analysis or {}) if isinstance(domain_analysis, dict) else {}
    valid_refs = _collect_traceable_ids(contribution, domain_analysis)
    errors: list[str] = []
    for collection_name in ("findings", "attributionInputs", "logicInputs", "recommendationInputs"):
        for item in contribution.get(collection_name, []) if isinstance(contribution.get(collection_name), list) else []:
            if not isinstance(item, dict):
                continue
            trace_ids = _trace_ids(item.get("traceRefs"))
            if not trace_ids:
                errors.append(f"{collection_name}:{item.get('id', '')} missing trace references")
                continue
            if not any(trace_id in valid_refs for trace_id in trace_ids):
                errors.append(f"{collection_name}:{item.get('id', '')} references unknown trace ids")
    if errors:
        raise ReportContributionValidationError("; ".join(errors))
    return []


def build_robotics_domain_analysis(module_result: dict[str, Any]) -> dict[str, Any]:
    result = _dict_value(module_result.get("result"))
    handoff = _dict_value(module_result.get("documentHandoff"))
    module_id = _clean_text(module_result.get("moduleId")) or "robotics_risk"
    evidence = _list_of_dicts(handoff.get("evidenceTable"))
    opportunities = _list_of_dicts(handoff.get("opportunitySections"))
    risks = _list_of_dicts(handoff.get("riskSections"))
    return _drop_empty(
        {
            "schemaVersion": DOMAIN_ANALYSIS_SCHEMA_VERSION,
            "moduleId": module_id,
            "displayName": _clean_text(module_result.get("displayName")),
            "status": _clean_text(module_result.get("status")),
            "methodology": "基于机器人产业相关政策、公告、招中标与竞争信息的模块化风险机会识别。",
            "summary": _clean_text(module_result.get("summary")),
            "domainOutputs": [
                *_robotics_signal_domain_outputs(opportunities, output_type="opportunity"),
                *_robotics_signal_domain_outputs(risks, output_type="risk"),
            ],
            "evidence": _normalize_contribution_items(evidence, "evidence", module_id=module_id),
            "reasoningTrace": _robotics_reasoning_trace(opportunities, risks, module_id=module_id),
            "diagnostics": _list_of_dicts(module_result.get("sourceDiagnostics")),
            "modelOutputs": [],
            "visualAssets": [],
            "limitations": _normalize_limitations(module_result.get("limitations"), module_id=module_id),
            "sourceReferences": _list_of_dicts(module_result.get("sourceReferences")),
            "rawResult": result,
        }
    )


def build_robotics_report_contribution(module_result: dict[str, Any], domain_analysis: dict[str, Any]) -> dict[str, Any]:
    module_id = _clean_text(module_result.get("moduleId")) or "robotics_risk"
    handoff = _dict_value(module_result.get("documentHandoff"))
    opportunities = _list_of_dicts(handoff.get("opportunitySections"))
    risks = _list_of_dicts(handoff.get("riskSections"))
    evidence = _list_of_dicts(handoff.get("evidenceTable"))
    findings = [
        *_robotics_findings(opportunities, module_id=module_id, kind="opportunity"),
        *_robotics_findings(risks, module_id=module_id, kind="risk"),
    ]
    contribution = normalize_report_contribution(
        {
            "moduleId": module_id,
            "displayName": module_result.get("displayName"),
            "status": module_result.get("status"),
            "findings": findings,
            "evidence": evidence,
            "attributionInputs": _robotics_attribution_inputs(findings, module_id=module_id),
            "logicInputs": _robotics_logic_inputs(findings, module_id=module_id),
            "recommendationInputs": _robotics_recommendations(findings, module_id=module_id),
            "modelOutputs": [],
            "visualAssets": [],
            "attachments": [],
            "limitations": module_result.get("limitations"),
        },
        module_id=module_id,
        display_name=_clean_text(module_result.get("displayName")),
        status=_clean_text(module_result.get("status")),
    )
    validate_report_contribution_traceability(contribution, domain_analysis)
    return contribution


def generate_analysis_report(
    *,
    analysis_session: dict[str, Any],
    handoff_bundle: dict[str, Any],
    module_results: dict[str, dict[str, Any]],
    report_writer: Any | None = None,
) -> dict[str, Any] | None:
    if not isinstance(handoff_bundle, dict) or not isinstance(module_results, dict):
        return None
    enabled_modules = _string_list(handoff_bundle.get("enabledModules") or analysis_session.get("enabledModules"))
    if not enabled_modules:
        return None

    contributions: list[dict[str, Any]] = []
    included_results: list[dict[str, Any]] = []
    limitations = _normalize_limitations(handoff_bundle.get("limitations"), module_id="report")
    stale_modules = _string_list(handoff_bundle.get("staleModules"))
    for module_id in enabled_modules:
        result = module_results.get(module_id)
        if not isinstance(result, dict):
            limitations.append(_limitation("report", "某项已启用分析能力未获得输出，相关内容已从报告正文中省略。"))
            continue
        contribution = result.get("reportContribution")
        if not isinstance(contribution, dict) or not contribution:
            if str(result.get("status", "")).strip() in {"failed", "need_input", "stale"}:
                limitations.extend(_normalize_limitations(result.get("limitations"), module_id=module_id))
                continue
            contribution = normalize_report_contribution(
                {},
                module_id=module_id,
                display_name=str(result.get("displayName", "")),
                status=str(result.get("status", "")),
            )
        domain_analysis = result.get("domainAnalysis") if isinstance(result.get("domainAnalysis"), dict) else {}
        try:
            validate_report_contribution_traceability(contribution, domain_analysis)
        except ReportContributionValidationError as exc:
            limitations.append(_limitation(module_id, f"某项分析输出未通过追溯校验，已降级处理：{exc}"))
            contribution = _drop_substantive_items(contribution)
        contributions.append(contribution)
        included_results.append(result)

    if not contributions and not limitations:
        return None

    report_id = _new_report_id()
    generated_at = _format_datetime(datetime.utcnow())
    shared_summary = _dict_value(handoff_bundle.get("sharedInputSummary"))
    session_payload = _dict_value(handoff_bundle.get("analysisSession") or analysis_session)
    title = _report_title(shared_summary, included_results)
    status = _report_status(contributions, stale_modules=stale_modules)
    limitations.extend(_contribution_limitations(contributions))
    if stale_modules:
        limitations.append(_limitation("report", "部分已启用分析能力输出已过期，报告只能作为降级快照使用。"))
    module_run_ids = _dict_value(handoff_bundle.get("moduleRunIds"))
    if shared_summary.get("enterpriseName"):
        shared_summary["enterpriseName"] = _clean_report_subject(shared_summary.get("enterpriseName"))
    semantic_model = build_report_semantic_model(
        title=title,
        status=status,
        shared_summary=shared_summary,
        enabled_modules=enabled_modules,
        session_payload=session_payload,
        module_run_ids=module_run_ids,
        contributions=contributions,
        module_results=included_results,
        limitations=limitations,
    )
    semantic_model["qualityFlags"] = [
        *_list_of_dicts(semantic_model.get("qualityFlags")),
        *_semantic_quality_flags(semantic_model, stale_modules=stale_modules),
    ]
    sections = _build_semantic_report_sections(semantic_model)
    published_forbidden_values = _published_forbidden_values(
        enabled_modules=enabled_modules,
        module_run_ids=module_run_ids,
        contributions=contributions,
    )
    writer_title = title
    writer_quality_flags: list[dict[str, Any]] = []
    if report_writer is None:
        writer_quality_flags.append(_quality_flag("llm_writer_unavailable", "warning", "未接入报告写作模型，已使用结构化降级报告。"))
    else:
        writer_result = _write_report_with_llm(
            report_writer,
            semantic_model=semantic_model,
            fallback_title=title,
            fallback_sections=sections,
            forbidden_values=published_forbidden_values,
        )
        if writer_result.get("ok"):
            writer_title = _clean_text(writer_result.get("title")) or title
            sections = _list_of_dicts(writer_result.get("sections"))
            writer_quality_flags.append(_quality_flag("llm_writer", "info", "已使用受约束的报告写作模型润色正文。"))
        else:
            reason = _clean_text(writer_result.get("reason")) or "写作模型输出未通过校验"
            writer_quality_flags.append(_quality_flag("llm_writer_fallback", "warning", f"{reason}，已使用结构化降级报告。"))
    semantic_model["qualityFlags"] = [*_list_of_dicts(semantic_model.get("qualityFlags")), *writer_quality_flags]
    artifact = _drop_empty(
        {
            "schemaVersion": REPORT_ARTIFACT_SCHEMA_VERSION,
            "reportId": report_id,
            "title": writer_title,
            "status": status,
            "generatedAt": generated_at,
            "scope": {
                "reportGoal": _clean_text(shared_summary.get("reportGoal")),
                "targetCompany": _clean_report_subject(shared_summary.get("enterpriseName")),
                "stockCode": _clean_text(shared_summary.get("stockCode")),
                "timeRange": _clean_text(shared_summary.get("timeRange")),
                "enabledModules": enabled_modules,
                "analysisSessionId": _clean_text(session_payload.get("sessionId")),
                "analysisSessionRevision": _safe_int(session_payload.get("revision"), default=0),
                "moduleRunIds": module_run_ids,
            },
            "moduleSummaries": _module_summaries(contributions, included_results),
            "semanticModel": semantic_model,
            "internalTraceIndex": _dict_value(semantic_model.get("internalTraceIndex")),
            "sectionPlan": [{"id": section.get("id"), "title": section.get("title")} for section in sections if isinstance(section, dict)],
            "sections": sections,
            "findings": _list_of_dicts(semantic_model.get("keyFindings")),
            "attributionChains": _list_of_dicts(semantic_model.get("drivers")),
            "logicBreakdown": _list_of_dicts(semantic_model.get("drivers")),
            "recommendations": _list_of_dicts(semantic_model.get("recommendations")),
            "evidenceTraceability": _list_of_dicts(semantic_model.get("evidenceChains")),
            "modelOutputs": _list_of_dicts(semantic_model.get("modelExplanations")),
            "visualAssets": _with_report_asset_urls(report_id, _all_items(contributions, "visualAssets")),
            "attachments": _with_report_asset_urls(report_id, _all_items(contributions, "attachments")),
            "limitations": _list_of_dicts(semantic_model.get("limitations")),
            "qualityFlags": _list_of_dicts(semantic_model.get("qualityFlags")),
        }
    )
    markdown_body = render_report_markdown(artifact)
    html_body = render_report_html(artifact, markdown_body=markdown_body)
    validation_errors = validate_published_report(
        markdown_body,
        html_body,
        bounded_report_preview(markdown_body),
        forbidden_values=published_forbidden_values,
    )
    if validation_errors:
        artifact["status"] = "failed"
        artifact["qualityFlags"] = [
            *_list_of_dicts(artifact.get("qualityFlags")),
            _quality_flag("published_output", "hard", "发布报告包含内部字段，已阻止对外发布：" + "；".join(validation_errors[:5])),
        ]
        markdown_body = "# 报告生成失败\n\n发布报告未通过内部字段泄露校验，请重新生成或联系管理员复核。\n"
        html_body = render_report_html({"title": "报告生成失败", "sections": [_section("validation_failed", "报告生成失败", [_paragraph("发布报告未通过内部字段泄露校验，请重新生成或联系管理员复核。")])]}, markdown_body=markdown_body)
    artifact["markdownBody"] = markdown_body
    artifact["htmlBody"] = html_body
    artifact["preview"] = bounded_report_preview(markdown_body)
    artifact["downloadMetadata"] = report_download_metadata(report_id)
    return artifact


def build_report_semantic_model(
    *,
    title: str,
    status: str,
    shared_summary: dict[str, Any],
    enabled_modules: list[str],
    session_payload: dict[str, Any],
    module_run_ids: dict[str, Any],
    contributions: list[dict[str, Any]],
    module_results: list[dict[str, Any]],
    limitations: list[dict[str, Any]],
) -> dict[str, Any]:
    blocked_terms = _internal_reader_blocklist(
        enabled_modules=enabled_modules,
        module_run_ids=module_run_ids,
        contributions=contributions,
        module_results=module_results,
    )
    trace_index: dict[str, Any] = {}
    key_findings: list[dict[str, Any]] = []
    risk_signals: list[dict[str, Any]] = []
    opportunity_signals: list[dict[str, Any]] = []
    drivers: list[dict[str, Any]] = []
    evidence_chains: list[dict[str, Any]] = []
    model_explanations: list[dict[str, Any]] = []
    visual_narratives: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    semantic_limitations: list[dict[str, Any]] = []

    for contribution in contributions:
        module_id = _clean_text(contribution.get("moduleId"))
        profile = _semantic_profile(contribution)
        for item in _list_of_dicts(contribution.get("findings")):
            semantic = _semantic_finding(item, blocked_terms=blocked_terms)
            if not semantic:
                continue
            _add_trace(trace_index, semantic["id"], contribution=contribution, item=item, kind="finding", profile=profile)
            existing = _find_similar_semantic_item(key_findings, semantic)
            if existing is not None:
                _merge_semantic_item(existing, semantic)
                _add_trace(trace_index, existing["id"], contribution=contribution, item=item, kind="finding", profile=profile)
                continue
            key_findings.append(semantic)
            kind = _clean_text(item.get("kind")).lower()
            if kind == "risk" or "风险" in semantic.get("title", ""):
                risk_signals.append({**semantic, "id": semantic["id"].replace("finding", "risk", 1), "signalType": "risk"})
            elif kind == "opportunity" or "机会" in semantic.get("title", ""):
                opportunity_signals.append({**semantic, "id": semantic["id"].replace("finding", "opportunity", 1), "signalType": "opportunity"})

        for item in [*_list_of_dicts(contribution.get("attributionInputs")), *_list_of_dicts(contribution.get("logicInputs"))]:
            semantic = _semantic_driver(item, blocked_terms=blocked_terms)
            if semantic:
                drivers.append(semantic)
                _add_trace(trace_index, semantic["id"], contribution=contribution, item=item, kind="driver", profile=profile)

        for item in _list_of_dicts(contribution.get("evidence")):
            semantic = _semantic_evidence_chain(item, blocked_terms=blocked_terms)
            if semantic:
                evidence_chains.append(semantic)
                _add_trace(trace_index, semantic["id"], contribution=contribution, item=item, kind="evidence", profile=profile)

        for item in _list_of_dicts(contribution.get("modelOutputs")):
            semantic = _semantic_model_explanation(item, blocked_terms=blocked_terms)
            if semantic:
                model_explanations.append(semantic)
                _add_trace(trace_index, semantic["id"], contribution=contribution, item=item, kind="model_explanation", profile=profile)

        for item in _list_of_dicts(contribution.get("visualAssets")):
            semantic = _semantic_visual_narrative(item, blocked_terms=blocked_terms)
            if semantic:
                visual_narratives.append(semantic)
                _add_trace(trace_index, semantic["id"], contribution=contribution, item=item, kind="visual_narrative", profile=profile)

        grounded_finding_ids = {item.get("id") for item in _list_of_dicts(contribution.get("findings")) if _clean_text(item.get("id"))}
        for item in _list_of_dicts(contribution.get("recommendationInputs")):
            semantic = _semantic_recommendation(item, blocked_terms=blocked_terms, grounded_finding_ids=grounded_finding_ids)
            if semantic:
                recommendations.append(semantic)
                _add_trace(trace_index, semantic["id"], contribution=contribution, item=item, kind="recommendation", profile=profile)

        for item in _list_of_dicts(contribution.get("limitations")):
            semantic = _semantic_limitation(item, blocked_terms=blocked_terms)
            if semantic:
                semantic_limitations.append(semantic)
                _add_trace(trace_index, semantic["id"], contribution=contribution, item=item, kind="limitation", profile=profile)

        if module_id and not _list_of_dicts(contribution.get("findings")) and _clean_text(contribution.get("status")).lower() in {"partial", "failed", "need_input", "stale"}:
            semantic_limitations.append(
                _semantic_limitation(
                    {"summary": "部分已启用分析能力未提供足够可支撑的实质性结论，相关内容已从报告正文中降级处理。"},
                    blocked_terms=blocked_terms,
                )
            )

    for item in limitations:
        semantic = _semantic_limitation(item, blocked_terms=blocked_terms)
        if semantic:
            semantic_limitations.append(semantic)

    semantic_limitations = _dedupe_semantic_items(semantic_limitations)
    executive_judgements = _executive_judgements_from_semantics(
        status=status,
        findings=key_findings,
        limitations=semantic_limitations,
        blocked_terms=blocked_terms,
    )
    return _drop_empty(
        {
            "schemaVersion": REPORT_SEMANTIC_MODEL_SCHEMA_VERSION,
            "reportIntent": {
                "goal": _reader_text(shared_summary.get("reportGoal"), blocked_terms=blocked_terms),
                "language": "zh-CN",
                "outputStyle": "decision_report",
            },
            "subject": {
                "name": _clean_report_subject(_reader_text(shared_summary.get("enterpriseName"), blocked_terms=blocked_terms)),
                "stockCode": _reader_text(shared_summary.get("stockCode"), blocked_terms=blocked_terms),
            },
            "scope": {
                "timeRange": _reader_text(shared_summary.get("timeRange"), blocked_terms=blocked_terms),
                "analysisFocus": _reader_text("、".join(_string_list(shared_summary.get("analysisFocusTags"))), blocked_terms=blocked_terms),
                "status": status,
            },
            "executiveJudgements": executive_judgements,
            "keyFindings": key_findings,
            "riskSignals": _dedupe_semantic_items(risk_signals),
            "opportunitySignals": _dedupe_semantic_items(opportunity_signals),
            "drivers": _dedupe_semantic_items(drivers),
            "evidenceChains": _dedupe_semantic_items(evidence_chains),
            "modelExplanations": _dedupe_semantic_items(model_explanations),
            "visualNarratives": _dedupe_semantic_items(visual_narratives),
            "recommendations": _dedupe_semantic_items(recommendations),
            "limitations": semantic_limitations,
            "qualityFlags": [],
            "internalTraceIndex": {
                "session": {
                    "sessionId": _clean_text(session_payload.get("sessionId")),
                    "revision": _safe_int(session_payload.get("revision"), default=0),
                },
                "enabledModules": enabled_modules,
                "moduleRunIds": module_run_ids,
                "items": trace_index,
            },
            "title": _reader_text(title, blocked_terms=blocked_terms) or "定制化分析报告",
        }
    )


def build_report_writing_packet(semantic_model: dict[str, Any]) -> dict[str, Any]:
    subject = _dict_value(semantic_model.get("subject"))
    scope = _dict_value(semantic_model.get("scope"))
    intent = _dict_value(semantic_model.get("reportIntent"))
    return _drop_empty(
        {
            "报告标题": _clean_text(semantic_model.get("title")),
            "主体": {
                "名称": _clean_text(subject.get("name")),
                "股票代码": _clean_text(subject.get("stockCode")),
            },
            "范围": {
                "时间范围": _clean_text(scope.get("timeRange")),
                "分析重点": _clean_text(scope.get("analysisFocus")),
                "报告目标": _clean_text(intent.get("goal")),
                "生成状态": _clean_text(scope.get("status")),
            },
            "核心判断": [_reader_packet_item(item) for item in _list_of_dicts(semantic_model.get("executiveJudgements"))],
            "关键发现": [_reader_packet_item(item) for item in _list_of_dicts(semantic_model.get("keyFindings"))],
            "风险信号": [_reader_packet_item(item) for item in _list_of_dicts(semantic_model.get("riskSignals"))],
            "机会信号": [_reader_packet_item(item) for item in _list_of_dicts(semantic_model.get("opportunitySignals"))],
            "归因与逻辑": [_reader_packet_item(item) for item in _list_of_dicts(semantic_model.get("drivers"))],
            "来源与核验": [_reader_packet_item(item) for item in _list_of_dicts(semantic_model.get("evidenceChains"))],
            "模型解读": [_reader_packet_item(item) for item in _list_of_dicts(semantic_model.get("modelExplanations"))],
            "图表解读": [_reader_packet_item(item) for item in _list_of_dicts(semantic_model.get("visualNarratives"))],
            "决策建议": [_reader_packet_item(item) for item in _list_of_dicts(semantic_model.get("recommendations"))],
            "限制说明": [_reader_packet_item(item) for item in _list_of_dicts(semantic_model.get("limitations"))],
        }
    )


def _write_report_with_llm(
    report_writer: Any,
    *,
    semantic_model: dict[str, Any],
    fallback_title: str,
    fallback_sections: list[dict[str, Any]],
    forbidden_values: list[str],
) -> dict[str, Any]:
    packet = build_report_writing_packet(semantic_model)
    prompt = (
        "你是面向决策读者的中文报告写作器。只根据给定写作包重写报告，不新增事实、数字、来源或判断。"
        "禁止出现模块名、运行标识、数据库字段、代码字段、traceRefs、sourceIds、moduleId 等内部实现词。"
        "输出必须是 JSON 对象，格式为："
        "{\"title\":\"...\",\"sections\":[{\"id\":\"executive_judgement\",\"title\":\"核心判断\",\"blocks\":[{\"type\":\"paragraph\",\"text\":\"...\"}]}]}。"
        "允许的 section id 包括 report_scope、executive_judgement、key_findings、risk_opportunity_assessment、"
        "attribution_logic、evidence_verification、model_visual_interpretation、recommendations、limitations。"
        "允许的 block type 包括 paragraph、items、evidence、visuals。items/evidence/visuals 的条目只使用面向读者的标题、摘要、理由、边界说明等文本。"
    )
    try:
        response = report_writer.invoke(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
            ]
        )
    except Exception as exc:
        return {"ok": False, "reason": f"报告写作模型调用失败：{exc}"}
    payload = _extract_writer_payload(response)
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "报告写作模型未返回可解析的 JSON"}
    title = _clean_text(payload.get("title")) or fallback_title
    sections = _normalize_writer_sections(payload.get("sections"))
    if not sections:
        return {"ok": False, "reason": "报告写作模型未返回有效章节"}
    errors = _validate_written_report(title=title, sections=sections, forbidden_values=forbidden_values)
    if errors:
        return {"ok": False, "reason": "报告写作模型输出未通过发布校验：" + "；".join(errors[:5])}
    return {"ok": True, "title": title, "sections": sections}


def _reader_packet_item(item: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "标题": _clean_text(item.get("title") or item.get("claim") or item.get("action") or item.get("name")),
            "摘要": _clean_text(item.get("readerSummary") or item.get("summary") or item.get("description") or item.get("caption")),
            "依据": _clean_text(item.get("basisSummary")),
            "理由": _clean_text(item.get("rationale")),
            "预期价值": _clean_text(item.get("expectedBenefit")),
            "风险提示": _clean_text(item.get("riskNote")),
            "核验状态": _clean_text(item.get("verificationStatus")),
            "支撑关系": _clean_text(item.get("supportRelationship")),
            "解读边界": _clean_text(item.get("interpretationBoundary")),
            "置信度": item.get("confidence"),
            "优先级": _clean_text(item.get("priority")),
        }
    )


def _extract_writer_payload(response: Any) -> dict[str, Any] | None:
    if isinstance(response, dict):
        return response
    content = getattr(response, "content", response)
    if isinstance(content, dict):
        return content
    text = _clean_text(content)
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


def _normalize_writer_sections(value: Any) -> list[dict[str, Any]]:
    allowed_section_ids = {
        "report_scope",
        "executive_judgement",
        "key_findings",
        "risk_opportunity_assessment",
        "attribution_logic",
        "evidence_verification",
        "model_visual_interpretation",
        "recommendations",
        "limitations",
    }
    sections: list[dict[str, Any]] = []
    for section in _list_of_dicts(value):
        section_id = _clean_text(section.get("id"))
        title = _clean_text(section.get("title"))
        if section_id not in allowed_section_ids or not title:
            continue
        blocks = _normalize_writer_blocks(section.get("blocks"))
        if blocks:
            sections.append({"id": section_id, "title": title, "blocks": blocks})
    return sections


def _normalize_writer_blocks(value: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in _list_of_dicts(value):
        block_type = _clean_text(block.get("type"))
        if block_type == "paragraph":
            text = _clean_text(block.get("text"))
            if text:
                blocks.append({"type": "paragraph", "text": text})
            continue
        if block_type in {"items", "evidence", "visuals"}:
            items = [_normalize_writer_item(item) for item in _list_of_dicts(block.get("items"))]
            items = [item for item in items if item]
            if items:
                blocks.append({"type": block_type, "items": items})
    return blocks


def _normalize_writer_item(item: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = (
        "title",
        "claim",
        "action",
        "name",
        "readerSummary",
        "basisSummary",
        "summary",
        "description",
        "text",
        "rationale",
        "expectedBenefit",
        "riskNote",
        "interpretationBoundary",
        "sourceDescription",
        "verificationStatus",
        "supportRelationship",
        "caption",
        "altText",
        "fallbackText",
        "type",
        "downloadUrl",
    )
    return _drop_empty({key: _clean_text(item.get(key)) for key in allowed_keys if item.get(key) not in (None, "", [], {})})


def _validate_written_report(*, title: str, sections: list[dict[str, Any]], forbidden_values: list[str]) -> list[str]:
    if not any(section.get("id") == "executive_judgement" for section in sections):
        return ["缺少核心判断章节"]
    if not any(section.get("id") in {"key_findings", "limitations"} for section in sections):
        return ["缺少发现或限制章节"]
    artifact = {"title": title, "sections": sections}
    markdown_body = render_report_markdown(artifact)
    html_body = render_report_html(artifact, markdown_body=markdown_body)
    errors = validate_published_report(markdown_body, html_body, forbidden_values=forbidden_values)
    lowered = markdown_body.lower()
    unsupported_tokens = ("未提供的事实", "自行假设", "凭经验判断", "数据库字段", "代码字段")
    errors.extend(f"unsupported content indicator: {token}" for token in unsupported_tokens if token in lowered or token in markdown_body)
    return errors


def _build_semantic_report_sections(semantic_model: dict[str, Any]) -> list[dict[str, Any]]:
    intent = _dict_value(semantic_model.get("reportIntent"))
    subject = _dict_value(semantic_model.get("subject"))
    scope = _dict_value(semantic_model.get("scope"))
    sections: list[dict[str, Any]] = []
    scope_items = [
        {"title": "企业", "summary": _clean_text(subject.get("name"))},
        {"title": "股票代码", "summary": _clean_text(subject.get("stockCode"))},
        {"title": "时间范围", "summary": _clean_text(scope.get("timeRange"))},
        {"title": "报告目标", "summary": _clean_text(intent.get("goal"))},
    ]
    sections.append(_section("report_scope", "报告范围", [_items_block([item for item in scope_items if item.get("summary")])]))
    sections.append(_section("executive_judgement", "核心判断", [_items_block(semantic_model.get("executiveJudgements"), empty_text="当前输入不足以形成可支撑的核心判断。")]))
    sections.append(_section("key_findings", "关键发现", [_items_block(semantic_model.get("keyFindings"), empty_text="当前未形成可支撑的实质性发现。")]))
    signal_blocks = []
    if _list_of_dicts(semantic_model.get("riskSignals")):
        signal_blocks.append(_items_block(semantic_model.get("riskSignals")))
    if _list_of_dicts(semantic_model.get("opportunitySignals")):
        signal_blocks.append(_items_block(semantic_model.get("opportunitySignals")))
    if signal_blocks:
        sections.append(_section("risk_opportunity_assessment", "风险与机会评估", signal_blocks))
    if _list_of_dicts(semantic_model.get("drivers")):
        sections.append(_section("attribution_logic", "归因与逻辑拆解", [_items_block(semantic_model.get("drivers"))]))
    sections.append(_section("evidence_verification", "来源与核验", [_evidence_block(semantic_model.get("evidenceChains"))]))
    visual_blocks = []
    if _list_of_dicts(semantic_model.get("visualNarratives")):
        visual_blocks.append(_visual_block(semantic_model.get("visualNarratives")))
    if _list_of_dicts(semantic_model.get("modelExplanations")):
        visual_blocks.append(_items_block(semantic_model.get("modelExplanations")))
    if visual_blocks:
        sections.append(_section("model_visual_interpretation", "模型与图表解读", visual_blocks))
    sections.append(_section("recommendations", "决策建议", [_items_block(semantic_model.get("recommendations"), empty_text="当前未形成可追溯的决策建议。")]))
    sections.append(_section("limitations", "限制说明", [_items_block(semantic_model.get("limitations"), empty_text="暂无额外限制。")]))
    return [section for section in sections if section.get("blocks")]


def validate_published_report(*bodies: str, forbidden_values: list[str] | None = None) -> list[str]:
    text = "\n".join(str(body or "") for body in bodies)
    errors: list[str] = []
    for token in sorted(PUBLISHED_REPORT_FORBIDDEN_LABELS, key=len, reverse=True):
        if token and token in text:
            errors.append(f"internal label leaked: {token}")
    for value in forbidden_values or []:
        clean = _clean_text(value)
        if len(clean) >= 4 and clean in text:
            errors.append(f"internal value leaked: {clean}")
    return errors


def render_report_markdown(artifact: dict[str, Any]) -> str:
    title = _clean_text(artifact.get("title")) or "分析报告"
    lines = [f"# {title}", ""]
    scope = _dict_value(artifact.get("scope"))
    meta_parts = []
    if not isinstance(artifact.get("semanticModel"), dict):
        for key, label in (
            ("targetCompany", "企业"),
            ("stockCode", "股票代码"),
            ("timeRange", "时间范围"),
            ("reportGoal", "报告目标"),
        ):
            value = _clean_text(scope.get(key))
            if value:
                meta_parts.append(f"{label}：{value}")
        if meta_parts:
            lines.extend(["## 报告范围", "", *[f"- {item}" for item in meta_parts], ""])

    for section in artifact.get("sections", []) if isinstance(artifact.get("sections"), list) else []:
        if not isinstance(section, dict):
            continue
        section_title = _clean_text(section.get("title"))
        if section_title:
            lines.extend([f"## {section_title}", ""])
        for block in section.get("blocks", []) if isinstance(section.get("blocks"), list) else []:
            _append_markdown_block(lines, block)
        if lines[-1] != "":
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_report_html(artifact: dict[str, Any], *, markdown_body: str | None = None) -> str:
    body = markdown_body if markdown_body is not None else render_report_markdown(artifact)
    parts: list[str] = []
    in_list = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            if in_list:
                parts.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
        elif line.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline_markdown_to_html(line[2:].strip())}</li>")
        elif line.startswith("!["):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(_image_markdown_to_html(line))
        else:
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<p>{_inline_markdown_to_html(line)}</p>")
    if in_list:
        parts.append("</ul>")
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(_clean_text(artifact.get('title')) or '分析报告')}</title>"
        "<style>body{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.65;max-width:920px;margin:32px auto;padding:0 24px;color:#17202a}"
        "h1,h2,h3{line-height:1.25}img{max-width:100%;height:auto}table{border-collapse:collapse;width:100%}td,th{border:1px solid #d8dee8;padding:6px}</style>"
        "</head><body>"
        + "\n".join(parts)
        + "</body></html>"
    )


def bounded_report_preview(markdown_body: str, *, limit: int = REPORT_PREVIEW_LIMIT) -> str:
    clean = str(markdown_body or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def report_download_metadata(report_id: str) -> dict[str, Any]:
    clean_report_id = _clean_text(report_id)
    return {
        "availableFormats": [REPORT_DOWNLOAD_FORMAT],
        "downloadUrls": {
            REPORT_DOWNLOAD_FORMAT: f"/api/workspace/reports/{clean_report_id}/download?format={REPORT_DOWNLOAD_FORMAT}"
        } if clean_report_id else {},
    }


def normalized_report_download_metadata(report_id: str, stored_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    del stored_metadata
    return report_download_metadata(report_id)


def report_preview_metadata(artifact: dict[str, Any]) -> dict[str, Any]:
    report_id = _clean_text(artifact.get("reportId"))
    metadata = normalized_report_download_metadata(report_id, _dict_value(artifact.get("downloadMetadata")))
    render_style = normalize_report_render_style(artifact.get("renderStyle") or _dict_value(artifact.get("rendering")).get("style"))
    return _drop_empty(
        {
            "reportId": report_id,
            "title": _clean_text(artifact.get("title")),
            "status": _clean_text(artifact.get("status")),
            "preview": _clean_text(artifact.get("preview") or bounded_report_preview(_clean_text(artifact.get("markdownBody")))),
            "availableFormats": metadata["availableFormats"],
            "downloadUrls": metadata["downloadUrls"],
            "previewUrl": report_preview_url(report_id) if report_id else "",
            "renderStyle": render_style,
            "regeneration": report_regeneration_metadata(report_id) if report_id else {},
            "limitations": artifact.get("limitations") if isinstance(artifact.get("limitations"), list) else [],
        }
    )


def normalize_report_render_style(value: Any) -> str:
    clean = _clean_text(value)
    allowed = {style["id"] for style in REPORT_RENDER_STYLES}
    return clean if clean in allowed else DEFAULT_REPORT_RENDER_STYLE


def report_render_styles_metadata() -> list[dict[str, str]]:
    return [dict(style) for style in REPORT_RENDER_STYLES]


def report_preview_url(report_id: str) -> str:
    clean_report_id = _clean_text(report_id)
    if not clean_report_id:
        return ""
    return f"/api/workspace/reports/{clean_report_id}/preview?format={REPORT_PREVIEW_FORMAT}"


def report_regeneration_metadata(report_id: str = "") -> dict[str, Any]:
    return _drop_empty(
        {
            "allowed": True,
            "reportId": _clean_text(report_id),
            "renderStyles": report_render_styles_metadata(),
            "defaultRenderStyle": DEFAULT_REPORT_RENDER_STYLE,
        }
    )


def build_analysis_module_artifacts(
    *,
    analysis_session: dict[str, Any],
    module_results: dict[str, dict[str, Any]],
    module_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    session_payload = _dict_value(analysis_session)
    ordered_module_ids = _string_list(module_ids or session_payload.get("enabledModules"))
    if not ordered_module_ids:
        ordered_module_ids = [module_id for module_id in module_results.keys() if _clean_text(module_id)]
    artifacts: list[dict[str, Any]] = []
    for module_id in ordered_module_ids:
        result = module_results.get(module_id)
        if not isinstance(result, dict):
            continue
        markdown_body = _module_markdown_body(result)
        if not markdown_body:
            continue
        title = _module_artifact_title(result, module_id=module_id)
        run_id = _clean_text(result.get("runId"))
        artifact_id = _clean_text(result.get("moduleArtifactId")) or _new_module_artifact_id()
        artifacts.append(
            _drop_empty(
                {
                    "schemaVersion": "analysis_module_artifact.v1",
                    "artifactId": artifact_id,
                    "moduleId": _clean_text(result.get("moduleId")) or module_id,
                    "moduleRunId": run_id,
                    "title": title,
                    "status": _clean_text(result.get("status")) or "completed",
                    "contentType": "text/markdown",
                    "markdownBody": markdown_body,
                    "analysisSession": {
                        "sessionId": _clean_text(session_payload.get("sessionId")),
                        "revision": _safe_int(session_payload.get("revision"), default=0),
                    },
                    "metadata": {
                        "displayName": _clean_text(result.get("displayName")),
                        "summary": _clean_text(result.get("summary")),
                        "moduleResult": result,
                    },
                }
            )
        )
    return artifacts


def build_report_generation_request(
    *,
    analysis_session: dict[str, Any],
    module_artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    artifact_ids = [_clean_text(item.get("artifactId")) for item in module_artifacts if isinstance(item, dict)]
    artifact_ids = [item for item in artifact_ids if item]
    if not artifact_ids:
        return {}
    session_payload = _dict_value(analysis_session)
    return _drop_empty(
        {
            "requestId": f"rreq_{uuid.uuid4().hex[:24]}",
            "analysisSessionId": _clean_text(session_payload.get("sessionId")),
            "analysisSessionRevision": _safe_int(session_payload.get("revision"), default=0),
            "moduleArtifactIds": artifact_ids,
            "renderStyles": report_render_styles_metadata(),
            "defaultRenderStyle": DEFAULT_REPORT_RENDER_STYLE,
        }
    )


def save_analysis_module_artifacts(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    role: str,
    conversation_id: str,
    artifacts: list[dict[str, Any]],
    analysis_session: dict[str, Any] | None = None,
) -> list[AnalysisModuleArtifact]:
    rows: list[AnalysisModuleArtifact] = []
    session_payload = _dict_value(analysis_session)
    now = datetime.utcnow()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_id = _clean_text(artifact.get("artifactId"))
        module_id = _clean_text(artifact.get("moduleId"))
        markdown_body = _clean_text(artifact.get("markdownBody") or artifact.get("textBody"))
        if not artifact_id or not module_id or not markdown_body:
            continue
        artifact_session = _dict_value(artifact.get("analysisSession"))
        analysis_session_id = _clean_text(session_payload.get("sessionId") or artifact_session.get("sessionId")) or None
        analysis_session_revision = _safe_int(
            session_payload.get("revision", artifact_session.get("revision")),
            default=0,
        )
        row = db.execute(
            select(AnalysisModuleArtifact).where(AnalysisModuleArtifact.artifact_id == artifact_id)
        ).scalar_one_or_none()
        if row is None:
            row = AnalysisModuleArtifact(
                artifact_id=artifact_id,
                user_id=user_id,
                workspace_id=workspace_id,
                role=role,
                conversation_id=conversation_id,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        row.analysis_session_id = analysis_session_id
        row.analysis_session_revision = analysis_session_revision
        row.module_id = module_id
        row.module_run_id = _clean_text(artifact.get("moduleRunId")) or None
        row.title = _clean_text(artifact.get("title")) or "模块分析结果"
        row.status = _clean_text(artifact.get("status")) or "completed"
        row.content_type = _clean_text(artifact.get("contentType")) or "text/markdown"
        row.markdown_body = markdown_body
        row.text_body = _clean_text(artifact.get("textBody"))
        row.artifact_json = {
            key: value
            for key, value in artifact.items()
            if key not in {"markdownBody", "textBody"}
        }
        row.metadata_json = _dict_value(artifact.get("metadata"))
        row.updated_at = now
        rows.append(row)
    if rows:
        db.flush()
    return rows


def analysis_module_artifact_to_payload(row: AnalysisModuleArtifact, *, include_body: bool = True) -> dict[str, Any]:
    payload = _drop_empty(
        {
            "artifactId": row.artifact_id,
            "moduleId": row.module_id,
            "moduleRunId": row.module_run_id,
            "title": row.title,
            "status": row.status,
            "contentType": row.content_type,
            "analysisSession": {
                "sessionId": row.analysis_session_id,
                "revision": int(row.analysis_session_revision or 0),
            },
            "createdAt": _format_datetime(row.created_at),
            "updatedAt": _format_datetime(row.updated_at),
        }
    )
    if include_body:
        payload["markdownBody"] = row.markdown_body or row.text_body or ""
    return payload


def get_analysis_module_artifacts_by_ids(
    db: Session,
    *,
    user_id: int,
    artifact_ids: list[str],
    workspace_id: str | None = None,
) -> list[AnalysisModuleArtifact]:
    clean_ids = _string_list(artifact_ids)
    if not clean_ids:
        return []
    criteria = [AnalysisModuleArtifact.user_id == user_id, AnalysisModuleArtifact.artifact_id.in_(clean_ids)]
    if workspace_id:
        criteria.append(AnalysisModuleArtifact.workspace_id == workspace_id)
    rows = db.execute(select(AnalysisModuleArtifact).where(*criteria)).scalars().all()
    row_by_id = {row.artifact_id: row for row in rows}
    return [row_by_id[artifact_id] for artifact_id in clean_ids if artifact_id in row_by_id]


def generate_analysis_report_from_module_artifacts(
    module_artifacts: list[AnalysisModuleArtifact],
    *,
    render_style: str = DEFAULT_REPORT_RENDER_STYLE,
    report_writer: Any | None = None,
) -> dict[str, Any] | None:
    rows = [row for row in module_artifacts if row.markdown_body or row.text_body]
    if not rows:
        return None
    clean_style = normalize_report_render_style(render_style)
    artifact = _artifact_report_from_module_text(rows, render_style=clean_style)
    artifact["renderStyle"] = clean_style
    artifact["sourceModuleArtifactIds"] = [row.artifact_id for row in rows]
    artifact["downloadMetadata"] = report_download_metadata(_clean_text(artifact.get("reportId")))
    artifact["preview"] = bounded_report_preview(_clean_text(artifact.get("markdownBody")))
    return artifact


def save_analysis_report_artifact(
    db: Session,
    *,
    user_id: int,
    workspace_id: str,
    role: str,
    conversation_id: str,
    artifact: dict[str, Any] | None,
) -> AnalysisReport | None:
    if not isinstance(artifact, dict) or not artifact:
        return None
    report_id = _clean_text(artifact.get("reportId"))
    if not report_id:
        return None
    scope = _dict_value(artifact.get("scope"))
    now = datetime.utcnow()
    row = db.execute(select(AnalysisReport).where(AnalysisReport.report_id == report_id)).scalar_one_or_none()
    if row is None:
        row = AnalysisReport(
            report_id=report_id,
            user_id=user_id,
            workspace_id=workspace_id,
            role=role,
            conversation_id=conversation_id,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    row.status = _clean_text(artifact.get("status")) or "completed"
    row.title = _clean_text(artifact.get("title")) or "分析报告"
    row.analysis_session_id = _clean_text(scope.get("analysisSessionId")) or None
    row.analysis_session_revision = _safe_int(scope.get("analysisSessionRevision"), default=0)
    row.enabled_modules_json = {"items": _string_list(scope.get("enabledModules"))}
    row.module_run_ids_json = _dict_value(scope.get("moduleRunIds"))
    row.artifact_json = {key: value for key, value in artifact.items() if key not in {"markdownBody", "htmlBody"}}
    row.markdown_body = _clean_text(artifact.get("markdownBody"))
    row.html_body = _clean_text(artifact.get("htmlBody"))
    row.visual_assets_json = {"items": _list_of_dicts(artifact.get("visualAssets"))}
    row.attachments_json = {"items": _list_of_dicts(artifact.get("attachments"))}
    row.limitations_json = {"items": artifact.get("limitations") if isinstance(artifact.get("limitations"), list) else []}
    row.download_metadata_json = report_download_metadata(report_id)
    row.updated_at = now
    db.flush()
    return row


def get_analysis_report(
    db: Session,
    *,
    user_id: int,
    report_id: str,
    workspace_id: str | None = None,
) -> AnalysisReport | None:
    criteria = [AnalysisReport.user_id == user_id, AnalysisReport.report_id == report_id]
    if workspace_id:
        criteria.append(AnalysisReport.workspace_id == workspace_id)
    return db.execute(select(AnalysisReport).where(*criteria)).scalar_one_or_none()


def analysis_report_to_payload(row: AnalysisReport, *, include_body: bool = False) -> dict[str, Any]:
    artifact = _dict_value(row.artifact_json)
    metadata = normalized_report_download_metadata(row.report_id, _dict_value(row.download_metadata_json))
    render_style = normalize_report_render_style(artifact.get("renderStyle") or _dict_value(artifact.get("rendering")).get("style"))
    payload = _drop_empty(
        {
            "reportId": row.report_id,
            "title": row.title,
            "status": row.status,
            "preview": _clean_text(artifact.get("preview") or bounded_report_preview(row.markdown_body or "")),
            "availableFormats": metadata["availableFormats"],
            "downloadUrls": metadata["downloadUrls"],
            "previewUrl": report_preview_url(row.report_id),
            "renderStyle": render_style,
            "regeneration": report_regeneration_metadata(row.report_id),
            "analysisSession": {
                "sessionId": row.analysis_session_id,
                "revision": int(row.analysis_session_revision or 0),
            },
            "enabledModules": _string_list((row.enabled_modules_json or {}).get("items", [])),
            "moduleRunIds": _dict_value(row.module_run_ids_json),
            "limitations": (row.limitations_json or {}).get("items", []) if isinstance(row.limitations_json, dict) else [],
            "createdAt": _format_datetime(row.created_at),
            "updatedAt": _format_datetime(row.updated_at),
        }
    )
    if include_body:
        payload["artifact"] = artifact
        payload["markdownBody"] = row.markdown_body or ""
        payload["htmlBody"] = row.html_body or ""
    return payload


def safe_report_filename(row: AnalysisReport, report_format: str) -> str:
    extension = REPORT_DOWNLOAD_FORMAT
    base = _ascii_filename(row.title or row.report_id).rsplit(".", 1)[0]
    return f"{base}-{row.report_id}.{extension}"


def find_report_asset(row: AnalysisReport, asset_id: str) -> dict[str, Any] | None:
    target = _clean_text(asset_id)
    if not target:
        return None
    artifact = _dict_value(row.artifact_json)
    for collection_name in ("visualAssets", "attachments"):
        for item in _list_of_dicts(artifact.get(collection_name)):
            if _clean_text(item.get("assetId") or item.get("id")) == target:
                return item
    return None


def inline_asset_response_payload(asset: dict[str, Any]) -> tuple[bytes, str, str] | None:
    content_type = _clean_text(asset.get("contentType")) or "application/octet-stream"
    filename = _clean_filename(asset.get("filename") or asset.get("title") or asset.get("assetId") or "asset")
    inline_content = _clean_text(asset.get("inlineContent"))
    if inline_content:
        if content_type == "application/octet-stream":
            content_type = "text/plain; charset=utf-8"
        return inline_content.encode("utf-8"), content_type, filename
    render_payload = asset.get("renderPayload")
    if isinstance(render_payload, dict) and render_payload:
        import json

        return json.dumps(render_payload, ensure_ascii=False, indent=2).encode("utf-8"), "application/json", filename
    return None


def report_row_forbidden_values(row: AnalysisReport) -> list[str]:
    artifact = _dict_value(row.artifact_json)
    values = set(_string_list((row.enabled_modules_json or {}).get("items", [])))
    values.update(_clean_text(value) for value in _dict_value(row.module_run_ids_json).values())
    values.add(_clean_text(row.analysis_session_id))
    for item in _list_of_dicts(artifact.get("moduleSummaries")):
        values.add(_clean_text(item.get("moduleId")))
        values.add(_clean_text(item.get("runId")))
    internal_items = _dict_value(_dict_value(artifact.get("internalTraceIndex")).get("items"))
    for item in internal_items.values():
        if not isinstance(item, dict):
            continue
        values.add(_clean_text(item.get("moduleId")))
        values.add(_clean_text(item.get("runId")))
    return [value for value in values if len(value) >= 4]


def render_report_pdf(
    artifact: dict[str, Any],
    *,
    markdown_body: str | None = None,
    forbidden_values: list[str] | None = None,
) -> bytes:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("pdf rendering requires pymupdf dependency") from exc

    artifact = _dict_value(artifact)
    markdown_body = _clean_text(markdown_body if markdown_body is not None else artifact.get("markdownBody"))
    if not markdown_body:
        markdown_body = render_report_markdown(artifact)
    segments = _report_pdf_segments(markdown_body, artifact)
    if not segments:
        fallback_title = html.escape(_clean_text(artifact.get("title")) or "分析报告")
        segments = [f"<h1>{fallback_title}</h1>", "<p>报告内容为空。</p>"]

    doc = fitz.open()
    page = doc.new_page(width=REPORT_PDF_PAGE_WIDTH, height=REPORT_PDF_PAGE_HEIGHT)
    cursor_y = REPORT_PDF_MARGIN_TOP
    css = _report_pdf_css(artifact)
    for segment in segments:
        page, cursor_y = _insert_report_pdf_segment(doc, page, cursor_y, segment, fitz_module=fitz, css=css)
    pdf_bytes = doc.tobytes(deflate=True, garbage=3)
    doc.close()

    validation_errors = validate_report_pdf_bytes(pdf_bytes, forbidden_values=forbidden_values)
    if validation_errors:
        raise PublishedReportValidationError("；".join(validation_errors[:5]))
    return pdf_bytes


def validate_report_pdf_bytes(pdf_bytes: bytes, *, forbidden_values: list[str] | None = None) -> list[str]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("pdf validation requires pymupdf dependency") from exc
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        text = "\n".join(page.get_text("text") for page in document)
    return validate_published_report(text, forbidden_values=forbidden_values)


def _report_pdf_css(artifact: dict[str, Any]) -> str:
    style_id = normalize_report_render_style(
        artifact.get("renderStyle") or _dict_value(artifact.get("rendering")).get("style")
    )
    return REPORT_PDF_CSS + REPORT_PDF_STYLE_CSS.get(style_id, "")


def _insert_report_pdf_segment(
    doc: Any,
    page: Any,
    cursor_y: float,
    segment: str,
    *,
    fitz_module: Any,
    css: str,
) -> tuple[Any, float]:
    right = REPORT_PDF_PAGE_WIDTH - REPORT_PDF_MARGIN_X
    bottom = REPORT_PDF_PAGE_HEIGHT - REPORT_PDF_MARGIN_BOTTOM
    rect = fitz_module.Rect(REPORT_PDF_MARGIN_X, cursor_y, right, bottom)
    spare_height, _ = page.insert_htmlbox(rect, segment, css=css, scale_low=1)
    if spare_height == -1:
        page = doc.new_page(width=REPORT_PDF_PAGE_WIDTH, height=REPORT_PDF_PAGE_HEIGHT)
        cursor_y = REPORT_PDF_MARGIN_TOP
        rect = fitz_module.Rect(REPORT_PDF_MARGIN_X, cursor_y, right, bottom)
        spare_height, _ = page.insert_htmlbox(rect, segment, css=css, scale_low=1)
    if spare_height == -1:
        fallback_html = f"<p>{html.escape(_report_pdf_plain_text(segment))}</p>"
        spare_height, _ = page.insert_htmlbox(rect, fallback_html, css=css, scale_low=0.7)
    if spare_height == -1:
        final_html = "<p>该段内容过长，已在下载版中省略，请回到系统内查看完整预览。</p>"
        spare_height, _ = page.insert_htmlbox(rect, final_html, css=css, scale_low=0.7)
    next_y = bottom - max(spare_height, 0) + REPORT_PDF_SEGMENT_GAP
    if next_y > bottom - 20:
        page = doc.new_page(width=REPORT_PDF_PAGE_WIDTH, height=REPORT_PDF_PAGE_HEIGHT)
        next_y = REPORT_PDF_MARGIN_TOP
    return page, next_y


def _report_pdf_segments(markdown_body: str, artifact: dict[str, Any]) -> list[str]:
    asset_lookup = _report_pdf_asset_lookup(artifact)
    lines = str(markdown_body or "").splitlines()
    segments: list[str] = []
    index = 0
    while index < len(lines):
        raw_line = lines[index].rstrip()
        line = raw_line.strip()
        if not line:
            index += 1
            continue
        if line.startswith("# "):
            segments.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
            index += 1
            continue
        if line.startswith("## "):
            segments.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
            index += 1
            continue
        if line.startswith("### "):
            segments.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
            index += 1
            continue
        if line.startswith("!["):
            segments.append(_report_pdf_image_segment(line, asset_lookup))
            index += 1
            continue
        if re.match(r"^\s*-\s+", raw_line):
            items: list[str] = []
            while index < len(lines):
                current_raw = lines[index].rstrip()
                if not re.match(r"^\s*-\s+", current_raw):
                    break
                current_text = re.sub(r"^\s*-\s+", "", current_raw.strip())
                items.append(f"<li>{_inline_markdown_to_html(current_text)}</li>")
                index += 1
            if items:
                segments.append("<ul>" + "".join(items) + "</ul>")
            continue

        paragraph_lines = [line]
        index += 1
        while index < len(lines):
            candidate_raw = lines[index].rstrip()
            candidate = candidate_raw.strip()
            if not candidate or candidate.startswith("#") or candidate.startswith("![") or re.match(r"^\s*-\s+", candidate_raw):
                break
            paragraph_lines.append(candidate)
            index += 1
        segments.append("<p>" + "<br>".join(_inline_markdown_to_html(item) for item in paragraph_lines) + "</p>")
    return segments


def _report_pdf_image_segment(line: str, asset_lookup: dict[str, dict[str, Any]]) -> str:
    match = re.match(r"!\[(.*?)\]\((.*?)\)", line)
    if not match:
        return f"<p>{_inline_markdown_to_html(line)}</p>"
    alt_text, url = match.groups()
    clean_url = _clean_text(url)
    asset_id = _report_asset_id_from_url(clean_url)
    asset = asset_lookup.get(clean_url) or asset_lookup.get(asset_id)
    title = _clean_text(asset.get("title") if isinstance(asset, dict) else "") or _clean_text(alt_text) or "图表"
    caption = _clean_text(asset.get("caption") if isinstance(asset, dict) else "") or _clean_text(
        asset.get("readerSummary") if isinstance(asset, dict) else ""
    ) or _clean_text(asset.get("description") if isinstance(asset, dict) else "")
    boundary = _clean_text(asset.get("interpretationBoundary") if isinstance(asset, dict) else "")
    data_url = _report_pdf_asset_data_url(asset) if isinstance(asset, dict) else ""
    if data_url:
        parts = [
            "<figure>",
            f"<img src=\"{html.escape(data_url, quote=True)}\" alt=\"{html.escape(_clean_text(alt_text) or title, quote=True)}\">",
        ]
        if title or caption or boundary:
            figcaption = " ".join(part for part in (title, caption, boundary) if part)
            parts.append(f"<figcaption>{html.escape(figcaption)}</figcaption>")
        parts.append("</figure>")
        return "".join(parts)
    fallback = caption or boundary or _clean_text(alt_text) or "该图片资产未提供可嵌入内容。"
    return (
        "<div class=\"pdf-visual-fallback\">"
        f"<p><strong>{html.escape(title)}</strong></p>"
        f"<p>{html.escape(fallback)}</p>"
        "</div>"
    )


def _report_pdf_asset_lookup(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for collection_name in ("visualAssets", "attachments"):
        for asset in _list_of_dicts(artifact.get(collection_name)):
            for key in (
                asset.get("downloadUrl"),
                asset.get("assetId"),
                asset.get("id"),
            ):
                clean = _clean_text(key)
                if clean:
                    lookup[clean] = asset
    return lookup


def _report_asset_id_from_url(value: str) -> str:
    match = re.search(r"/assets/([^/]+)/download", _clean_text(value))
    return _clean_text(match.group(1)) if match else ""


def _report_pdf_asset_data_url(asset: dict[str, Any]) -> str:
    content_type = _clean_text(asset.get("contentType")).split(";", 1)[0].lower()
    if not content_type.startswith("image/"):
        return ""
    image_bytes = _report_pdf_asset_bytes(asset, content_type=content_type)
    if not image_bytes:
        return ""
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _report_pdf_asset_bytes(asset: dict[str, Any], *, content_type: str) -> bytes:
    inline_content = _clean_text(asset.get("inlineContent"))
    if inline_content:
        decoded = _decode_pdf_image_bytes(inline_content)
        if decoded:
            return decoded

    render_payload = _dict_value(asset.get("renderPayload"))
    for key in ("dataUrl", "imageData", "imageBase64", "base64", "bytesBase64", "src", "url"):
        decoded = _decode_pdf_image_bytes(render_payload.get(key))
        if decoded:
            return decoded

    payload = inline_asset_response_payload(asset)
    if payload is None:
        return b""
    raw_bytes, payload_content_type, _ = payload
    payload_type = _clean_text(payload_content_type).split(";", 1)[0].lower()
    if payload_type.startswith("image/"):
        return raw_bytes
    if content_type.startswith("image/"):
        decoded = _decode_pdf_image_bytes(raw_bytes.decode("utf-8", errors="ignore"))
        if decoded:
            return decoded
    return b""


def _decode_pdf_image_bytes(value: Any) -> bytes:
    text = _clean_text(value)
    if not text:
        return b""
    if text.startswith("data:"):
        match = re.match(r"data:([^;,]+)?(;base64)?,(.*)", text, flags=re.S)
        if not match:
            return b""
        payload = match.group(3)
        if match.group(2):
            try:
                return base64.b64decode(payload, validate=False)
            except (ValueError, TypeError):
                return b""
        return payload.encode("utf-8")
    try:
        return base64.b64decode(text, validate=True)
    except (ValueError, TypeError):
        return b""


def _report_pdf_plain_text(segment: str) -> str:
    clean = re.sub(r"<br\s*/?>", "\n", str(segment or ""), flags=re.I)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = html.unescape(clean)
    clean = re.sub(r"[ \t]+", " ", clean)
    clean = re.sub(r"\n\s+", "\n", clean)
    return clean.strip()


def _build_report_sections(
    *,
    title: str,
    status: str,
    shared_summary: dict[str, Any],
    enabled_modules: list[str],
    session_payload: dict[str, Any],
    module_run_ids: dict[str, Any],
    contributions: list[dict[str, Any]],
    module_results: list[dict[str, Any]],
    limitations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings = _all_items(contributions, "findings")
    attribution = _all_items(contributions, "attributionInputs")
    logic = _all_items(contributions, "logicInputs")
    recommendations = _all_items(contributions, "recommendationInputs")
    evidence = _all_items(contributions, "evidence")
    model_outputs = _all_items(contributions, "modelOutputs")
    visual_assets = _all_items(contributions, "visualAssets")
    sections = [
        _section(
            "user_need",
            "用户核心需求",
            [
                _paragraph(
                    _clean_text(shared_summary.get("reportGoal"))
                    or f"围绕 {(_clean_text(shared_summary.get('enterpriseName')) or '目标企业')} 的已选分析模块输出生成定制化决策报告。"
                )
            ],
        ),
        _section("executive_summary", "执行摘要", [_paragraph(_executive_summary_text(findings, limitations, status=status))]),
        _section("key_findings", "关键发现", [_items_block(findings, empty_text="当前模块未提供可支持的实质性发现。")]),
        _section("attribution_analysis", "归因分析", [_items_block(attribution, empty_text="当前模块未提供可追溯的归因链。")]),
        _section("logic_breakdown", "逻辑拆解", [_items_block(logic, empty_text="当前模块未提供可展开的逻辑步骤。")]),
        _section("decision_recommendations", "决策建议", [_items_block(recommendations, empty_text="当前模块未提供可追溯的建议输入。")]),
        _section("source_traceability", "信息来源追溯", [_evidence_block(evidence)]),
    ]
    if visual_assets or model_outputs:
        sections.append(_section("visual_model_outputs", "图表与模型输出", [_visual_block(visual_assets), _items_block(model_outputs, empty_text="暂无模型输出。")]))
    for contribution, module_result in zip(contributions, module_results):
        module_id = _clean_text(contribution.get("moduleId"))
        if module_id not in enabled_modules:
            continue
        sections.append(
            _section(
                f"module_{module_id}",
                _clean_text(contribution.get("displayName")) or module_id,
                [
                    _paragraph(_clean_text(module_result.get("summary")) or f"模块状态：{_clean_text(contribution.get('status')) or 'unknown'}"),
                    _items_block(contribution.get("findings"), empty_text="该模块没有可纳入报告的实质性发现。"),
                ],
            )
        )
    snapshot_lines = [
        f"报告标题：{title}",
        f"分析会话：{_clean_text(session_payload.get('sessionId')) or 'transient'} / revision={_safe_int(session_payload.get('revision'), default=0)}",
        "已选模块：" + ("、".join(enabled_modules) or "无"),
    ]
    if module_run_ids:
        snapshot_lines.append("模块运行标识：" + "；".join(f"{key}={value}" for key, value in module_run_ids.items()))
    sections.append(_section("snapshot", "生成快照", [_items_block([{"title": item, "summary": ""} for item in snapshot_lines])]))
    sections.append(_section("limitations", "限制说明", [_items_block(limitations, empty_text="暂无额外限制。")]))
    return sections


def _append_markdown_block(lines: list[str], block: Any) -> None:
    if not isinstance(block, dict):
        return
    block_type = _clean_text(block.get("type"))
    if block_type == "paragraph":
        text = _clean_text(block.get("text"))
        if text:
            lines.extend([text, ""])
    elif block_type == "items":
        items = block.get("items", [])
        if not isinstance(items, list) or not items:
            empty_text = _clean_text(block.get("emptyText"))
            if empty_text:
                lines.extend([empty_text, ""])
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            title = _clean_text(item.get("title") or item.get("claim") or item.get("action") or item.get("name"))
            summary = _clean_text(
                item.get("readerSummary")
                or item.get("basisSummary")
                or item.get("summary")
                or item.get("description")
                or item.get("text")
                or item.get("reasoning")
            )
            prefix = f"- **{title}**" if title else "-"
            lines.append(f"{prefix}：{summary}" if summary else prefix)
            rationale = _clean_text(item.get("rationale"))
            if rationale:
                lines.append(f"  - 理由：{rationale}")
            expected_benefit = _clean_text(item.get("expectedBenefit"))
            if expected_benefit:
                lines.append(f"  - 预期价值：{expected_benefit}")
            risk_note = _clean_text(item.get("riskNote"))
            if risk_note:
                lines.append(f"  - 风险提示：{risk_note}")
            boundary = _clean_text(item.get("interpretationBoundary"))
            if boundary:
                lines.append(f"  - 解读边界：{boundary}")
        lines.append("")
    elif block_type == "evidence":
        evidence = block.get("items", [])
        if not isinstance(evidence, list) or not evidence:
            lines.extend(["暂无可引用来源。", ""])
            return
        for item in evidence:
            if not isinstance(item, dict):
                continue
            title = _clean_text(item.get("title") or item.get("sourceDescription")) or "来源"
            text = _clean_text(item.get("readerSummary") or item.get("summary") or item.get("description"))
            source = _clean_text(item.get("sourceDescription"))
            verification = _clean_text(item.get("verificationStatus"))
            support = _clean_text(item.get("supportRelationship"))
            lines.append(f"- **{title}**：{text or source}")
            if source and source != title:
                lines.append(f"  - 来源说明：{source}")
            if verification:
                lines.append(f"  - 核验状态：{verification}")
            if support:
                lines.append(f"  - 支撑关系：{support}")
        lines.append("")
    elif block_type == "visuals":
        for asset in block.get("items", []) if isinstance(block.get("items"), list) else []:
            if not isinstance(asset, dict):
                continue
            title = _clean_text(asset.get("title"))
            url = _clean_text(asset.get("downloadUrl"))
            alt = _clean_text(asset.get("altText") or title)
            caption = _clean_text(asset.get("caption") or asset.get("readerSummary") or asset.get("description"))
            if url and str(asset.get("type", "")).lower() == "image":
                lines.append(f"![{alt}]({url})")
            else:
                lines.append(f"- **{title or '图表'}**：{caption or alt}")
                fallback = _clean_text(asset.get("fallbackText"))
                if fallback and fallback != caption:
                    lines.append(f"  - 降级呈现：{fallback}")
            if caption:
                lines.append(f"  - 说明：{caption}")
            boundary = _clean_text(asset.get("interpretationBoundary"))
            if boundary:
                lines.append(f"  - 解读边界：{boundary}")
        lines.append("")


def _semantic_profile(contribution: dict[str, Any]) -> dict[str, Any]:
    profile = _dict_value(contribution.get("semanticContributionProfile"))
    if profile:
        return _drop_empty(
            {
                "profileVersion": _clean_text(profile.get("profileVersion")) or REPORT_SEMANTIC_CONTRIBUTION_PROFILE_VERSION,
                "capabilityTypes": _string_list(profile.get("capabilityTypes")),
                "supportedSemanticItems": _string_list(profile.get("supportedSemanticItems")),
            }
        )
    supported = []
    for key, item_type in (
        ("findings", "finding"),
        ("evidence", "evidence"),
        ("attributionInputs", "driver"),
        ("logicInputs", "driver"),
        ("recommendationInputs", "recommendation"),
        ("modelOutputs", "model_explanation"),
        ("visualAssets", "visual"),
    ):
        if _list_of_dicts(contribution.get(key)) and item_type not in supported:
            supported.append(item_type)
    return {
        "profileVersion": REPORT_SEMANTIC_CONTRIBUTION_PROFILE_VERSION,
        "capabilityTypes": _semantic_capability_types(contribution),
        "supportedSemanticItems": supported,
    }


def _semantic_capability_types(contribution: dict[str, Any]) -> list[str]:
    kinds = {_clean_text(item.get("kind")).lower() for item in _list_of_dicts(contribution.get("findings"))}
    titles = " ".join(_clean_text(item.get("title")) for item in _list_of_dicts(contribution.get("findings")))
    result: list[str] = []
    if "risk" in kinds or "风险" in titles:
        result.append("risk_assessment")
    if "opportunity" in kinds or "机会" in titles:
        result.append("opportunity_assessment")
    if _list_of_dicts(contribution.get("modelOutputs")):
        result.append("model_explanation")
    if not result:
        result.append("general_analysis")
    return result


def _semantic_finding(item: dict[str, Any], *, blocked_terms: set[str]) -> dict[str, Any]:
    title = _reader_text(item.get("title"), blocked_terms=blocked_terms) or "关键发现"
    summary = _reader_text(item.get("summary"), blocked_terms=blocked_terms)
    if not title and not summary:
        return {}
    semantic_id = _semantic_id("finding", item)
    return _drop_empty(
        {
            "id": semantic_id,
            "title": title,
            "claim": title,
            "readerSummary": summary or title,
            "basisSummary": _basis_summary(item),
            "category": _reader_text(item.get("kind"), blocked_terms=blocked_terms),
            "confidence": item.get("confidence"),
            "priority": _reader_text(item.get("priority"), blocked_terms=blocked_terms),
            "supportRefs": [semantic_id],
        }
    )


def _semantic_driver(item: dict[str, Any], *, blocked_terms: set[str]) -> dict[str, Any]:
    title = _reader_text(item.get("title"), blocked_terms=blocked_terms) or "影响因素"
    summary = _reader_text(item.get("summary") or item.get("rationale"), blocked_terms=blocked_terms)
    if not summary and title == "影响因素":
        return {}
    return _drop_empty(
        {
            "id": _semantic_id("driver", item),
            "title": title,
            "readerSummary": summary or title,
            "basisSummary": _basis_summary(item),
            "direction": _reader_text(item.get("direction"), blocked_terms=blocked_terms),
            "strength": item.get("strength"),
            "confidence": item.get("confidence"),
            "interpretationBoundary": _reader_text(item.get("interpretationBoundary"), blocked_terms=blocked_terms),
        }
    )


def _semantic_evidence_chain(item: dict[str, Any], *, blocked_terms: set[str]) -> dict[str, Any]:
    source_name = _reader_text(item.get("sourceName") or item.get("title"), blocked_terms=blocked_terms)
    source_type = _source_type_label(item)
    summary = _reader_text(item.get("summary") or item.get("evidenceText") or item.get("description"), blocked_terms=blocked_terms)
    url = _clean_text(item.get("url"))
    source_description = source_name or source_type or (url if url.startswith(("http://", "https://")) else "")
    if not summary and not source_description:
        return {}
    return _drop_empty(
        {
            "id": _semantic_id("evidence", item),
            "title": source_description or "来源",
            "readerSummary": summary or "该来源用于支撑相关判断，需结合上下文阅读。",
            "sourceDescription": source_description,
            "verificationStatus": _reader_text(item.get("verificationStatus"), blocked_terms=blocked_terms) or "已纳入结构化分析输入，需以后续事实更新复核。",
            "supportRelationship": _reader_text(item.get("supportRelationship"), blocked_terms=blocked_terms) or "支撑报告中的相关发现或限制说明。",
            "uncertainty": _reader_text(item.get("uncertainty"), blocked_terms=blocked_terms),
        }
    )


def _semantic_model_explanation(item: dict[str, Any], *, blocked_terms: set[str]) -> dict[str, Any]:
    title = _reader_text(item.get("title"), blocked_terms=blocked_terms) or "模型解释"
    summary = _reader_text(item.get("summary") or item.get("description"), blocked_terms=blocked_terms)
    if not summary and title == "模型解释":
        return {}
    boundary = _reader_text(item.get("interpretationBoundary"), blocked_terms=blocked_terms) or "模型得分、特征贡献或预测结果用于解释模型输出，不等同于现实世界因果关系。"
    return _drop_empty(
        {
            "id": _semantic_id("model", item),
            "title": title,
            "readerSummary": summary or title,
            "basisSummary": _basis_summary(item),
            "interpretationBoundary": boundary,
            "confidence": item.get("confidence"),
        }
    )


def _semantic_visual_narrative(item: dict[str, Any], *, blocked_terms: set[str]) -> dict[str, Any]:
    title = _reader_text(item.get("title"), blocked_terms=blocked_terms) or "分析图表"
    caption = _reader_text(item.get("caption") or item.get("description"), blocked_terms=blocked_terms)
    render_payload = _dict_value(item.get("renderPayload"))
    fallback = _reader_text(render_payload.get("text") or render_payload.get("summary") or item.get("inlineContent"), blocked_terms=blocked_terms)
    limitations = _list_of_dicts(item.get("limitations"))
    limitation_text = "；".join(_reader_text(entry.get("summary"), blocked_terms=blocked_terms) for entry in limitations if _reader_text(entry.get("summary"), blocked_terms=blocked_terms))
    boundary = _reader_text(item.get("interpretationBoundary"), blocked_terms=blocked_terms) or limitation_text
    if _clean_text(item.get("subtype")).lower() in {"shap_summary_plot", "feature_importance"} and "因果" not in boundary:
        boundary = (boundary + " " if boundary else "") + "模型贡献不等于现实因果关系。"
    return _drop_empty(
        {
            "id": _semantic_id("visual", item),
            "type": _clean_text(item.get("type")),
            "title": title,
            "caption": caption or fallback or title,
            "readerSummary": caption or fallback or title,
            "fallbackText": fallback,
            "altText": _reader_text(item.get("altText"), blocked_terms=blocked_terms) or title,
            "interpretationBoundary": boundary,
            "assetRef": _clean_text(item.get("assetId") or item.get("id")),
        }
    )


def _semantic_recommendation(item: dict[str, Any], *, blocked_terms: set[str], grounded_finding_ids: set[str]) -> dict[str, Any]:
    refs = _trace_ids(item.get("traceRefs"))
    if grounded_finding_ids and refs and not refs.intersection(grounded_finding_ids):
        return {}
    title = _reader_text(item.get("title"), blocked_terms=blocked_terms) or "建议事项"
    summary = _reader_text(item.get("summary"), blocked_terms=blocked_terms)
    rationale = _reader_text(item.get("rationale"), blocked_terms=blocked_terms) or summary
    if not summary and title == "建议事项":
        return {}
    return _drop_empty(
        {
            "id": _semantic_id("recommendation", item),
            "title": title,
            "action": title,
            "readerSummary": summary or rationale or title,
            "rationale": rationale,
            "expectedBenefit": _reader_text(item.get("expectedBenefit"), blocked_terms=blocked_terms),
            "riskNote": _reader_text(item.get("riskNote"), blocked_terms=blocked_terms),
            "priority": _reader_text(item.get("priority"), blocked_terms=blocked_terms),
            "confidence": item.get("confidence"),
        }
    )


def _semantic_limitation(item: dict[str, Any], *, blocked_terms: set[str]) -> dict[str, Any]:
    summary = _reader_text(item.get("summary") if isinstance(item, dict) else item, blocked_terms=blocked_terms)
    if not summary:
        return {}
    return _drop_empty({"id": _semantic_id("limitation", item if isinstance(item, dict) else {"summary": summary}), "title": "限制说明", "readerSummary": summary, "summary": summary})


def _semantic_id(prefix: str, item: dict[str, Any]) -> str:
    raw = _clean_text(item.get("id") or item.get("assetId") or item.get("title") or item.get("summary"))
    if not raw:
        raw = uuid.uuid4().hex[:12]
    token = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", raw).strip("_")[:48]
    return f"sem_{prefix}_{token or uuid.uuid4().hex[:12]}"


def _reader_text(value: Any, *, blocked_terms: set[str]) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    for term in sorted(blocked_terms, key=len, reverse=True):
        if not term or term not in text:
            continue
        if re.fullmatch(r"[A-Za-z0-9_.:\-/]+", term):
            text = text.replace(term, "")
        else:
            text = text.replace(term, "相关分析")
    text = re.sub(r"\s+", " ", text).strip(" ；;，,")
    return text


def _internal_reader_blocklist(
    *,
    enabled_modules: list[str],
    module_run_ids: dict[str, Any],
    contributions: list[dict[str, Any]],
    module_results: list[dict[str, Any]],
) -> set[str]:
    terms = set(enabled_modules)
    terms.update(_clean_text(value) for value in module_run_ids.values())
    for contribution in contributions:
        terms.add(_clean_text(contribution.get("moduleId")))
        terms.add(_clean_text(contribution.get("displayName")))
        for collection_name in ("findings", "evidence", "attributionInputs", "logicInputs", "recommendationInputs", "modelOutputs", "visualAssets", "attachments", "limitations"):
            for item in _list_of_dicts(contribution.get(collection_name)):
                terms.add(_clean_text(item.get("moduleId")))
    for result in module_results:
        terms.add(_clean_text(result.get("moduleId")))
        terms.add(_clean_text(result.get("displayName")))
        terms.add(_clean_text(result.get("runId")))
    return {term for term in terms if len(term) >= 3}


def _basis_summary(item: dict[str, Any]) -> str:
    refs = _trace_ids(item.get("traceRefs"))
    if refs:
        return "该判断可追溯到已完成的结构化分析材料。"
    if _string_list(item.get("sourceIds")):
        return "该判断基于已纳入的来源材料。"
    if _string_list(item.get("eventIds")):
        return "该判断基于已纳入的事件材料。"
    return ""


def _source_type_label(item: dict[str, Any]) -> str:
    source_type = _clean_text(item.get("sourceType")).lower()
    labels = {
        "web": "公开网页",
        "rag": "知识库文档",
        "policy": "政策文件",
        "announcement": "公告文件",
        "bidding": "招投标信息",
        "model": "模型输出",
    }
    return labels.get(source_type, _reader_text(source_type, blocked_terms=set()))


def _find_similar_semantic_item(items: list[dict[str, Any]], candidate: dict[str, Any]) -> dict[str, Any] | None:
    title = _clean_text(candidate.get("title"))
    claim = _clean_text(candidate.get("claim"))
    for item in items:
        if title and title == _clean_text(item.get("title")):
            return item
        if claim and claim == _clean_text(item.get("claim")):
            return item
    return None


def _merge_semantic_item(target: dict[str, Any], candidate: dict[str, Any]) -> None:
    if not _clean_text(target.get("readerSummary")) and _clean_text(candidate.get("readerSummary")):
        target["readerSummary"] = candidate["readerSummary"]
    if _clean_text(candidate.get("basisSummary")) and _clean_text(candidate.get("basisSummary")) not in _clean_text(target.get("basisSummary")):
        target["basisSummary"] = "；".join(part for part in [_clean_text(target.get("basisSummary")), _clean_text(candidate.get("basisSummary"))] if part)
    target["supportRefs"] = list(dict.fromkeys([*_string_list(target.get("supportRefs")), *_string_list(candidate.get("supportRefs"))]))


def _dedupe_semantic_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = _clean_text(item.get("readerSummary") or item.get("claim") or item.get("title") or item.get("id"))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _add_trace(
    trace_index: dict[str, Any],
    semantic_id: str,
    *,
    contribution: dict[str, Any],
    item: dict[str, Any],
    kind: str,
    profile: dict[str, Any],
) -> None:
    trace_index[semantic_id] = _drop_empty(
        {
            "kind": kind,
            "moduleId": _clean_text(contribution.get("moduleId")),
            "displayName": _clean_text(contribution.get("displayName")),
            "status": _clean_text(contribution.get("status")),
            "itemId": _clean_text(item.get("id") or item.get("assetId")),
            "traceRefs": _normalize_trace_refs(item.get("traceRefs")),
            "sourceIds": _string_list(item.get("sourceIds")),
            "eventIds": _string_list(item.get("eventIds")),
            "semanticContributionProfile": profile,
        }
    )


def _executive_judgements_from_semantics(
    *,
    status: str,
    findings: list[dict[str, Any]],
    limitations: list[dict[str, Any]],
    blocked_terms: set[str],
) -> list[dict[str, Any]]:
    if findings:
        finding_count = len(findings)
        return [
            _drop_empty(
                {
                    "id": "sem_judgement_primary",
                    "title": "核心判断",
                    "claim": "已形成可追溯的结构化判断。",
                    "readerSummary": f"本报告基于已完成的结构化分析材料生成，当前状态为 {status}。已识别 {finding_count} 项需要关注的判断方向，正文按发现、成因、来源和建议展开。",
                    "basisSummary": "所有核心判断均由已纳入的分析材料、证据链、模型解释或限制说明支撑。",
                }
            )
        ]
    if limitations:
        return [
            {
                "id": "sem_judgement_limited",
                "title": "核心判断",
                "claim": "当前材料不足以形成充分的实质性结论。",
                "readerSummary": f"本报告当前状态为 {status}。由于可支撑材料不足，正文主要呈现限制、来源缺口与后续复核方向。",
            }
        ]
    return [
        {
            "id": "sem_judgement_empty",
            "title": "核心判断",
            "claim": "当前尚未形成可支撑的实质性结论。",
            "readerSummary": f"本报告当前状态为 {status}，尚未获得足够可支撑材料。",
        }
    ]


def _semantic_quality_flags(semantic_model: dict[str, Any], *, stale_modules: list[str]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if stale_modules:
        flags.append(_quality_flag("stale_inputs", "warning", "部分分析输入已过期，报告仅作为降级快照。"))
    if not _list_of_dicts(semantic_model.get("keyFindings")):
        flags.append(_quality_flag("missing_findings", "warning", "未形成可支撑的实质性发现。"))
    if _list_of_dicts(semantic_model.get("recommendations")) and not _list_of_dicts(semantic_model.get("keyFindings")):
        flags.append(_quality_flag("weak_recommendations", "warning", "建议缺少关键发现支撑。"))
    return flags


def _quality_flag(flag_type: str, severity: str, message: str) -> dict[str, Any]:
    return {"type": flag_type, "severity": severity, "message": _clean_text(message)}


def _published_forbidden_values(*, enabled_modules: list[str], module_run_ids: dict[str, Any], contributions: list[dict[str, Any]]) -> list[str]:
    values = set(enabled_modules)
    values.update(_clean_text(value) for value in module_run_ids.values())
    for contribution in contributions:
        values.add(_clean_text(contribution.get("moduleId")))
        for collection_name in ("findings", "evidence", "attributionInputs", "logicInputs", "recommendationInputs", "modelOutputs"):
            for item in _list_of_dicts(contribution.get(collection_name)):
                values.update(_string_list(item.get("sourceIds")))
                values.update(_string_list(item.get("eventIds")))
                for trace_value in _normalize_trace_refs(item.get("traceRefs")).values():
                    values.update(trace_value)
    return [value for value in values if len(value) >= 4]


def _normalize_contribution_items(value: Any, item_type: str, *, module_id: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(_list_of_dicts(value), start=1):
        item_id = _clean_text(item.get("id") or item.get("itemId") or item.get("sourceId"))
        if not item_id:
            item_id = f"{module_id}_{item_type}_{index}"
        normalized.append(
            _drop_empty(
                {
                    "id": item_id,
                    "moduleId": _clean_text(item.get("moduleId") or module_id),
                    "type": _clean_text(item.get("type") or item_type),
                    "kind": _clean_text(item.get("kind") or item.get("category")),
                    "title": _clean_text(item.get("title") or item.get("name") or item.get("sourceName")),
                    "summary": _clean_text(item.get("summary") or item.get("description") or item.get("evidenceText") or item.get("reasoning")),
                    "confidence": item.get("confidence"),
                    "priority": _clean_text(item.get("priority")),
                    "rationale": _clean_text(item.get("rationale") or item.get("reasoning")),
                    "expectedBenefit": _clean_text(item.get("expectedBenefit") or item.get("expected_benefit")),
                    "riskNote": _clean_text(item.get("riskNote") or item.get("risk_note")),
                    "sourceIds": _string_list(item.get("sourceIds") or item.get("source_ids")),
                    "eventIds": _string_list(item.get("eventIds") or item.get("event_ids") or item.get("relatedEventIds")),
                    "url": _clean_text(item.get("url")),
                    "locator": _clean_text(item.get("locator")),
                    "sourceType": _clean_text(item.get("sourceType") or item.get("source_type")),
                    "sourceName": _clean_text(item.get("sourceName") or item.get("source_name")),
                    "traceRefs": _normalize_trace_refs(item.get("traceRefs") or item.get("trace_refs")),
                    "limitations": _normalize_limitations(item.get("limitations"), module_id=module_id),
                }
            )
        )
    return normalized


def _normalize_trace_refs(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    refs: dict[str, list[str]] = {}
    for key, raw in value.items():
        clean_key = str(key or "").strip()
        if clean_key:
            refs[clean_key] = _string_list(raw)
    return _drop_empty(refs)


def _normalize_limitations(value: Any, *, module_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            text = _clean_text(item.get("summary") or item.get("text") or item.get("description"))
            limitation_id = _clean_text(item.get("id"))
        else:
            text = _clean_text(item)
            limitation_id = ""
        if text:
            result.append(_limitation(module_id, text, limitation_id=limitation_id or f"{module_id}_limitation_{index}"))
    return result


def _limitation(module_id: str, text: str, *, limitation_id: str = "") -> dict[str, Any]:
    return _drop_empty(
        {
            "id": limitation_id or f"{module_id}_limitation_{uuid.uuid4().hex[:8]}",
            "moduleId": module_id,
            "type": "limitation",
            "title": "限制说明",
            "summary": _clean_text(text),
        }
    )


def _robotics_signal_domain_outputs(items: list[dict[str, Any]], *, output_type: str) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for item in items:
        signal_id = _clean_text(item.get("id"))
        if signal_id:
            outputs.append(
                _drop_empty(
                    {
                        "id": signal_id,
                        "type": output_type,
                        "title": _clean_text(item.get("title")),
                        "summary": _clean_text(item.get("reasoning")),
                        "sourceIds": _string_list(item.get("sourceIds")),
                        "eventIds": _string_list(item.get("relatedEventIds")),
                        "confidence": item.get("confidence"),
                    }
                )
            )
    return outputs


def _robotics_reasoning_trace(opportunities: list[dict[str, Any]], risks: list[dict[str, Any]], *, module_id: str) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    for item in [*opportunities, *risks]:
        signal_id = _clean_text(item.get("id"))
        reasoning = _clean_text(item.get("reasoning"))
        if signal_id and reasoning:
            trace.append(
                {
                    "id": f"{module_id}_logic_{signal_id}",
                    "title": _clean_text(item.get("title")),
                    "summary": reasoning,
                    "traceRefs": {"domainOutputIds": [signal_id], "sourceIds": _string_list(item.get("sourceIds"))},
                }
            )
    return trace


def _robotics_findings(items: list[dict[str, Any]], *, module_id: str, kind: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in items:
        signal_id = _clean_text(item.get("id"))
        if not signal_id:
            continue
        source_ids = _string_list(item.get("sourceIds"))
        findings.append(
            {
                "id": f"{module_id}_finding_{signal_id}",
                "moduleId": module_id,
                "type": "finding",
                "kind": kind,
                "title": _clean_text(item.get("title")) or ("机会信号" if kind == "opportunity" else "风险信号"),
                "summary": _clean_text(item.get("reasoning")),
                "confidence": item.get("confidence"),
                "sourceIds": source_ids,
                "eventIds": _string_list(item.get("relatedEventIds")),
                "traceRefs": {"domainOutputIds": [signal_id], "sourceIds": source_ids},
            }
        )
    return findings


def _robotics_attribution_inputs(findings: list[dict[str, Any]], *, module_id: str) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{module_id}_attribution_{index}",
            "moduleId": module_id,
            "type": "attribution",
            "title": item.get("title"),
            "summary": item.get("summary"),
            "traceRefs": {"findingIds": [item["id"]], **_dict_value(item.get("traceRefs"))},
        }
        for index, item in enumerate(findings, start=1)
    ]


def _robotics_logic_inputs(findings: list[dict[str, Any]], *, module_id: str) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{module_id}_logic_{index}",
            "moduleId": module_id,
            "type": "logic",
            "title": f"从模块信号到报告结论：{item.get('title', '')}",
            "summary": item.get("summary"),
            "traceRefs": {"findingIds": [item["id"]], **_dict_value(item.get("traceRefs"))},
        }
        for index, item in enumerate(findings, start=1)
    ]


def _robotics_recommendations(findings: list[dict[str, Any]], *, module_id: str) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for index, item in enumerate(findings, start=1):
        kind = _clean_text(item.get("kind"))
        if kind == "opportunity":
            title = f"优先验证并跟进机会信号：{item.get('title', '')}"
            risk_note = "需结合后续公告、订单兑现和资金投入节奏复核。"
        else:
            title = f"建立风险监测项：{item.get('title', '')}"
            risk_note = "需持续补采来源并区分短期扰动与长期趋势。"
        recommendations.append(
            {
                "id": f"{module_id}_recommendation_{index}",
                "moduleId": module_id,
                "type": "recommendation",
                "title": title,
                "summary": item.get("summary"),
                "expectedBenefit": "将模块识别的信号转化为可跟踪的决策动作。",
                "riskNote": risk_note,
                "priority": "medium",
                "confidence": item.get("confidence"),
                "traceRefs": {"findingIds": [item["id"]], **_dict_value(item.get("traceRefs"))},
            }
        )
    return recommendations


def _collect_traceable_ids(contribution: dict[str, Any], domain_analysis: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for collection_name in (
        "findings",
        "evidence",
        "attributionInputs",
        "logicInputs",
        "recommendationInputs",
        "modelOutputs",
        "visualAssets",
        "attachments",
        "limitations",
    ):
        for item in _list_of_dicts(contribution.get(collection_name)):
            for key in ("id", "assetId", "sourceId"):
                value = _clean_text(item.get(key))
                if value:
                    ids.add(value)
            ids.update(_string_list(item.get("sourceIds")))
            ids.update(_string_list(item.get("eventIds")))
    for collection_name in ("domainOutputs", "evidence", "reasoningTrace", "modelOutputs", "visualAssets", "limitations", "sourceReferences"):
        for item in _list_of_dicts(domain_analysis.get(collection_name)):
            for key in ("id", "assetId", "sourceId"):
                value = _clean_text(item.get(key))
                if value:
                    ids.add(value)
            ids.update(_string_list(item.get("sourceIds")))
            ids.update(_string_list(item.get("eventIds")))
    return ids


def _trace_ids(value: Any) -> set[str]:
    refs = _normalize_trace_refs(value)
    result: set[str] = set()
    for values in refs.values():
        result.update(values)
    return result


def _drop_substantive_items(contribution: dict[str, Any]) -> dict[str, Any]:
    degraded = dict(contribution)
    for key in ("findings", "attributionInputs", "logicInputs", "recommendationInputs"):
        degraded[key] = []
    return _drop_empty(degraded)


def _with_report_asset_urls(report_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        normalized = dict(item)
        asset_id = _clean_text(normalized.get("assetId") or normalized.get("id"))
        if asset_id and not _clean_text(normalized.get("downloadUrl")):
            normalized["downloadUrl"] = f"/api/workspace/reports/{report_id}/assets/{asset_id}/download"
        result.append(normalized)
    return result


def _all_items(contributions: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for contribution in contributions:
        result.extend(_list_of_dicts(contribution.get(key)))
    return result


def _module_summaries(contributions: list[dict[str, Any]], module_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for contribution, result in zip(contributions, module_results):
        summaries.append(
            _drop_empty(
                {
                    "moduleId": _clean_text(contribution.get("moduleId")),
                    "displayName": _clean_text(contribution.get("displayName")),
                    "status": _clean_text(contribution.get("status") or result.get("status")),
                    "summary": _clean_text(result.get("summary")),
                    "runId": _clean_text(result.get("runId")),
                }
            )
        )
    return summaries


def _clean_report_subject(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = re.sub(r"(?<!\d)\d{6}(?!\d)", "", text).strip(" ,，、；;。")
    text = re.sub(r"^(?:请|麻烦|帮我|帮忙|可以)?(?:生成|出具|写|做|分析|查看|评估|开始|继续)?", "", text).strip(" ,，、；;。")
    context_match = re.search(r"(?:时间范围|报告目标|分析目标|分析重点|关注重点|区域范围|时间|目标|重点|关注|聚焦|区域)\s*(?:是|为|:|：)?", text)
    time_match = re.search(r"(?:近\s*\d+\s*(?:天|日|周|个月|月|年)|过去\s*\d+\s*(?:天|日|周|个月|月|年)|本(?:周|月|季度|季|年)|上(?:周|月|季度|季|年))", text)
    cut_points = [match.start() for match in (context_match, time_match) if match is not None]
    if cut_points:
        text = text[: min(cut_points)]
    text = re.sub(r"(?:的)?(?:定制化)?(?:分析)?(?:报告|简报|研报|洞察)$", "", text).strip(" ,，、；;。")
    return text


def _clean_report_title(value: Any, *, enterprise: str) -> str:
    title = _clean_text(value).replace("简报", "定制化分析报告")
    if not title:
        return ""
    if re.search(r"(?:时间范围|报告目标|分析目标|分析重点|关注重点|区域范围|时间|目标|重点|关注|聚焦|区域)", title):
        return f"{enterprise}定制化分析报告"
    if enterprise and enterprise not in title:
        return f"{enterprise}定制化分析报告"
    return title


def _contribution_limitations(contributions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for contribution in contributions:
        for item in _list_of_dicts(contribution.get("limitations")):
            summary = _clean_text(item.get("summary"))
            if summary and summary not in seen:
                seen.add(summary)
                result.append(item)
        for collection_name in ("visualAssets", "modelOutputs", "attachments"):
            for asset in _list_of_dicts(contribution.get(collection_name)):
                for item in _list_of_dicts(asset.get("limitations")):
                    summary = _clean_text(item.get("summary"))
                    if summary and summary not in seen:
                        seen.add(summary)
                        result.append(item)
    return result


def _report_status(contributions: list[dict[str, Any]], *, stale_modules: list[str]) -> str:
    if stale_modules:
        return "degraded"
    statuses = {_clean_text(item.get("status")).lower() for item in contributions}
    if statuses and statuses.issubset({"failed", "need_input", "stale"}):
        return "degraded"
    if any(status in {"partial", "failed", "need_input", "stale"} for status in statuses):
        return "partial"
    return "completed"


def _report_title(shared_summary: dict[str, Any], module_results: list[dict[str, Any]]) -> str:
    enterprise = _clean_report_subject(shared_summary.get("enterpriseName")) or "目标企业"
    for result in module_results:
        handoff = _dict_value(result.get("documentHandoff"))
        title = _clean_text(handoff.get("title"))
        if title:
            clean_title = _clean_report_title(title, enterprise=enterprise)
            if clean_title:
                return clean_title
    return f"{enterprise}定制化分析报告"


def _executive_summary_text(findings: list[dict[str, Any]], limitations: list[dict[str, Any]], *, status: str) -> str:
    if findings:
        titles = "；".join(_clean_text(item.get("title")) for item in findings[:3] if _clean_text(item.get("title")))
        return f"本报告基于已完成的结构化分析材料生成，当前状态为 {status}。核心发现集中在：{titles}。所有结论均保留来源、证据或限制说明。"
    if limitations:
        return f"本报告当前状态为 {status}。现有材料未提供足够可支持的实质性发现，因此正文主要呈现状态、来源缺口与限制。"
    return f"本报告当前状态为 {status}，尚未获得足够可支撑材料。"


def _section(section_id: str, title: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": section_id, "title": title, "blocks": [block for block in blocks if block]}


def _paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "text": _clean_text(text)}


def _items_block(items: Any, *, empty_text: str = "") -> dict[str, Any]:
    return {"type": "items", "items": _list_of_dicts(items), "emptyText": empty_text}


def _evidence_block(items: Any) -> dict[str, Any]:
    return {"type": "evidence", "items": _list_of_dicts(items)}


def _visual_block(items: Any) -> dict[str, Any]:
    return {"type": "visuals", "items": _list_of_dicts(items)}


def _trace_label(item: dict[str, Any]) -> str:
    refs = _normalize_trace_refs(item.get("traceRefs"))
    parts = []
    for key, values in refs.items():
        if values:
            parts.append(f"{key}={','.join(values)}")
    return "；".join(parts)


def _inline_markdown_to_html(value: str) -> str:
    escaped = html.escape(value)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _image_markdown_to_html(line: str) -> str:
    match = re.match(r"!\[(.*?)\]\((.*?)\)", line)
    if not match:
        return f"<p>{html.escape(line)}</p>"
    alt, url = match.groups()
    return f"<img src=\"{html.escape(url, quote=True)}\" alt=\"{html.escape(alt, quote=True)}\">"


def _content_type_for_visual_type(asset_type: str) -> str:
    if asset_type == "image":
        return "image/png"
    return "application/json"


def _new_module_artifact_id() -> str:
    return f"mart_{uuid.uuid4().hex[:24]}"


def _module_artifact_title(result: dict[str, Any], *, module_id: str) -> str:
    handoff = _dict_value(result.get("documentHandoff"))
    return (
        _clean_text(handoff.get("title"))
        or _clean_text(result.get("title"))
        or _clean_text(result.get("displayName"))
        or f"{module_id}分析结果"
    )


def _module_markdown_body(result: dict[str, Any]) -> str:
    result_payload = _dict_value(result.get("result"))
    handoff = _dict_value(result.get("documentHandoff"))
    body = (
        _clean_text(result.get("markdownBody"))
        or _clean_text(result_payload.get("briefMarkdown"))
        or _clean_text(handoff.get("compactMarkdown"))
        or _clean_text(result.get("summary"))
    )
    if body:
        return body
    limitations = result.get("limitations") if isinstance(result.get("limitations"), list) else []
    if limitations:
        return "# 模块分析结果\n\n" + "\n".join(f"- {_clean_text(item)}" for item in limitations if _clean_text(item))
    return ""


def _shared_summary_from_module_rows(rows: list[AnalysisModuleArtifact]) -> dict[str, Any]:
    for row in rows:
        metadata = _dict_value(row.metadata_json)
        module_result = _dict_value(metadata.get("moduleResult"))
        target = _dict_value(module_result.get("targetCompany"))
        normalized_input = _dict_value(module_result.get("normalizedInput"))
        if target or normalized_input:
            enterprise = _clean_text(target.get("name") or _dict_value(normalized_input.get("enterprise")).get("name") or normalized_input.get("enterpriseName"))
            scope = _dict_value(normalized_input.get("analysisScope"))
            return _drop_empty(
                {
                    "enterpriseName": enterprise,
                    "stockCode": _clean_text(target.get("stockCode") or normalized_input.get("stockCode")),
                    "timeRange": _clean_text(scope.get("timeRange") or normalized_input.get("timeRange")),
                    "reportGoal": _clean_text(_dict_value(normalized_input.get("metadata")).get("reportGoal")),
                }
            )
    return {}


def _artifact_report_from_module_text(
    rows: list[AnalysisModuleArtifact],
    *,
    render_style: str,
) -> dict[str, Any]:
    report_id = _new_report_id()
    title = "综合分析报告"
    style_label = _report_style_label(render_style)
    generated_at = _format_datetime(datetime.utcnow())
    toc_items = [row.title for row in rows if row.title]
    lines = [
        f"# {title}",
        "",
        "## 封面",
        "",
        f"- 报告名称：{title}",
        f"- 生成时间：{generated_at}",
        f"- 渲染风格：{style_label}",
        "",
        "## 目录",
        "",
        "- 报告范围",
        "- 模块分析正文",
        *[f"- {item}" for item in toc_items],
        "- 来源与限制",
        "",
        "## 报告范围",
        "",
        "本报告基于本轮对话中已完成的分析模块原文生成，报告结构由系统固定，渲染风格仅影响最终 PDF 的视觉呈现。",
        "",
        "## 模块分析正文",
        "",
    ]
    for row in rows:
        lines.extend([f"### {row.title}", "", row.markdown_body or row.text_body or "", ""])
    lines.extend(["## 来源与限制", "", "- 报告生成基于已完成模块输出，不会在生成阶段重新运行分析模块。"])
    markdown_body = "\n".join(lines).strip() + "\n"
    artifact = _drop_empty(
        {
            "schemaVersion": REPORT_ARTIFACT_SCHEMA_VERSION,
            "reportId": report_id,
            "title": title,
            "status": "completed",
            "generatedAt": generated_at,
            "renderStyle": render_style,
            "scope": {
                "analysisSessionId": rows[0].analysis_session_id,
                "analysisSessionRevision": int(rows[0].analysis_session_revision or 0),
                "enabledModules": [row.module_id for row in rows],
                "moduleRunIds": {row.module_id: row.module_run_id for row in rows if row.module_run_id},
            },
            "sectionPlan": [
                {"id": "cover", "title": "封面"},
                {"id": "toc", "title": "目录"},
                {"id": "module_bodies", "title": "模块分析正文"},
                {"id": "limitations", "title": "来源与限制"},
            ],
            "sourceModuleArtifactIds": [row.artifact_id for row in rows],
            "qualityFlags": [
                _quality_flag("artifact_text_report", "info", "报告基于模块原文生成，未要求模块提供额外 reportBrief。")
            ],
            "markdownBody": markdown_body,
        }
    )
    artifact["htmlBody"] = render_report_html(artifact, markdown_body=markdown_body)
    artifact["preview"] = bounded_report_preview(markdown_body)
    artifact["downloadMetadata"] = report_download_metadata(report_id)
    return artifact


def _report_style_label(render_style: str) -> str:
    style_id = normalize_report_render_style(render_style)
    for style in REPORT_RENDER_STYLES:
        if style["id"] == style_id:
            return style["label"]
    return style_id


def _new_report_id() -> str:
    return f"arpt_{uuid.uuid4().hex[:24]}"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.replace(microsecond=0).isoformat()


def _clean_filename(value: Any) -> str:
    text = _clean_text(value) or "report"
    text = re.sub(r"[\\/:*?\"<>|\r\n]+", "-", text)
    text = text.strip(" .")
    return text[:180] or "report"


def _ascii_filename(value: Any) -> str:
    clean = _clean_filename(value)
    ascii_text = "".join(char if char.isascii() and (char.isalnum() or char in {"-", "_", "."}) else "-" for char in clean)
    ascii_text = re.sub(r"-+", "-", ascii_text).strip("-.")
    return ascii_text[:120] or "report"


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        clean = _clean_text(item)
        if clean and clean not in result:
            result.append(clean)
    return result


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _drop_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _drop_empty(item) for key, item in value.items() if item not in (None, "", [], {})}
    if isinstance(value, list):
        return [_drop_empty(item) for item in value if item not in (None, "", [], {})]
    return value
