from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ...rag.errors import RAGContractError
from ...rag.schemas import RetrievalHit
from ...rag.service import build_cited_response
from ..reporting import (
    build_analysis_module_artifacts,
    build_report_generation_request,
    generate_analysis_report,
    report_preview_metadata,
)
from .analysis_modules import (
    AnalysisModuleContract,
    build_analysis_handoff_bundle,
    build_runtime_input,
    build_slot_catalog,
    get_analysis_module_registry,
    map_legacy_inputs_to_slot_updates,
    normalize_analysis_module_output,
)
from .analysis_slots import (
    AnalysisSlotDefinition,
    SHARED_ANALYSIS_FOCUS_TAGS,
    SHARED_ENTERPRISE_NAME,
    SHARED_REGION_SCOPE,
    SHARED_REPORT_GOAL,
    SHARED_STOCK_CODE,
    SHARED_TIME_RANGE,
    contains_explicit_correction_for_other_slots,
    has_slot_value,
    parse_explicit_correction_for_slots,
    parse_compound_answer_for_slots,
    parse_answer_for_group,
    slot_label,
)
from .mcp import build_mcp_graph
from .search import build_search_graph
from .source_intent import has_explicit_public_web_intent, has_fresh_public_info_intent, has_mixed_source_intent
from .state import AgentState

_search_graph = build_search_graph()
_mcp_graph = build_mcp_graph()

_KNOWLEDGE_HINTS = (
    "根据",
    "文件",
    "文档",
    "资料",
    "source",
    "citation",
    "引用",
    "证明",
    "依据",
    "manual",
    "policy",
    "spec",
    "搜索",
    "查找",
    "最新",
    "news",
)

_GRAPH_HINTS = (
    "知识图谱",
    "knowledge graph",
)

_MCP_HINTS = (
    "mcp",
    "server",
    "列出mcp工具",
    "列出工具",
    "list tools",
)

_MAX_COMPOSE_HISTORY_MESSAGES = 8


class PlannerOutput(BaseModel):
    needs_search: bool = Field(default=False)
    needs_mcp: bool = Field(default=False)
    needs_clarification: bool = Field(default=False)
    clarification_question: str = Field(default="")


def _extract_segment_context(chunk: dict) -> tuple[str, str] | None:
    semantic_segment = chunk.get("semantic_segment")
    if isinstance(semantic_segment, dict):
        seg_id = str(semantic_segment.get("id", "")).strip()
        seg_text = str(semantic_segment.get("text", "")).strip()
        if seg_id and seg_text:
            return seg_id, seg_text
    metadata = chunk.get("metadata")
    if isinstance(metadata, dict):
        seg_id = str(metadata.get("semantic_segment_id", "")).strip()
        seg_text = str(metadata.get("semantic_segment_text", "")).strip()
        if seg_id and seg_text:
            return seg_id, seg_text
    return None
def _build_kg_query(state: AgentState) -> str:
    entity = str(state.get("entity", "") or "").strip()
    graph_intent = str(state.get("graph_intent", "") or "").strip() or str(state.get("intent", "") or "").strip()
    user_message = str(state.get("user_message", "") or "").strip()
    if entity and graph_intent:
        return f"查询{entity}的{graph_intent}"
    if entity:
        return f"查询{entity}相关知识图谱"
    return user_message


