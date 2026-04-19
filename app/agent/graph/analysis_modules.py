from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ...robotics_risk import run_robotics_risk_subagent

ANALYSIS_HANDOFF_BUNDLE_SCHEMA_VERSION = "analysis_handoff_bundle.v1"


@dataclass(frozen=True)
class AnalysisFieldDefinition:
    field: str
    label: str
    required: bool = True


@dataclass(frozen=True)
class AnalysisModuleContract:
    module_id: str
    display_name: str
    shared_fields: tuple[AnalysisFieldDefinition, ...]
    module_fields: tuple[AnalysisFieldDefinition, ...]
    build_input: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]]
    run: Callable[[dict[str, Any]], Any]


_SHARED_FIELDS: dict[str, AnalysisFieldDefinition] = {
    "enterpriseName": AnalysisFieldDefinition("enterpriseName", "企业名称（如有股票代码可一并提供）"),
    "stockCode": AnalysisFieldDefinition("stockCode", "股票代码", required=False),
    "timeRange": AnalysisFieldDefinition("timeRange", "时间范围"),
    "reportGoal": AnalysisFieldDefinition("reportGoal", "报告目标"),
}


def shared_field_definition(field_name: str) -> AnalysisFieldDefinition:
    return _SHARED_FIELDS[field_name]


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
    enterprise_name = _clean_text(
        raw.get("enterpriseName") or raw.get("enterprise_name") or fallback_enterprise
    )
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
    shared_fields = (
        shared_field_definition("enterpriseName"),
        shared_field_definition("stockCode"),
        shared_field_definition("timeRange"),
        shared_field_definition("reportGoal"),
    )
    return {
        "robotics_risk": AnalysisModuleContract(
            module_id="robotics_risk",
            display_name="机器人风险机会洞察",
            shared_fields=shared_fields,
            module_fields=(
                AnalysisFieldDefinition("focus", "关注重点"),
                AnalysisFieldDefinition("dimensions", "分析维度", required=False),
                AnalysisFieldDefinition("sourceControls", "来源开关", required=False),
            ),
            build_input=_build_robotics_risk_input,
            run=_run_robotics_risk_module,
        )
    }


def normalize_analysis_module_output(contract: AnalysisModuleContract, raw_output: Any) -> dict[str, Any]:
    payload = raw_output.to_dict() if hasattr(raw_output, "to_dict") else dict(raw_output or {})
    if not isinstance(payload, dict):
        payload = {}
    result_payload = payload.get("result", {})
    if not isinstance(result_payload, dict):
        result_payload = {}
    handoff_payload = payload.get("documentHandoff", {})
    if not isinstance(handoff_payload, dict):
        handoff_payload = {}
    limitations = _normalize_string_list(payload.get("limitations"))
    run_id = _clean_text(payload.get("runId") or payload.get("run_id"))
    summary = _build_module_summary(result_payload=result_payload, handoff_payload=handoff_payload, limitations=limitations)
    return _drop_empty(
        {
            "moduleId": contract.module_id,
            "displayName": contract.display_name,
            "status": _clean_text(payload.get("status")) or "failed",
            "summary": summary,
            "limitations": limitations,
            "runId": run_id,
            "documentHandoff": handoff_payload,
            "result": result_payload,
            "targetCompany": payload.get("targetCompany") if isinstance(payload.get("targetCompany"), dict) else payload.get("target_company", {}),
            "normalizedInput": payload.get("normalizedInput")
            if isinstance(payload.get("normalizedInput"), dict)
            else payload.get("normalized_input", {}),
            "sourceReferences": payload.get("sourceReferences")
            if isinstance(payload.get("sourceReferences"), list)
            else payload.get("source_references", []),
            "errorMessage": _clean_text(payload.get("errorMessage") or payload.get("error_message")),
        }
    )


def build_analysis_handoff_bundle(
    *,
    enabled_modules: list[str],
    shared_inputs: dict[str, Any],
    module_results: dict[str, dict[str, Any]],
    unsupported_modules: list[str] | None = None,
) -> dict[str, Any]:
    unsupported = [module_id for module_id in list(unsupported_modules or []) if module_id]
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
    module_summaries = {
        module_id: str(result.get("summary", "")).strip()
        for module_id, result in module_results.items()
        if isinstance(result, dict) and str(result.get("summary", "")).strip()
    }
    limitations = _bundle_limitations(module_results, unsupported)
    return _drop_empty(
        {
            "schemaVersion": ANALYSIS_HANDOFF_BUNDLE_SCHEMA_VERSION,
            "enabledModules": list(enabled_modules),
            "sharedInputSummary": _drop_empty(
                {
                    "enterpriseName": _clean_text(shared_inputs.get("enterpriseName")),
                    "stockCode": _clean_text(shared_inputs.get("stockCode")),
                    "timeRange": _clean_text(shared_inputs.get("timeRange")),
                    "reportGoal": _clean_text(shared_inputs.get("reportGoal")),
                }
            ),
            "moduleResults": module_result_list,
            "moduleRunIds": module_run_ids,
            "moduleSummaries": module_summaries,
            "documentHandoffs": document_handoffs,
            "unsupportedModules": unsupported,
            "limitations": limitations,
        }
    )


def _run_robotics_risk_module(payload: dict[str, Any]) -> Any:
    return run_robotics_risk_subagent(payload)


def _build_robotics_risk_input(
    shared_inputs: dict[str, Any],
    module_inputs: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    dimensions = module_inputs.get("dimensions")
    source_controls = module_inputs.get("sourceControls") or module_inputs.get("source_controls")
    return _drop_empty(
        {
            "enterpriseName": _clean_text(shared_inputs.get("enterpriseName")),
            "stockCode": _clean_text(shared_inputs.get("stockCode")),
            "timeRange": _clean_text(shared_inputs.get("timeRange")) or "近30天",
            "focus": _clean_text(module_inputs.get("focus")),
            "dimensions": dimensions if isinstance(dimensions, list) else [],
            "sourceControls": source_controls if isinstance(source_controls, dict) else {},
            "conversationContext": _clean_text(context.get("conversationContext")),
            "metadata": _drop_empty(
                {
                    "reportGoal": _clean_text(shared_inputs.get("reportGoal")),
                    "orchestration": {
                        "moduleId": "robotics_risk",
                        "sharedInputs": _drop_empty(
                            {
                                "enterpriseName": _clean_text(shared_inputs.get("enterpriseName")),
                                "stockCode": _clean_text(shared_inputs.get("stockCode")),
                                "timeRange": _clean_text(shared_inputs.get("timeRange")),
                                "reportGoal": _clean_text(shared_inputs.get("reportGoal")),
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
) -> str:
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
            _clean_text(executive_summary.get("opportunity")),
            _clean_text(executive_summary.get("risk")),
        ]
        merged = " ".join(line for line in summary_lines if line)
        if merged:
            return _truncate(merged, limit=300)
    brief_markdown = _clean_text(result_payload.get("briefMarkdown") or handoff_payload.get("compactMarkdown"))
    if brief_markdown:
        return _truncate(brief_markdown, limit=300)
    if limitations:
        return _truncate(limitations[0], limit=300)
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
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        clean = _clean_text(item)
        if clean and clean not in result:
            result.append(clean)
    return result


def _truncate(value: str, *, limit: int) -> str:
    clean = " ".join(str(value or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


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
