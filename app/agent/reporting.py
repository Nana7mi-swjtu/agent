from __future__ import annotations

import html
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AnalysisReport

REPORT_ARTIFACT_SCHEMA_VERSION = "analysis_report_artifact.v1"
REPORT_CONTRIBUTION_SCHEMA_VERSION = "analysis_report_contribution.v1"
DOMAIN_ANALYSIS_SCHEMA_VERSION = "analysis_domain_analysis.v1"
VISUAL_ASSET_SCHEMA_VERSION = "analysis_report_visual_asset.v1"
REPORT_PREVIEW_LIMIT = 1200
SUPPORTED_REPORT_DOWNLOAD_FORMATS = {"markdown", "html"}
VISUAL_ASSET_TYPES = {"image", "chart", "table", "graph", "timeline", "heatmap"}


class ReportContributionValidationError(ValueError):
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
            limitations.append(_limitation("report", f"已选择模块 {module_id}，但未获得模块输出。"))
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
            limitations.append(_limitation(module_id, f"模块报告贡献未通过追溯校验，已降级处理：{exc}"))
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
        limitations.append(_limitation("report", "部分模块输出已过期，报告只能作为降级快照使用：" + "、".join(stale_modules)))
    module_run_ids = _dict_value(handoff_bundle.get("moduleRunIds"))
    sections = _build_report_sections(
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
    artifact = _drop_empty(
        {
            "schemaVersion": REPORT_ARTIFACT_SCHEMA_VERSION,
            "reportId": report_id,
            "title": title,
            "status": status,
            "generatedAt": generated_at,
            "scope": {
                "reportGoal": _clean_text(shared_summary.get("reportGoal")),
                "targetCompany": _clean_text(shared_summary.get("enterpriseName")),
                "stockCode": _clean_text(shared_summary.get("stockCode")),
                "timeRange": _clean_text(shared_summary.get("timeRange")),
                "enabledModules": enabled_modules,
                "analysisSessionId": _clean_text(session_payload.get("sessionId")),
                "analysisSessionRevision": _safe_int(session_payload.get("revision"), default=0),
                "moduleRunIds": module_run_ids,
            },
            "moduleSummaries": _module_summaries(contributions, included_results),
            "sections": sections,
            "findings": _all_items(contributions, "findings"),
            "attributionChains": _all_items(contributions, "attributionInputs"),
            "logicBreakdown": _all_items(contributions, "logicInputs"),
            "recommendations": _all_items(contributions, "recommendationInputs"),
            "evidenceTraceability": _all_items(contributions, "evidence"),
            "modelOutputs": _all_items(contributions, "modelOutputs"),
            "visualAssets": _with_report_asset_urls(report_id, _all_items(contributions, "visualAssets")),
            "attachments": _with_report_asset_urls(report_id, _all_items(contributions, "attachments")),
            "limitations": limitations,
        }
    )
    markdown_body = render_report_markdown(artifact)
    html_body = render_report_html(artifact, markdown_body=markdown_body)
    artifact["markdownBody"] = markdown_body
    artifact["htmlBody"] = html_body
    artifact["preview"] = bounded_report_preview(markdown_body)
    artifact["downloadMetadata"] = report_download_metadata(report_id)
    return artifact


def render_report_markdown(artifact: dict[str, Any]) -> str:
    title = _clean_text(artifact.get("title")) or "分析报告"
    lines = [f"# {title}", ""]
    scope = _dict_value(artifact.get("scope"))
    meta_parts = []
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
    return {
        "availableFormats": ["markdown", "html"],
        "downloadUrls": {
            "markdown": f"/api/workspace/reports/{report_id}/download?format=markdown",
            "html": f"/api/workspace/reports/{report_id}/download?format=html",
        },
    }


def report_preview_metadata(artifact: dict[str, Any]) -> dict[str, Any]:
    report_id = _clean_text(artifact.get("reportId"))
    metadata = report_download_metadata(report_id)
    return _drop_empty(
        {
            "reportId": report_id,
            "title": _clean_text(artifact.get("title")),
            "status": _clean_text(artifact.get("status")),
            "preview": _clean_text(artifact.get("preview") or bounded_report_preview(_clean_text(artifact.get("markdownBody")))),
            "availableFormats": metadata["availableFormats"],
            "downloadUrls": metadata["downloadUrls"],
            "limitations": artifact.get("limitations") if isinstance(artifact.get("limitations"), list) else [],
        }
    )


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
    payload = _drop_empty(
        {
            "reportId": row.report_id,
            "title": row.title,
            "status": row.status,
            "preview": _clean_text(artifact.get("preview") or bounded_report_preview(row.markdown_body or "")),
            "availableFormats": ["markdown", "html"],
            "downloadUrls": _dict_value(row.download_metadata_json).get("downloadUrls", {}),
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
    extension = "md" if report_format == "markdown" else "html"
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
            title = _clean_text(item.get("title") or item.get("name") or item.get("id"))
            summary = _clean_text(item.get("summary") or item.get("description") or item.get("text") or item.get("reasoning"))
            prefix = f"- **{title}**" if title else "-"
            lines.append(f"{prefix}：{summary}" if summary else prefix)
            trace = _trace_label(item)
            if trace:
                lines.append(f"  - 追溯：{trace}")
        lines.append("")
    elif block_type == "evidence":
        evidence = block.get("items", [])
        if not isinstance(evidence, list) or not evidence:
            lines.extend(["暂无可引用来源。", ""])
            return
        for item in evidence:
            if not isinstance(item, dict):
                continue
            title = _clean_text(item.get("title") or item.get("sourceName") or item.get("sourceId") or item.get("id"))
            source = _clean_text(item.get("url") or item.get("locator") or item.get("sourceType"))
            text = _clean_text(item.get("summary") or item.get("evidenceText") or item.get("description"))
            lines.append(f"- **{title or '来源'}**：{text or source}")
            if source and source != text:
                lines.append(f"  - 位置：{source}")
        lines.append("")
    elif block_type == "visuals":
        for asset in block.get("items", []) if isinstance(block.get("items"), list) else []:
            if not isinstance(asset, dict):
                continue
            title = _clean_text(asset.get("title"))
            url = _clean_text(asset.get("downloadUrl"))
            alt = _clean_text(asset.get("altText") or title)
            caption = _clean_text(asset.get("caption") or asset.get("description"))
            if url and str(asset.get("type", "")).lower() == "image":
                lines.append(f"![{alt}]({url})")
            else:
                lines.append(f"- **{title or '图表'}**：{caption or alt}")
                render_payload = asset.get("renderPayload")
                if isinstance(render_payload, dict) and render_payload:
                    lines.append(f"  - 降级呈现：{_clean_text(render_payload.get('text') or render_payload.get('summary') or render_payload)}")
            if caption:
                lines.append(f"  - 说明：{caption}")
        lines.append("")


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
    enterprise = _clean_text(shared_summary.get("enterpriseName")) or "目标企业"
    for result in module_results:
        handoff = _dict_value(result.get("documentHandoff"))
        title = _clean_text(handoff.get("title"))
        if title:
            return title.replace("简报", "定制化分析报告")
    return f"{enterprise}定制化分析报告"


def _executive_summary_text(findings: list[dict[str, Any]], limitations: list[dict[str, Any]], *, status: str) -> str:
    if findings:
        titles = "；".join(_clean_text(item.get("title")) for item in findings[:3] if _clean_text(item.get("title")))
        return f"本报告基于已选模块的可追溯输出生成，当前状态为 {status}。核心发现包括：{titles}。所有结论均保留模块来源、证据或限制说明。"
    if limitations:
        return f"本报告基于已选模块输出生成，当前状态为 {status}。模块未提供足够可支持的实质性发现，因此报告主要呈现状态、来源缺口与限制。"
    return f"本报告基于已选模块输出生成，当前状态为 {status}。"


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