def _conversation_context(state: AgentState) -> str:
    context = str(state.get("conversation_context", "") or "").strip()
    if context:
        return context

    history = state.get("conversation_history", [])
    if not isinstance(history, list) or not history:
        return ""

    lines = ["最近对话："]
    for item in history[-8:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if not role or not content:
            continue
        label = {"user": "用户", "assistant": "助手", "system": "系统"}.get(role.lower(), role)
        lines.append(f"{label}: {content[:360]}")
    return "\n".join(lines)


def _planner_prefers_search(message: str, *, rag_enabled: bool, web_enabled: bool) -> bool:
    lowered = message.lower()
    if any(token in lowered for token in _KNOWLEDGE_HINTS):
        return bool(rag_enabled or web_enabled)
    return False


def _planner_prefers_mcp(message: str, *, mcp_enabled: bool) -> bool:
    lowered = message.lower()
    return bool(mcp_enabled and any(token in lowered for token in _MCP_HINTS))


def _search_strategy(message: str, *, rag_enabled: bool, web_enabled: bool) -> str:
    if has_mixed_source_intent(message):
        if rag_enabled and web_enabled:
            return "hybrid"
        if rag_enabled:
            return "private_first"
        return "public_only"
    if has_explicit_public_web_intent(message):
        return "public_only"
    freshness = has_fresh_public_info_intent(message)
    if freshness and rag_enabled and web_enabled:
        return "hybrid"
    if freshness and web_enabled:
        return "public_only"
    if rag_enabled:
        return "private_first"
    if web_enabled:
        return "public_only"
    return "private_only"


def _enabled_analysis_modules(state: AgentState) -> list[str]:
    value = state.get("enabled_analysis_modules", [])
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _analysis_shared_inputs(state: AgentState) -> dict[str, Any]:
    value = state.get("analysis_shared_inputs", {})
    return dict(value) if isinstance(value, dict) else {}


def _analysis_module_inputs(state: AgentState) -> dict[str, dict[str, Any]]:
    value = state.get("analysis_module_inputs", {})
    if not isinstance(value, dict):
        return {}
    return {
        str(module_id): dict(payload)
        for module_id, payload in value.items()
        if str(module_id).strip() and isinstance(payload, dict)
    }


def _analysis_session_state(state: AgentState) -> dict[str, Any]:
    value = state.get("analysis_session", {})
    return dict(value) if isinstance(value, dict) else {}


def _analysis_contracts(enabled_modules: list[str]) -> tuple[list[AnalysisModuleContract], list[str]]:
    registry = get_analysis_module_registry()
    contracts: list[AnalysisModuleContract] = []
    unsupported: list[str] = []
    for module_id in enabled_modules:
        contract = registry.get(module_id)
        if contract is None:
            unsupported.append(module_id)
            continue
        contracts.append(contract)
    return contracts, unsupported


def _analysis_missing_field_id(item: dict[str, Any]) -> str:
    scope = str(item.get("scope", "")).strip()
    slot_id = str(item.get("slotId", "")).strip() or str(item.get("field", "")).strip()
    if scope == "module" and slot_id:
        return f"analysis.{slot_id}"
    return f"analysis.shared.{slot_id}"


def _analysis_shared_question(missing_fields: list[dict[str, Any]]) -> str:
    labels = [str(item.get("label", "")).strip() for item in missing_fields if str(item.get("label", "")).strip()]
    return "为继续已开启的分析模块，请先补充共享信息：" + "、".join(labels) + "。"


def _analysis_module_question(missing_fields: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for item in missing_fields:
        module_id = str(item.get("moduleId", "")).strip()
        label = str(item.get("label", "")).strip()
        module_name = str(item.get("moduleName", module_id)).strip() or module_id
        if not module_id or not label:
            continue
        grouped.setdefault(module_id, [])
        if label not in grouped[module_id]:
            grouped[module_id].append(label)
        names[module_id] = module_name
    parts = [f"{names[module_id]}：{'、'.join(labels)}" for module_id, labels in grouped.items() if labels]
    return "共享信息已收到，请继续补充模块信息：" + "；".join(parts) + "。"


def _analysis_clarification_question(*, missing_fields: list[dict[str, Any]], enabled_modules: list[str]) -> str:
    shared_missing = [item for item in missing_fields if str(item.get("scope", "")).strip() == "shared"]
    module_missing = [item for item in missing_fields if str(item.get("scope", "")).strip() == "module"]
    if shared_missing:
        labels: list[str] = []
        for item in shared_missing:
            label = str(item.get("label", "")).strip()
            if label and label not in labels:
                labels.append(label)
        suffix = "补齐后，系统只会在仍有缺口时继续追问模块特有信息。"
        return "为启动已选分析模块，请先补充共享信息：" + "、".join(labels) + "。" + suffix
    if module_missing:
        if len(enabled_modules) > 1:
            return _analysis_module_question(module_missing) + "补齐后将直接进入模块执行。"
        labels: list[str] = []
        for item in module_missing:
            label = str(item.get("label", "")).strip()
            if label and label not in labels:
                labels.append(label)
        return "共享信息已齐备，请补充当前模块仍缺少的信息：" + "、".join(labels) + "。补齐后将直接进入模块执行。"
    return ""


def _analysis_need_input_question(module_result: dict[str, Any], contract: AnalysisModuleContract) -> str:
    limitations = module_result.get("limitations", [])
    if isinstance(limitations, list):
        first = next((str(item).strip() for item in limitations if str(item).strip()), "")
        if first:
            return f"{contract.display_name} 仍需补充信息：{first}"
    error_message = str(module_result.get("errorMessage", "")).strip()
    if error_message:
        return f"{contract.display_name} 仍需补充信息：{error_message}"
    return f"{contract.display_name} 仍需补充必要输入后才能继续。"


def _base_analysis_session(existing: dict[str, Any], *, enabled_modules: list[str]) -> dict[str, Any]:
    compatibility = existing.get("compatibility", {}) if isinstance(existing.get("compatibility"), dict) else {}
    return {
        "sessionId": str(existing.get("sessionId", "")).strip(),
        "status": str(existing.get("status", "")).strip() or "collecting",
        "revision": _safe_int(existing.get("revision", 0), default=0),
        "enabledModules": _string_list(existing.get("enabledModules", enabled_modules)),
        "slotValues": dict(existing.get("slotValues", {})) if isinstance(existing.get("slotValues"), dict) else {},
        "slotStates": dict(existing.get("slotStates", {})) if isinstance(existing.get("slotStates"), dict) else {},
        "missingSlots": _string_list(existing.get("missingSlots", [])),
        "questionPlan": [dict(item) for item in existing.get("questionPlan", []) if isinstance(item, dict)]
        if isinstance(existing.get("questionPlan"), list)
        else [],
        "moduleStates": dict(existing.get("moduleStates", {})) if isinstance(existing.get("moduleStates"), dict) else {},
        "moduleResults": dict(existing.get("moduleResults", {})) if isinstance(existing.get("moduleResults"), dict) else {},
        "compatibility": {
            "legacySharedInputs": dict(compatibility.get("legacySharedInputs", {}))
            if isinstance(compatibility.get("legacySharedInputs"), dict)
            else {},
            "legacyModuleInputs": dict(compatibility.get("legacyModuleInputs", {}))
            if isinstance(compatibility.get("legacyModuleInputs"), dict)
            else {},
        },
        "handoffBundle": dict(existing.get("handoffBundle", {})) if isinstance(existing.get("handoffBundle"), dict) else {},
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        clean = str(item or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _merge_enabled_modules_into_session(session: dict[str, Any], explicit_enabled_modules: list[str]) -> tuple[list[str], bool]:
    current_enabled = _string_list(session.get("enabledModules", []))
    if not explicit_enabled_modules:
        session["enabledModules"] = current_enabled
        return current_enabled, False
    normalized_explicit = [module_id for module_id in explicit_enabled_modules if module_id]
    changed = normalized_explicit != current_enabled
    if changed:
        allowed = set(normalized_explicit)
        session["enabledModules"] = normalized_explicit
        session["moduleStates"] = {
            module_id: payload
            for module_id, payload in _dict_payload(session.get("moduleStates")).items()
            if module_id in allowed
        }
        session["moduleResults"] = {
            module_id: payload
            for module_id, payload in _dict_payload(session.get("moduleResults")).items()
            if module_id in allowed
        }
        compatibility = _dict_payload(session.get("compatibility"))
        legacy_module_inputs = _dict_payload(compatibility.get("legacyModuleInputs"))
        session["compatibility"] = {
            **compatibility,
            "legacyModuleInputs": {
                module_id: payload
                for module_id, payload in legacy_module_inputs.items()
                if module_id in allowed
            },
        }
        session["handoffBundle"] = {}
        session["missingSlots"] = []
        session["questionPlan"] = []
    return normalized_explicit, changed


def _dict_payload(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _merge_compatibility(session: dict[str, Any], compatibility_update: dict[str, Any]) -> list[str]:
    compatibility = _dict_payload(session.get("compatibility"))
    existing_shared = _dict_payload(compatibility.get("legacySharedInputs"))
    existing_modules = _dict_payload(compatibility.get("legacyModuleInputs"))
    update_shared = _dict_payload(compatibility_update.get("legacySharedInputs"))
    update_modules = _dict_payload(compatibility_update.get("legacyModuleInputs"))
    changed_modules: list[str] = []

    for key, value in update_shared.items():
        if existing_shared.get(key) != value:
            existing_shared[key] = value

    for module_id, payload in update_modules.items():
        if not isinstance(payload, dict):
            continue
        if existing_modules.get(module_id) != payload:
            changed_modules.append(module_id)
            existing_modules[module_id] = dict(payload)

    session["compatibility"] = {
        "legacySharedInputs": existing_shared,
        "legacyModuleInputs": existing_modules,
    }
    return changed_modules


def _mark_modules_stale(
    session: dict[str, Any],
    *,
    contracts: list[AnalysisModuleContract],
    changed_slots: list[str] | None = None,
    changed_modules: list[str] | None = None,
) -> list[str]:
    dirty_modules: list[str] = []
    dirty_slot_set = set(changed_slots or [])
    dirty_module_set = set(changed_modules or [])
    module_states = _dict_payload(session.get("moduleStates"))
    module_results = _dict_payload(session.get("moduleResults"))
    for contract in contracts:
        dependency_slots = set(contract.required_slots) | set(contract.optional_slots)
        affected_slots = sorted(dirty_slot_set.intersection(dependency_slots))
        if not affected_slots and contract.module_id not in dirty_module_set:
            continue
        if contract.module_id not in module_results and contract.module_id not in module_states:
            continue
        dirty_modules.append(contract.module_id)
        module_state = dict(module_states.get(contract.module_id, {}))
        module_state["status"] = "stale"
        if affected_slots:
            module_state["staleSlots"] = affected_slots
        module_states[contract.module_id] = module_state
        module_result = dict(module_results.get(contract.module_id, {}))
        if module_result:
            module_result["status"] = "stale"
            if affected_slots:
                module_result["staleSlots"] = affected_slots
            module_result["stale"] = True
            module_results[contract.module_id] = module_result
    session["moduleStates"] = module_states
    session["moduleResults"] = module_results
    return dirty_modules


def _apply_slot_updates(session: dict[str, Any], slot_updates: dict[str, Any], *, contracts: list[AnalysisModuleContract]) -> list[str]:
    if not slot_updates:
        return []
    slot_values = _dict_payload(session.get("slotValues"))
    slot_states = _dict_payload(session.get("slotStates"))
    changed_slots: list[str] = []
    for slot_id, value in slot_updates.items():
        if slot_values.get(slot_id) == value:
            continue
        slot_values[slot_id] = value
        changed_slots.append(slot_id)
    if not changed_slots:
        return []
    session["revision"] = _safe_int(session.get("revision", 0), default=0) + 1
    for slot_id in changed_slots:
        slot_states[slot_id] = {
            "status": "resolved",
            "updatedRevision": int(session["revision"]),
            "value": slot_values.get(slot_id),
        }
    session["slotValues"] = slot_values
    session["slotStates"] = slot_states
    _mark_modules_stale(session, contracts=contracts, changed_slots=changed_slots)
    return changed_slots


def _required_slot_ids(contracts: list[AnalysisModuleContract]) -> list[str]:
    result: list[str] = []
    for contract in contracts:
        for slot_id in contract.required_slots:
            if slot_id not in result:
                result.append(slot_id)
    return result


def _relevant_slot_ids(contracts: list[AnalysisModuleContract]) -> list[str]:
    result = _required_slot_ids(contracts)
    for contract in contracts:
        for slot_id in contract.optional_slots:
            if slot_id not in result:
                result.append(slot_id)
    return result


def _missing_slot_entries(
    *,
    required_slot_ids: list[str],
    slot_catalog: dict[str, AnalysisSlotDefinition],
    contracts: list[AnalysisModuleContract],
    slot_values: dict[str, Any],
) -> list[dict[str, Any]]:
    contract_names = {contract.module_id: contract.display_name for contract in contracts}
    missing: list[dict[str, Any]] = []
    for slot_id in required_slot_ids:
        definition = slot_catalog.get(slot_id)
        if definition is None:
            continue
        if any(not has_slot_value(slot_values.get(depends_on)) for depends_on in definition.depends_on):
            continue
        if has_slot_value(slot_values.get(slot_id)):
            continue
        missing.append(
            {
                "scope": definition.scope,
                "slotId": definition.slot_id,
                "label": definition.label,
                "groupId": definition.group_id,
                "moduleId": definition.module_id,
                "moduleName": contract_names.get(definition.module_id, definition.module_id),
            }
        )
    missing.sort(key=lambda item: (_slot_priority(slot_catalog, item.get("slotId", "")), item.get("label", "")))
    return missing


def _slot_priority(slot_catalog: dict[str, AnalysisSlotDefinition], slot_id: str) -> int:
    definition = slot_catalog.get(str(slot_id))
    return int(definition.priority) if definition is not None else 999


def _build_question_plan(
    *,
    missing_entries: list[dict[str, Any]],
    relevant_slot_ids: list[str],
    slot_catalog: dict[str, AnalysisSlotDefinition],
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    seen_groups: set[str] = set()
    for item in missing_entries:
        group_id = str(item.get("groupId", "")).strip()
        if not group_id or group_id in seen_groups:
            continue
        seen_groups.add(group_id)
        group_slot_ids = [
            slot_id
            for slot_id in relevant_slot_ids
            if slot_id in slot_catalog and slot_catalog[slot_id].group_id == group_id
        ]
        labels = [slot_label(slot_catalog, slot_id) for slot_id in group_slot_ids if slot_id in slot_catalog]
        required_slot_ids = [str(entry.get("slotId", "")).strip() for entry in missing_entries if entry.get("groupId") == group_id]
        first_definition = slot_catalog.get(required_slot_ids[0]) if required_slot_ids else None
        question = ""
        if first_definition is not None and first_definition.prompt_hint:
            question = first_definition.prompt_hint
        if not question:
            question = "请补充以下信息：" + "、".join(label for label in labels if label) + "。"
        plan.append(
            {
                "groupId": group_id,
                "slotIds": group_slot_ids,
                "requiredSlotIds": required_slot_ids,
                "labels": labels,
                "question": question,
            }
        )
    return plan


def _shared_summary_from_slot_values(slot_values: dict[str, Any]) -> dict[str, Any]:
    return {
        "enterpriseName": str(slot_values.get(SHARED_ENTERPRISE_NAME, "") or "").strip(),
        "stockCode": str(slot_values.get(SHARED_STOCK_CODE, "") or "").strip(),
        "timeRange": str(slot_values.get(SHARED_TIME_RANGE, "") or "").strip(),
        "reportGoal": str(slot_values.get(SHARED_REPORT_GOAL, "") or "").strip(),
        "analysisFocusTags": list(slot_values.get(SHARED_ANALYSIS_FOCUS_TAGS, []))
        if isinstance(slot_values.get(SHARED_ANALYSIS_FOCUS_TAGS), list)
        else [],
        "regionScope": list(slot_values.get(SHARED_REGION_SCOPE, []))
        if isinstance(slot_values.get(SHARED_REGION_SCOPE), list)
        else [],
    }


def _analysis_shared_inputs_from_slot_values(slot_values: dict[str, Any]) -> dict[str, Any]:
    shared_summary = _shared_summary_from_slot_values(slot_values)
    return {
        "enterpriseName": shared_summary.get("enterpriseName", ""),
        "stockCode": shared_summary.get("stockCode", ""),
        "timeRange": shared_summary.get("timeRange", ""),
        "reportGoal": shared_summary.get("reportGoal", ""),
    }


def _current_question_group(session: dict[str, Any]) -> dict[str, Any]:
    question_plan = session.get("questionPlan", [])
    if not isinstance(question_plan, list) or not question_plan:
        return {}
    first = question_plan[0]
    return dict(first) if isinstance(first, dict) else {}


def _has_current_results_for_all_enabled_modules(session: dict[str, Any]) -> bool:
    enabled_modules = _string_list(session.get("enabledModules"))
    module_results = _dict_payload(session.get("moduleResults"))
    module_states = _dict_payload(session.get("moduleStates"))
    if not enabled_modules:
        return False
    for module_id in enabled_modules:
        result = module_results.get(module_id)
        state = module_states.get(module_id, {})
        if not isinstance(result, dict):
            return False
        if str(result.get("status", "")).strip() == "stale":
            return False
        if isinstance(state, dict) and str(state.get("status", "")).strip() == "stale":
            return False
    return True


def _has_stale_modules(session: dict[str, Any]) -> bool:
    module_states = _dict_payload(session.get("moduleStates"))
    return any(str(payload.get("status", "")).strip() == "stale" for payload in module_states.values() if isinstance(payload, dict))


def _analysis_bundle_system_section(state: AgentState) -> str:
    bundle = state.get("analysis_handoff_bundle", {})
    if not isinstance(bundle, dict) or not bundle:
        return ""
    lines = ["分析模块编排结果："]
    enabled_modules = bundle.get("enabledModules", [])
    if isinstance(enabled_modules, list) and enabled_modules:
        lines.append("已启用模块：" + ", ".join(str(item).strip() for item in enabled_modules if str(item).strip()))
    shared_summary = bundle.get("sharedInputSummary", {})
    if isinstance(shared_summary, dict) and shared_summary:
        shared_lines = []
        for key, label in (
            ("enterpriseName", "企业"),
            ("stockCode", "股票代码"),
            ("timeRange", "时间范围"),
            ("reportGoal", "报告目标"),
        ):
            value = str(shared_summary.get(key, "")).strip()
            if value:
                shared_lines.append(f"{label}={value}")
        if shared_lines:
            lines.append("共享输入：" + "；".join(shared_lines))
    module_results = bundle.get("moduleResults", [])
    if isinstance(module_results, list) and module_results:
        lines.append("模块结果：")
        for index, item in enumerate(module_results, start=1):
            if not isinstance(item, dict):
                continue
            module_id = str(item.get("moduleId", "")).strip()
            display_name = str(item.get("displayName", module_id)).strip() or module_id
            status = str(item.get("status", "")).strip()
            run_id = str(item.get("runId", "")).strip()
            summary = str(item.get("summary", "")).strip()
            source_count = _analysis_module_source_count(item)
            header = f"[{index}] module={module_id} name={display_name} status={status}"
            if run_id:
                header += f" runId={run_id}"
            header += f" sourceCount={source_count}"
            lines.append(header)
            if summary:
                lines.append(summary)
            if source_count <= 0:
                lines.append(
                    "证据边界：该模块未返回可引用来源。主回答不得基于行业常识、公开基本面、模型记忆或未列明来源生成风险/机会判断；只能说明当前没有证据、列出失败/空结果状态，并建议补采或重试。"
                )
    limitations = bundle.get("limitations", [])
    if isinstance(limitations, list) and limitations:
        lines.append("限制说明：" + "；".join(str(item).strip() for item in limitations if str(item).strip()))
    return "\n".join(lines)


def _analysis_report_system_section(state: AgentState) -> str:
    report = state.get("analysis_report", {})
    if not isinstance(report, dict) or not report:
        return ""
    lines = ["报告生成结果："]
    title = str(report.get("title", "")).strip()
    status = str(report.get("status", "")).strip()
    report_id = str(report.get("reportId", "")).strip()
    if title or status:
        lines.append(f"title={title} status={status} reportId={report_id}")
    preview = str(report.get("preview", "")).strip()
    if preview:
        lines.append("报告正文预览：")
        lines.append(preview[:1200])
    lines.append("最终回复应提示报告已生成，可结合预览概述结果；下载动作由界面提供，不要在回复中输出原始下载链接；不要在回复中补写模块没有提供的领域结论。")
    return "\n".join(lines)


def _analysis_module_source_count(module_result: dict[str, Any]) -> int:
    source_references = module_result.get("sourceReferences", [])
    if isinstance(source_references, list) and source_references:
        return len(source_references)
    handoff = module_result.get("documentHandoff", {})
    if not isinstance(handoff, dict):
        return 0
    executive_summary = handoff.get("executiveSummary", {})
    if isinstance(executive_summary, dict):
        try:
            return max(0, int(executive_summary.get("sourceCount", 0) or 0))
        except (TypeError, ValueError):
            return 0
    evidence_table = handoff.get("evidenceTable", [])
    if isinstance(evidence_table, list):
        return len(evidence_table)
    return 0


def plan_route_node(state: AgentState):
    user_message = str(state.get("user_message", "")).strip()
    entity = str(state.get("entity", "")).strip()
    graph_intent = str(state.get("graph_intent", "")).strip()
    enabled_analysis_modules = _enabled_analysis_modules(state)
    kg_enabled = bool(state.get("kg_enabled", False))
    rag_enabled = bool(state.get("rag_enabled", False))
    web_enabled = bool(state.get("web_enabled", False))
    mcp_enabled = bool(state.get("mcp_enabled", False))
    conversation_context = _conversation_context(state)

    if enabled_analysis_modules:
        return {
            "intent": "analysis",
            "needs_search": False,
            "needs_mcp": False,
            "needs_clarification": False,
            "clarification_question": "",
            "missing_fields": [],
            "search_request": {},
            "mcp_request": {},
            "search_result": {},
            "mcp_result": {},
            "analysis_results": {},
            "analysis_handoff_bundle": {},
            "analysis_missing_fields": [],
            "analysis_completed": False,
            "analysis_unsupported_modules": [],
            "analysis_module_artifacts": [],
            "analysis_report_request": {},
            "analysis_report": {},
            "analysis_report_artifact": {},
            "analysis_report_generated": False,
            "search_completed": False,
            "mcp_completed": False,
            "rag_chunks": [],
            "rag_citations": [],
            "rag_no_evidence": False,
            "rag_debug": {},
            "debug": {
                **(state.get("debug", {}) if isinstance(state.get("debug"), dict) else {}),
                "analysisPlanner": {
                    "enabledModules": enabled_analysis_modules,
                    "conversationContextPresent": bool(conversation_context),
                },
            },
        }

    if not user_message:
        return {
            "intent": "clarify",
            "needs_search": False,
            "needs_mcp": False,
            "needs_clarification": True,
            "clarification_question": "请先提供你的问题或任务目标。",
            "missing_fields": ["user_message"],
        }

    heuristic_needs_search = _planner_prefers_search(user_message, rag_enabled=rag_enabled, web_enabled=web_enabled)
    if kg_enabled and (entity or graph_intent or any(token in user_message.lower() for token in _GRAPH_HINTS)):
        heuristic_needs_search = True
    needs_search = heuristic_needs_search
    needs_mcp = _planner_prefers_mcp(user_message, mcp_enabled=mcp_enabled)
    needs_clarification = False
    clarification_question = ""
    llm = state.get("main_llm")
    if hasattr(llm, "with_structured_output"):
        try:
            structured_llm = llm.with_structured_output(PlannerOutput)
            response = structured_llm.invoke(
                [
                    {
                        "role": "system",
                        "content": (
                            "You route user requests for a main agent. Decide whether the request needs "
                            "search evidence, MCP action execution, or clarification before proceeding."
                            + (f"\n\nConversation memory:\n{conversation_context}" if conversation_context else "")
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"message={user_message}\n"
                            f"rag_enabled={rag_enabled}\n"
                            f"web_enabled={web_enabled}\n"
                            f"mcp_enabled={mcp_enabled}\n"
                        ),
                    },
                ]
            )
            # The model can broaden tool usage, but should not disable deterministic
            # evidence lookup when the request is clearly asking about uploaded knowledge.
            needs_search = heuristic_needs_search or (bool(response.needs_search) and bool(rag_enabled or web_enabled))
            needs_mcp = bool(response.needs_mcp) and mcp_enabled
            needs_clarification = bool(response.needs_clarification)
            clarification_question = str(response.clarification_question).strip()
        except Exception:
            pass
    missing_fields: list[str] = []
    if needs_search and user_message.lower() in {"搜索", "查找", "search"}:
        needs_search = False
        needs_clarification = True
        clarification_question = clarification_question or "请说明你要搜索的具体主题或问题。"
        missing_fields = ["search_query"]

    intent = "answer"
    if needs_clarification:
        intent = "clarify"
    elif needs_search and needs_mcp:
        intent = "hybrid"
    elif needs_search:
        intent = "search"
    elif needs_mcp:
        intent = "act"

    return {
        "intent": intent,
        "needs_search": needs_search,
        "needs_mcp": needs_mcp,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "missing_fields": missing_fields,
        "search_request": {
            "query": user_message,
            "preferred_strategy": _search_strategy(user_message, rag_enabled=rag_enabled, web_enabled=web_enabled),
            "entity": entity,
            "graph_intent": graph_intent,
        },
        "mcp_request": {"request": user_message},
        "search_result": {},
        "mcp_result": {},
        "search_completed": False,
        "mcp_completed": False,
        "rag_chunks": [],
        "rag_citations": [],
        "rag_no_evidence": False,
        "rag_debug": {},
        "debug": {},
    }


def route_after_plan(state: AgentState) -> str:
    if state.get("needs_clarification", False):
        return "clarify"
    if _enabled_analysis_modules(state):
        return "analysis_intake"
    if state.get("needs_search", False) and not state.get("search_completed", False):
        return "search_subagent"
    if state.get("needs_mcp", False) and not state.get("mcp_completed", False):
        return "mcp_subagent"
    return "compose_answer"


def route_after_search(state: AgentState) -> str:
    if state.get("needs_clarification", False):
        return "clarify"
    if state.get("needs_mcp", False) and not state.get("mcp_completed", False):
        return "mcp_subagent"
    return "compose_answer"


def route_after_mcp(state: AgentState) -> str:
    if state.get("needs_clarification", False):
        return "clarify"
    return "compose_answer"


def route_after_analysis_intake(state: AgentState) -> str:
    if state.get("needs_clarification", False):
        return "clarify"
    if bool(state.get("analysis_completed", False)):
        return "compose_answer"
    return "analysis_modules"


def route_after_analysis_modules(state: AgentState) -> str:
    if state.get("needs_clarification", False):
        return "clarify"
    return "compose_answer"


def route_after_report_generation(state: AgentState) -> str:
    return "compose_answer"


def analysis_intake_node(state: AgentState):
    explicit_enabled_modules = _enabled_analysis_modules(state)
    shared_inputs = _analysis_shared_inputs(state)
    module_inputs = _analysis_module_inputs(state)
    session = _base_analysis_session(_analysis_session_state(state), enabled_modules=explicit_enabled_modules)
    enabled_modules, enabled_modules_changed = _merge_enabled_modules_into_session(session, explicit_enabled_modules)
    contracts, unsupported_modules = _analysis_contracts(enabled_modules)
    slot_catalog = build_slot_catalog(contracts)
    relevant_slot_ids = _relevant_slot_ids(contracts)

    slot_updates, compatibility_update = map_legacy_inputs_to_slot_updates(
        contracts=contracts,
        slot_catalog=slot_catalog,
        shared_inputs=shared_inputs,
        module_inputs=module_inputs,
    )
    compatibility_changed_modules = _merge_compatibility(session, compatibility_update)
    if enabled_modules_changed:
        compatibility_changed_modules = list({*compatibility_changed_modules, *enabled_modules})

    if not slot_updates and not shared_inputs and not module_inputs:
        current_group = _current_question_group(session)
        current_slot_ids = [slot_id for slot_id in current_group.get("slotIds", []) if slot_id in slot_catalog]
        user_message = str(state.get("user_message", "")).strip()
        correction_updates = parse_explicit_correction_for_slots(
            slot_ids=relevant_slot_ids,
            slot_catalog=slot_catalog,
            user_message=user_message,
        )
        if current_slot_ids and not contains_explicit_correction_for_other_slots(
            slot_ids=current_slot_ids,
            user_message=user_message,
        ):
            slot_updates = parse_answer_for_group(
                slot_ids=current_slot_ids,
                slot_catalog=slot_catalog,
                user_message=user_message,
            )
        compound_slot_ids = current_slot_ids or relevant_slot_ids
        if correction_updates:
            correction_slot_ids = set(correction_updates)
            compound_slot_ids = [slot_id for slot_id in compound_slot_ids if slot_id not in correction_slot_ids]
        compound_updates = parse_compound_answer_for_slots(
            slot_ids=compound_slot_ids,
            slot_catalog=slot_catalog,
            user_message=user_message,
        )
        slot_updates = {**slot_updates, **compound_updates, **correction_updates}

    changed_slots = _apply_slot_updates(session, slot_updates, contracts=contracts)
    if compatibility_changed_modules:
        _mark_modules_stale(
            session,
            contracts=contracts,
            changed_modules=compatibility_changed_modules,
        )

    missing_entries = _missing_slot_entries(
        required_slot_ids=_required_slot_ids(contracts),
        slot_catalog=slot_catalog,
        contracts=contracts,
        slot_values=_dict_payload(session.get("slotValues")),
    )
    question_plan = _build_question_plan(
        missing_entries=missing_entries,
        relevant_slot_ids=relevant_slot_ids,
        slot_catalog=slot_catalog,
    )
    session["questionPlan"] = question_plan
    session["missingSlots"] = [str(item.get("slotId", "")).strip() for item in missing_entries if str(item.get("slotId", "")).strip()]
    session["enabledModules"] = enabled_modules

    clarification_question = ""
    needs_clarification = bool(missing_entries)
    if needs_clarification:
        clarification_question = _analysis_clarification_question(
            missing_fields=missing_entries,
            enabled_modules=enabled_modules,
        ) or (str(question_plan[0].get("question", "")).strip() if question_plan else "")

    analysis_completed = False
    if missing_entries:
        session["status"] = "collecting"
    elif _has_stale_modules(session):
        session["status"] = "stale"
    elif _has_current_results_for_all_enabled_modules(session):
        session["status"] = "completed"
        analysis_completed = True
    else:
        session["status"] = "ready"

    debug_payload = {
        "sessionId": str(session.get("sessionId", "")).strip(),
        "status": str(session.get("status", "")).strip(),
        "revision": int(session.get("revision", 0) or 0),
        "enabledModules": enabled_modules,
        "supportedModules": [contract.module_id for contract in contracts],
        "unsupportedModules": unsupported_modules,
        "changedSlots": changed_slots,
        "missingSlots": list(session.get("missingSlots", [])),
        "questionPlan": list(session.get("questionPlan", [])),
        "sharedInputsReady": not bool(missing_entries),
    }
    return {
        "enabled_analysis_modules": enabled_modules,
        "analysis_session": session,
        "analysis_shared_inputs": _analysis_shared_inputs_from_slot_values(_dict_payload(session.get("slotValues"))),
        "analysis_results": _dict_payload(session.get("moduleResults")),
        "analysis_handoff_bundle": _dict_payload(session.get("handoffBundle")),
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "missing_fields": [_analysis_missing_field_id(item) for item in missing_entries],
        "analysis_missing_fields": missing_entries,
        "analysis_unsupported_modules": unsupported_modules,
        "analysis_completed": analysis_completed,
        "debug": {
            **(state.get("debug", {}) if isinstance(state.get("debug"), dict) else {}),
            "analysisIntake": debug_payload,
        },
    }


def analysis_modules_node(state: AgentState):
    session = _base_analysis_session(_analysis_session_state(state), enabled_modules=_enabled_analysis_modules(state))
    enabled_modules = _string_list(session.get("enabledModules"))
    contracts, unsupported_modules = _analysis_contracts(enabled_modules)
    context = {
        "conversationContext": _conversation_context(state),
        "userMessage": str(state.get("user_message", "")).strip(),
    }
    results: dict[str, dict[str, Any]] = _dict_payload(session.get("moduleResults"))
    needs_clarification = False
    clarification_question = ""
    module_states = _dict_payload(session.get("moduleStates"))
    session["status"] = "running"

    modules_to_run: list[AnalysisModuleContract] = []
    for contract in contracts:
        module_result = results.get(contract.module_id)
        module_state = module_states.get(contract.module_id, {})
        if not isinstance(module_result, dict):
            modules_to_run.append(contract)
            continue
        if str(module_result.get("status", "")).strip() == "stale":
            modules_to_run.append(contract)
            continue
        if isinstance(module_state, dict) and str(module_state.get("status", "")).strip() == "stale":
            modules_to_run.append(contract)
            continue

    for contract in contracts:
        if contract not in modules_to_run:
            continue
        runtime_input = build_runtime_input(
            contract,
            slot_values=_dict_payload(session.get("slotValues")),
            compatibility=_dict_payload(session.get("compatibility")),
            context=context,
        )
        normalized_result = normalize_analysis_module_output(
            contract,
            contract.run(runtime_input) if contract.run is not None else {},
            input_revision=_safe_int(session.get("revision", 0), default=0),
        )
        results[contract.module_id] = normalized_result
        module_states[contract.module_id] = {
            "status": str(normalized_result.get("status", "")).strip() or "failed",
            "lastRunRevision": _safe_int(session.get("revision", 0), default=0),
            "staleSlots": [],
        }
        if normalized_result.get("status") == "need_input" and not clarification_question:
            needs_clarification = True
            clarification_question = _analysis_need_input_question(normalized_result, contract)

    session["moduleResults"] = results
    session["moduleStates"] = module_states
    bundle = build_analysis_handoff_bundle(
        analysis_session=session,
        shared_summary=_shared_summary_from_slot_values(_dict_payload(session.get("slotValues"))),
        module_results=results,
        unsupported_modules=unsupported_modules,
    )
    session["handoffBundle"] = bundle
    if needs_clarification:
        session["status"] = "collecting"
    elif any(str(result.get("status", "")).strip() == "failed" for result in results.values() if isinstance(result, dict)):
        session["status"] = "failed"
    elif _has_stale_modules(session):
        session["status"] = "stale"
    else:
        session["status"] = "completed"

    debug_payload = {
        "sessionId": str(session.get("sessionId", "")).strip(),
        "status": str(session.get("status", "")).strip(),
        "revision": _safe_int(session.get("revision", 0), default=0),
        "enabledModules": enabled_modules,
        "executedModules": [contract.module_id for contract in modules_to_run],
        "completedModules": [module_id for module_id, result in results.items() if result.get("status") in {"done", "partial"}],
        "statuses": {
            module_id: str(result.get("status", "")).strip()
            for module_id, result in results.items()
            if isinstance(result, dict)
        },
        "runIds": {
            module_id: str(result.get("runId", "")).strip()
            for module_id, result in results.items()
            if isinstance(result, dict) and str(result.get("runId", "")).strip()
        },
        "unsupportedModules": unsupported_modules,
        "bundleLimitations": list(bundle.get("limitations", [])) if isinstance(bundle.get("limitations", []), list) else [],
    }
    module_artifacts: list[dict[str, Any]] = []
    report_request: dict[str, Any] = {}
    if session["status"] == "completed" and not needs_clarification:
        module_artifacts = build_analysis_module_artifacts(
            analysis_session=session,
            module_results=results,
            module_ids=enabled_modules,
        )
        report_request = build_report_generation_request(
            analysis_session=session,
            module_artifacts=module_artifacts,
        )
        debug_payload["moduleArtifactIds"] = [
            str(item.get("artifactId", "")).strip()
            for item in module_artifacts
            if isinstance(item, dict) and str(item.get("artifactId", "")).strip()
        ]
    return {
        "enabled_analysis_modules": enabled_modules,
        "analysis_session": session,
        "analysis_shared_inputs": _analysis_shared_inputs_from_slot_values(_dict_payload(session.get("slotValues"))),
        "analysis_results": results,
        "analysis_handoff_bundle": bundle,
        "analysis_completed": not needs_clarification,
        "analysis_unsupported_modules": unsupported_modules,
        "analysis_module_artifacts": module_artifacts,
        "analysis_report_request": report_request,
        "analysis_report": {},
        "analysis_report_artifact": {},
        "analysis_report_generated": False,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "missing_fields": ["analysis.modules"] if needs_clarification else [],
        "debug": {
            **(state.get("debug", {}) if isinstance(state.get("debug"), dict) else {}),
            "analysisModules": debug_payload,
        },
    }


def report_generation_node(state: AgentState):
    module_results = state.get("analysis_results", {})
    if not isinstance(module_results, dict):
        module_results = {}
    handoff_bundle = state.get("analysis_handoff_bundle", {})
    if not isinstance(handoff_bundle, dict):
        handoff_bundle = {}
    analysis_session = _analysis_session_state(state)
    try:
        artifact = generate_analysis_report(
            analysis_session=analysis_session,
            handoff_bundle=handoff_bundle,
            module_results=module_results,
            report_writer=state.get("main_llm"),
        )
    except Exception as exc:
        return {
            "analysis_report": {},
            "analysis_report_artifact": {},
            "analysis_report_generated": False,
            "debug": {
                **(state.get("debug", {}) if isinstance(state.get("debug"), dict) else {}),
                "analysisReport": {
                    "status": "failed",
                    "error": str(exc),
                },
            },
        }
    if not artifact:
        return {
            "analysis_report": {},
            "analysis_report_artifact": {},
            "analysis_report_generated": False,
            "debug": {
                **(state.get("debug", {}) if isinstance(state.get("debug"), dict) else {}),
                "analysisReport": {"status": "skipped"},
            },
        }
    metadata = report_preview_metadata(artifact)
    return {
        "analysis_report": metadata,
        "analysis_report_artifact": artifact,
        "analysis_report_generated": True,
        "debug": {
            **(state.get("debug", {}) if isinstance(state.get("debug"), dict) else {}),
            "analysisReport": {
                "status": metadata.get("status", ""),
                "reportId": metadata.get("reportId", ""),
                "title": metadata.get("title", ""),
            },
        },
    }


def search_subagent_node(state: AgentState):
    request = state.get("search_request", {})
    if not isinstance(request, dict):
        request = {}

    result = _search_graph.invoke(
        {
            "llm": state.get("search_llm"),
            "query": str(request.get("query", state.get("user_message", ""))).strip(),
            "conversation_history": list(state.get("conversation_history", [])) if isinstance(state.get("conversation_history"), list) else [],
            "conversation_context": str(state.get("conversation_context", "") or "").strip(),
            "user_id": state["user_id"],
            "workspace_id": state["workspace_id"],
            "kg_enabled": bool(state.get("kg_enabled", False)),
            "rag_enabled": bool(state.get("rag_enabled", False)),
            "rag_debug_enabled": bool(state.get("rag_debug_enabled", False)),
            "entity": str(request.get("entity", state.get("entity", ""))).strip(),
            "graph_intent": str(request.get("graph_intent", state.get("graph_intent", ""))).strip(),
            "preferred_strategy": str(request.get("preferred_strategy", "")),
            "use_kg": False,
            "use_rag": False,
            "use_web": False,
            "kg_result": {},
            "rag_result": {},
            "web_result": {},
            "evidence": [],
            "graph_data": {},
            "graph_meta": {},
            "rag_chunks": [],
            "rag_debug": {},
            "sufficient": False,
            "status": "pending",
            "summary": "",
            "follow_up_question": "",
            "strategy": "",
        }
    )
    search_result = {
        "status": str(result.get("status", "")),
        "strategy": str(result.get("strategy", "")),
        "summary": str(result.get("summary", "")),
        "sufficient": bool(result.get("sufficient", False)),
        "follow_up_question": str(result.get("follow_up_question", "")),
        "evidence": result.get("evidence", []) if isinstance(result.get("evidence"), list) else [],
        "web_result": result.get("web_result", {}) if isinstance(result.get("web_result"), dict) else {},
    }
    update: dict[str, Any] = {
        "search_result": search_result,
        "search_completed": True,
        "graph_data": result.get("graph_data", {}) if isinstance(result.get("graph_data"), dict) else {},
        "graph_meta": result.get("graph_meta", {}) if isinstance(result.get("graph_meta"), dict) else {},
        "rag_chunks": result.get("rag_chunks", []) if isinstance(result.get("rag_chunks"), list) else [],
        "rag_debug": result.get("rag_debug", {}) if isinstance(result.get("rag_debug"), dict) else {},
        "debug": {
            **(state.get("debug", {}) if isinstance(state.get("debug"), dict) else {}),
            "search": search_result,
        },
    }
    if search_result["status"] == "need_input" and search_result["follow_up_question"]:
        update["needs_clarification"] = True
        update["clarification_question"] = search_result["follow_up_question"]
        update["rag_no_evidence"] = True
    return update


def mcp_subagent_node(state: AgentState):
    request = state.get("mcp_request", {})
    if not isinstance(request, dict):
        request = {}
    result = _mcp_graph.invoke(
        {
            "llm": state.get("mcp_llm"),
            "request": str(request.get("request", state.get("user_message", ""))).strip(),
            "user_id": state["user_id"],
            "workspace_id": state["workspace_id"],
            "selected_server": "",
            "selected_tool": "",
            "tool_args": {},
            "execution_result": {},
            "status": "pending",
            "summary": "",
            "follow_up_question": "",
            "artifacts": {},
        }
    )
    mcp_result = {
        "status": str(result.get("status", "")),
        "summary": str(result.get("summary", "")),
        "follow_up_question": str(result.get("follow_up_question", "")),
        "artifacts": result.get("artifacts", {}) if isinstance(result.get("artifacts"), dict) else {},
        "execution_result": result.get("execution_result", {}) if isinstance(result.get("execution_result"), dict) else {},
    }
    update: dict[str, Any] = {
        "mcp_result": mcp_result,
        "mcp_completed": True,
        "debug": {
            **(state.get("debug", {}) if isinstance(state.get("debug"), dict) else {}),
            "mcp": mcp_result,
        },
    }
    if mcp_result["status"] == "need_input" and mcp_result["follow_up_question"]:
        update["needs_clarification"] = True
        update["clarification_question"] = mcp_result["follow_up_question"]
    return update


def clarify_node(state: AgentState):
    question = str(state.get("clarification_question", "")).strip() or "请补充更多信息后再试。"
    return {"reply": question}


def _build_system_content(state: AgentState) -> str:
    system_content = state["prompt_template"].format(role=state["role"], system_prompt=state["system_prompt"])
    graph_meta = state.get("graph_meta", {})
    if isinstance(graph_meta, dict) and graph_meta:
        kg_lines: list[str] = []
        source = str(graph_meta.get("source", "")).strip()
        if source:
            kg_lines.append(f"source={source}")
        cypher = str(graph_meta.get("cypher", "")).strip()
        if cypher:
            kg_lines.append(f"cypher={cypher}")
        fallback_reason = str(graph_meta.get("fallbackReason", "")).strip()
        if fallback_reason:
            kg_lines.append(f"fallback_reason={fallback_reason}")
        context_size = graph_meta.get("contextSize")
        if isinstance(context_size, int):
            kg_lines.append(f"context_size={context_size}")
        if kg_lines:
            system_content = f"{system_content}\n\nKnowledge Graph metadata:\n" + "\n".join(kg_lines)
    conversation_context = _conversation_context(state)
    if conversation_context:
        system_content = f"{system_content}\n\n对话记忆：\n{conversation_context}"
    search_result = state.get("search_result", {})
    if isinstance(search_result, dict) and search_result:
        summary = str(search_result.get("summary", "")).strip()
        evidence_items = search_result.get("evidence", [])
        if summary:
            system_content = f"{system_content}\n\nSearch Subagent summary:\n{summary}"
        if isinstance(evidence_items, list) and evidence_items:
            evidence_lines = []
            for idx, item in enumerate(evidence_items[:5], start=1):
                if not isinstance(item, dict):
                    continue
                evidence_lines.append(
                    f"[{idx}] source_type={item.get('source_type')} source={item.get('source')} title={item.get('title')}\n{item.get('snippet')}"
                )
            if evidence_lines:
                system_content = f"{system_content}\n\n检索证据如下：\n" + "\n\n".join(evidence_lines)

    rag_chunks = state.get("rag_chunks", [])
    if isinstance(rag_chunks, list) and rag_chunks:
        segment_contexts: list[tuple[str, str]] = []
        seen_segment_ids: set[str] = set()
        for item in rag_chunks:
            if not isinstance(item, dict):
                continue
            segment_context = _extract_segment_context(item)
            if segment_context is None:
                continue
            segment_id, segment_text = segment_context
            if segment_id in seen_segment_ids:
                continue
            seen_segment_ids.add(segment_id)
            segment_contexts.append((segment_id, segment_text))
        if segment_contexts:
            context_lines = [
                f"[{idx}] segment_id={segment_id}\n{segment_text}"
                for idx, (segment_id, segment_text) in enumerate(segment_contexts, start=1)
            ]
            system_content = f"{system_content}\n\n命中句所在语义段上下文：\n" + "\n\n".join(context_lines)

    mcp_result = state.get("mcp_result", {})
    if isinstance(mcp_result, dict) and mcp_result:
        summary = str(mcp_result.get("summary", "")).strip()
        if summary:
            system_content = f"{system_content}\n\nMCP Subagent summary:\n{summary}"
    analysis_section = _analysis_bundle_system_section(state)
    if analysis_section:
        system_content = f"{system_content}\n\n{analysis_section}"
    report_section = _analysis_report_system_section(state)
    if report_section:
        system_content = f"{system_content}\n\n{report_section}"
    return system_content


def _history_messages_for_compose(state: AgentState, *, limit: int = _MAX_COMPOSE_HISTORY_MESSAGES) -> list[Any]:
    history = state.get("conversation_history", [])
    if not isinstance(history, list) or not history:
        return []

    normalized: list[Any] = []
    for item in history[-limit:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if not role or not content:
            continue
        if role == "user":
            normalized.append(HumanMessage(content=content))
        elif role == "assistant":
            normalized.append(AIMessage(content=content))
    return normalized


def compose_answer_node(state: AgentState):
    llm = state["main_llm"]
    system_content = _build_system_content(state)
    history_messages = _history_messages_for_compose(state)
    messages: list[Any] = [SystemMessage(content=system_content), *history_messages, HumanMessage(content=state["user_message"])]
    response = llm.invoke(messages)
    reply = str(getattr(response, "content", "")).strip()
    if not reply:
        reply = "暂时无法生成有效回复，请稍后重试。"
    return {"reply": reply}


def answer_with_citations_node(state: AgentState):
    hits: list[RetrievalHit] = []
    raw_chunks = state.get("rag_chunks", [])
    if not isinstance(raw_chunks, list):
        raw_chunks = []

    for raw in raw_chunks:
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source", "")).strip()
        chunk_id = str(raw.get("chunk_id", "")).strip()
        if not source or not chunk_id:
            raise RAGContractError("retrieval hit missing required citation fields")
        hits.append(
            RetrievalHit(
                chunk_id=chunk_id,
                score=float(raw.get("score", 0.0)),
                source=source,
                page=raw.get("page") if isinstance(raw.get("page"), int) else None,
                section=raw.get("section") if isinstance(raw.get("section"), str) else None,
                content=str(raw.get("content", "")),
                metadata=raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
            )
        )

    payload = build_cited_response(
        base_reply=state.get("reply", ""),
        hits=hits,
        knowledge_required=bool(hits),
    )
    rag_debug = state.get("rag_debug", {})
    if not isinstance(rag_debug, dict):
        rag_debug = {}
    if bool(state.get("rag_debug_enabled", False)):
        rag_debug["citations"] = payload.citations
        rag_debug["noEvidence"] = bool(payload.no_evidence)
    debug_payload = state.get("debug", {})
    if not isinstance(debug_payload, dict):
        debug_payload = {}
    if rag_debug:
        debug_payload["rag"] = rag_debug
    result: dict[str, Any] = {
        "reply": payload.reply,
        "rag_citations": payload.citations,
        "rag_no_evidence": bool(state.get("rag_no_evidence", False) or payload.no_evidence),
        "rag_debug": rag_debug,
        "debug": debug_payload,
    }
    graph_data = state.get("graph_data", {})
    if isinstance(graph_data, dict):
        result["graph_data"] = graph_data
    graph_meta = state.get("graph_meta", {})
    if isinstance(graph_meta, dict):
        result["graph_meta"] = graph_meta
    return result
