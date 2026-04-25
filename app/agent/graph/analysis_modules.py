from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from flask import has_app_context

from ...analysis_artifacts import normalize_chart_candidate, normalize_fact_table, normalize_rendered_asset
from ...robotics_risk import run_robotics_risk_subagent
from ..reporting import (
    build_robotics_domain_analysis,
    build_robotics_report_contribution,
    normalize_report_contribution,
    validate_report_contribution_traceability,
)
from .analysis_slots import (
    AnalysisSlotDefinition,
    SHARED_ENTERPRISE_NAME,
    SHARED_REPORT_GOAL,
    SHARED_STOCK_CODE,
    SHARED_TIME_RANGE,
    SCOPE_MODULE,
    normalize_slot_value,
    shared_slot_catalog,
)

ANALYSIS_HANDOFF_BUNDLE_SCHEMA_VERSION = "analysis_handoff_bundle.v2"


@dataclass(frozen=True)
class AnalysisModuleContract:
    module_id: str
    display_name: str
    required_slots: tuple[str, ...]
    optional_slots: tuple[str, ...] = field(default_factory=tuple)
    slot_definitions: tuple[AnalysisSlotDefinition, ...] = field(default_factory=tuple)
    legacy_input_slot_map: dict[str, str] = field(default_factory=dict)
    legacy_passthrough_fields: tuple[str, ...] = field(default_factory=tuple)
    slot_mapping: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None
    run: Callable[[dict[str, Any]], Any] | None = None


def normalize_enabled_analysis_modules(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        module_id = _clean_module_id(item)
        if module_id and module_id not in normalized:
            normalized.append(module_id)
    return normalized


def normalize_analysis_shared_inputs(
    value: Any,
    *,
    fallback_enterprise: str = "",
    fallback_report_goal: str = "",
) -> dict[str, Any]:
    raw = dict(value or {}) if isinstance(value, dict) else {}
    enterprise_name = _clean_text(raw.get("enterpriseName") or raw.get("enterprise_name") or fallback_enterprise)
    stock_code = _clean_text(raw.get("stockCode") or raw.get("stock_code"))
    time_range = _clean_text(raw.get("timeRange") or raw.get("time_range"))
    report_goal = _clean_text(raw.get("reportGoal") or raw.get("report_goal") or fallback_report_goal)
    return _drop_empty(
        {
            "enterpriseName": enterprise_name,
            "stockCode": stock_code,
            "timeRange": time_range,
            "reportGoal": report_goal,
        }
    )


def normalize_analysis_module_inputs(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for raw_module_id, raw_payload in value.items():
        module_id = _clean_module_id(raw_module_id)
        if not module_id or not isinstance(raw_payload, dict):
            continue
        normalized[module_id] = _normalize_mapping(raw_payload)
    return normalized


def get_analysis_module_registry() -> dict[str, AnalysisModuleContract]:
    return {
        "robotics_risk": AnalysisModuleContract(
            module_id="robotics_risk",
            display_name="机器人风险机会洞察",
            required_slots=(
                SHARED_ENTERPRISE_NAME,
                SHARED_TIME_RANGE,
                SHARED_REPORT_GOAL,
            ),
            optional_slots=(SHARED_STOCK_CODE,),
            legacy_passthrough_fields=("sourceControls",),
            slot_mapping=_map_robotics_risk_runtime_input,
            run=_run_robotics_risk_module,
        )
    }


def build_slot_catalog(contracts: list[AnalysisModuleContract]) -> dict[str, AnalysisSlotDefinition]:
    catalog = shared_slot_catalog()
    for contract in contracts:
        for definition in contract.slot_definitions:
            catalog[definition.slot_id] = definition
    return catalog


def map_legacy_inputs_to_slot_updates(
    *,
    contracts: list[AnalysisModuleContract],
    slot_catalog: dict[str, AnalysisSlotDefinition],
    shared_inputs: dict[str, Any],
    module_inputs: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    slot_updates: dict[str, Any] = {}
    compatibility = {
        "legacySharedInputs": dict(shared_inputs) if isinstance(shared_inputs, dict) else {},
        "legacyModuleInputs": {},
    }
    shared_mapping = {
        "enterpriseName": SHARED_ENTERPRISE_NAME,
        "stockCode": SHARED_STOCK_CODE,
        "timeRange": SHARED_TIME_RANGE,
        "reportGoal": SHARED_REPORT_GOAL,
    }
    for field_name, slot_id in shared_mapping.items():
        raw_value = shared_inputs.get(field_name) if isinstance(shared_inputs, dict) else None
        if raw_value in (None, "", [], {}):
            continue
        definition = slot_catalog.get(slot_id)
        if definition is None:
            continue
        normalized = normalize_slot_value(definition, raw_value)
        if normalized not in (None, "", [], {}):
            slot_updates[slot_id] = normalized

    for contract in contracts:
        current_inputs = module_inputs.get(contract.module_id, {}) if isinstance(module_inputs, dict) else {}
        if not isinstance(current_inputs, dict):
            current_inputs = {}
        compatibility["legacyModuleInputs"][contract.module_id] = dict(current_inputs)
        for field_name, slot_id in contract.legacy_input_slot_map.items():
            raw_value = current_inputs.get(field_name)
            if raw_value in (None, "", [], {}):
                continue
            definition = slot_catalog.get(slot_id)
            if definition is None:
                continue
            normalized = normalize_slot_value(definition, raw_value)
            if normalized not in (None, "", [], {}):
                slot_updates[slot_id] = normalized
    return slot_updates, compatibility


def build_runtime_input(
    contract: AnalysisModuleContract,
    *,
    slot_values: dict[str, Any],
    compatibility: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    if contract.slot_mapping is None:
        return {}
    return contract.slot_mapping(slot_values, compatibility, context)


def normalize_analysis_module_output(
    contract: AnalysisModuleContract,
    raw_output: Any,
    *,
    input_revision: int | None = None,
) -> dict[str, Any]:
    payload = raw_output.to_dict() if hasattr(raw_output, "to_dict") else dict(raw_output or {})
    if not isinstance(payload, dict):
        payload = {}
    result_payload = payload.get("result", {})
    if not isinstance(result_payload, dict):
        result_payload = {}
    handoff_payload = payload.get("documentHandoff", {})
    if not isinstance(handoff_payload, dict):
        handoff_payload = {}
    reader_packet = _module_reader_packet_payload(handoff_payload=handoff_payload, result_payload=result_payload)
    evidence_references = _module_evidence_reference_payloads(
        handoff_payload=handoff_payload,
        reader_packet=reader_packet,
    )
    fact_tables = _module_fact_table_payloads(handoff_payload=handoff_payload, result_payload=result_payload)
    chart_candidates = _module_chart_candidate_payloads(handoff_payload=handoff_payload, result_payload=result_payload)
    rendered_assets = _module_rendered_asset_payloads(handoff_payload=handoff_payload, result_payload=result_payload)
    visual_summaries = _module_visual_summary_payloads(handoff_payload=handoff_payload, reader_packet=reader_packet)
    limitations = _normalize_string_list(payload.get("limitations"))
    run_id = _clean_text(payload.get("runId") or payload.get("run_id"))
    source_references = (
        payload.get("sourceReferences")
        if isinstance(payload.get("sourceReferences"), list)
        else payload.get("source_references", [])
    )
    if not isinstance(source_references, list):
        source_references = []
    status = _clean_text(payload.get("status")) or "failed"
    summary = _build_module_summary(
        result_payload=result_payload,
        handoff_payload=handoff_payload,
        limitations=limitations,
        status=status,
        source_reference_count=len(source_references),
    )
    normalized = _drop_empty(
        {
            "moduleId": contract.module_id,
            "displayName": contract.display_name,
            "status": status,
            "summary": summary,
            "limitations": limitations,
            "runId": run_id,
            "documentHandoff": handoff_payload,
            "result": result_payload,
            "readerPacket": reader_packet,
            "evidenceReferences": evidence_references,
            "factTables": fact_tables,
            "chartCandidates": chart_candidates,
            "renderedAssets": rendered_assets,
            "visualSummaries": visual_summaries,
            "targetCompany": payload.get("targetCompany")
            if isinstance(payload.get("targetCompany"), dict)
            else payload.get("target_company", {}),
            "normalizedInput": payload.get("normalizedInput")
            if isinstance(payload.get("normalizedInput"), dict)
            else payload.get("normalized_input", {}),
            "sourceReferences": source_references,
            "errorMessage": _clean_text(payload.get("errorMessage") or payload.get("error_message")),
        }
    )
    domain_analysis = payload.get("domainAnalysis") if isinstance(payload.get("domainAnalysis"), dict) else {}
    report_contribution = (
        payload.get("reportContribution") if isinstance(payload.get("reportContribution"), dict) else {}
    )
    if contract.module_id == "robotics_risk" and not domain_analysis:
        domain_analysis = build_robotics_domain_analysis(normalized)
    if contract.module_id == "robotics_risk" and not report_contribution:
        report_contribution = build_robotics_report_contribution(normalized, domain_analysis)
    elif report_contribution:
        report_contribution = normalize_report_contribution(
            report_contribution,
            module_id=contract.module_id,
            display_name=contract.display_name,
            status=status,
        )
        validate_report_contribution_traceability(report_contribution, domain_analysis)
    if domain_analysis:
        normalized["domainAnalysis"] = domain_analysis
    if report_contribution:
        normalized["reportContribution"] = report_contribution
    if input_revision is not None:
        normalized["inputSnapshotRevision"] = int(input_revision)
    return normalized


def build_analysis_handoff_bundle(
    *,
    analysis_session: dict[str, Any],
    shared_summary: dict[str, Any],
    module_results: dict[str, dict[str, Any]],
    unsupported_modules: list[str] | None = None,
) -> dict[str, Any]:
    unsupported = [module_id for module_id in list(unsupported_modules or []) if module_id]
    enabled_modules = _string_list(analysis_session.get("enabledModules"))
    stale_modules = [
        module_id
        for module_id, module_state in _dict_items(analysis_session.get("moduleStates")).items()
        if isinstance(module_state, dict) and str(module_state.get("status", "")).strip() == "stale"
    ]
    module_result_list = [
        dict(module_results[module_id])
        for module_id in enabled_modules
        if isinstance(module_results.get(module_id), dict)
    ]
    module_run_ids = {
        module_id: str(result.get("runId", "")).strip()
        for module_id, result in module_results.items()
        if isinstance(result, dict) and str(result.get("runId", "")).strip()
    }
    document_handoffs = {
        module_id: result.get("documentHandoff", {})
        for module_id, result in module_results.items()
        if isinstance(result, dict) and isinstance(result.get("documentHandoff"), dict) and result.get("documentHandoff")
    }
    module_reader_packets = {
        module_id: _dict_items(result.get("readerPacket"))
        for module_id, result in module_results.items()
        if isinstance(result, dict) and _dict_items(result.get("readerPacket"))
    }
    module_tabular_artifacts = {
        module_id: _drop_empty(
            {
                "evidenceReferences": _list_of_dicts(result.get("evidenceReferences")),
                "factTables": _list_of_dicts(result.get("factTables")),
                "chartCandidates": _list_of_dicts(result.get("chartCandidates")),
                "renderedAssets": _list_of_dicts(result.get("renderedAssets")),
                "visualSummaries": _list_of_dicts(result.get("visualSummaries")),
            }
        )
        for module_id, result in module_results.items()
        if isinstance(result, dict)
        and any(
            _list_of_dicts(result.get(key))
            for key in ("evidenceReferences", "factTables", "chartCandidates", "renderedAssets", "visualSummaries")
        )
    }
    module_summaries = {
        module_id: str(result.get("summary", "")).strip()
        for module_id, result in module_results.items()
        if isinstance(result, dict) and str(result.get("summary", "")).strip()
    }
    limitations = _bundle_limitations(module_results, unsupported)
    return _drop_empty(
        {
            "schemaVersion": ANALYSIS_HANDOFF_BUNDLE_SCHEMA_VERSION,
            "analysisSession": {
                "sessionId": _clean_text(analysis_session.get("sessionId")),
                "status": _clean_text(analysis_session.get("status")),
                "revision": int(analysis_session.get("revision", 0) or 0),
            },
            "enabledModules": enabled_modules,
            "sharedInputSummary": _drop_empty(
                {
                    "enterpriseName": _clean_text(shared_summary.get("enterpriseName")),
                    "stockCode": _clean_text(shared_summary.get("stockCode")),
                    "timeRange": _clean_text(shared_summary.get("timeRange")),
                    "reportGoal": _clean_text(shared_summary.get("reportGoal")),
                    "analysisFocusTags": _string_list(shared_summary.get("analysisFocusTags")),
                    "regionScope": _string_list(shared_summary.get("regionScope")),
                }
            ),
            "moduleResults": module_result_list,
            "moduleRunIds": module_run_ids,
            "moduleSummaries": module_summaries,
            "documentHandoffs": document_handoffs,
            "moduleReaderPackets": module_reader_packets,
            "moduleTabularArtifacts": module_tabular_artifacts,
            "unsupportedModules": unsupported,
            "staleModules": stale_modules,
            "limitations": limitations,
        }
    )


def _run_robotics_risk_module(payload: dict[str, Any]) -> Any:
    reader_writer = payload.get("readerWriter")
    if not has_app_context():
        return run_robotics_risk_subagent(payload, reader_writer=reader_writer)

    from ...db import session_scope
    from ...robotics_risk.cache import RoboticsEvidenceCache

    with session_scope() as db:
        evidence_cache = RoboticsEvidenceCache(db)
        return run_robotics_risk_subagent(
            payload,
            db=db,
            evidence_cache=evidence_cache,
            reader_writer=reader_writer,
        )


def _map_robotics_risk_runtime_input(
    slot_values: dict[str, Any],
    compatibility: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    module_inputs = compatibility.get("legacyModuleInputs", {}) if isinstance(compatibility, dict) else {}
    robotics_inputs = module_inputs.get("robotics_risk", {}) if isinstance(module_inputs, dict) else {}
    source_controls = robotics_inputs.get("sourceControls") or robotics_inputs.get("source_controls")
    return _drop_empty(
        {
            "enterpriseName": _clean_text(slot_values.get(SHARED_ENTERPRISE_NAME)),
            "stockCode": _clean_text(slot_values.get(SHARED_STOCK_CODE)),
            "timeRange": _clean_text(slot_values.get(SHARED_TIME_RANGE)) or "近30天",
            "sourceControls": source_controls if isinstance(source_controls, dict) else {},
            "conversationContext": _clean_text(context.get("conversationContext")),
            "readerWriter": context.get("readerWriter"),
            "metadata": _drop_empty(
                {
                    "reportGoal": _clean_text(slot_values.get(SHARED_REPORT_GOAL)),
                    "orchestration": {
                        "moduleId": "robotics_risk",
                        "sharedInputs": _drop_empty(
                            {
                                "enterpriseName": _clean_text(slot_values.get(SHARED_ENTERPRISE_NAME)),
                                "stockCode": _clean_text(slot_values.get(SHARED_STOCK_CODE)),
                                "timeRange": _clean_text(slot_values.get(SHARED_TIME_RANGE)),
                                "reportGoal": _clean_text(slot_values.get(SHARED_REPORT_GOAL)),
                            }
                        ),
                    },
                }
            ),
        }
    )


def _build_module_summary(
    *,
    result_payload: dict[str, Any],
    handoff_payload: dict[str, Any],
    limitations: list[str],
    status: str = "",
    source_reference_count: int = 0,
) -> str:
    if status in {"partial", "failed"} and source_reference_count <= 0:
        no_evidence = _first_no_evidence_limitation(limitations)
        if no_evidence:
            return _truncate(no_evidence, limit=300)
    summary_payload = result_payload.get("summary", {})
    if isinstance(summary_payload, dict):
        summary_lines = [
            _clean_text(summary_payload.get("opportunity")),
            _clean_text(summary_payload.get("risk")),
        ]
        merged = " ".join(line for line in summary_lines if line)
        if merged:
            return _truncate(merged, limit=300)
    executive_summary = handoff_payload.get("executiveSummary", {})
    if isinstance(executive_summary, dict):
        summary_lines = [
            _clean_text(executive_summary.get("headline")),
            _clean_text(executive_summary.get("opportunity")),
            _clean_text(executive_summary.get("risk")),
        ]
        merged = " ".join(line for line in summary_lines if line)
        if merged:
            return _truncate(merged, limit=300)
    if limitations:
        return _truncate(limitations[0], limit=300)
    return ""


def _first_no_evidence_limitation(limitations: list[str]) -> str:
    markers = ("未检索到", "未返回", "暂无可引用证据", "来源不可用", "不可用", "失败", "受限")
    for item in limitations:
        clean = _clean_text(item)
        if clean and any(marker in clean for marker in markers):
            return clean
    return ""


def _bundle_limitations(module_results: dict[str, dict[str, Any]], unsupported_modules: list[str]) -> list[str]:
    limitations: list[str] = []
    for module_id in unsupported_modules:
        limitations.append(f"尚未注册的分析模块：{module_id}")
    for result in module_results.values():
        if not isinstance(result, dict):
            continue
        for item in _normalize_string_list(result.get("limitations")):
            if item not in limitations:
                limitations.append(item)
    return limitations


def _clean_module_id(value: Any) -> str:
    text = _clean_text(value).lower().replace("-", "_").replace(" ", "_")
    return "".join(char for char in text if char.isalnum() or char == "_")


def _normalize_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        clean_key = str(key).strip()
        if not clean_key:
            continue
        normalized[clean_key] = _normalize_value(value)
    return _drop_empty(normalized)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _normalize_mapping(value)
    if isinstance(value, list):
        normalized_items = [_normalize_value(item) for item in value]
        return [item for item in normalized_items if item not in (None, "", [], {})]
    if isinstance(value, str):
        return value.strip()
    return value


def _normalize_string_list(value: Any) -> list[str]:
    return _string_list(value)


def _module_reader_packet_payload(
    *,
    handoff_payload: dict[str, Any],
    result_payload: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(handoff_payload.get("readerPacket"), dict) and handoff_payload.get("readerPacket"):
        return _dict_items(handoff_payload.get("readerPacket"))
    return _dict_items(result_payload.get("readerPacket"))


def _module_evidence_reference_payloads(
    *,
    handoff_payload: dict[str, Any],
    reader_packet: dict[str, Any],
) -> list[dict[str, Any]]:
    references = _list_of_dicts(handoff_payload.get("evidenceReferences"))
    if references:
        return references
    references = _list_of_dicts(reader_packet.get("evidenceReferences"))
    if references:
        return references
    return _list_of_dicts(handoff_payload.get("evidenceTable"))


def _module_fact_table_payloads(
    *,
    handoff_payload: dict[str, Any],
    result_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    tables = _list_of_dicts(handoff_payload.get("factTables"))
    if tables:
        return [normalize_fact_table(item) for item in tables]
    return [normalize_fact_table(item) for item in _list_of_dicts(result_payload.get("factTables"))]


def _module_chart_candidate_payloads(
    *,
    handoff_payload: dict[str, Any],
    result_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = _list_of_dicts(handoff_payload.get("chartCandidates"))
    if candidates:
        return [normalize_chart_candidate(item) for item in candidates]
    return [normalize_chart_candidate(item) for item in _list_of_dicts(result_payload.get("chartCandidates"))]


def _module_rendered_asset_payloads(
    *,
    handoff_payload: dict[str, Any],
    result_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    assets = _list_of_dicts(handoff_payload.get("renderedAssets"))
    if assets:
        return [normalize_rendered_asset(item) for item in assets]
    return [normalize_rendered_asset(item) for item in _list_of_dicts(result_payload.get("renderedAssets"))]


def _module_visual_summary_payloads(
    *,
    handoff_payload: dict[str, Any],
    reader_packet: dict[str, Any],
) -> list[dict[str, Any]]:
    visuals = _list_of_dicts(handoff_payload.get("visualSummaries"))
    if visuals:
        return visuals
    return _list_of_dicts(reader_packet.get("visualSummaries"))


def _truncate(value: str, *, limit: int) -> str:
    clean = " ".join(str(value or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _dict_items(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        clean = str(item or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _drop_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _drop_empty(item)
            for key, item in value.items()
            if item not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_drop_empty(item) for item in value if item not in (None, "", [], {})]
    return value
