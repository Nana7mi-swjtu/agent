from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ...rag.errors import RAGContractError
from ...rag.schemas import RetrievalHit
from ...rag.service import build_cited_response
from .analysis_modules import (
    AnalysisModuleContract,
    build_analysis_handoff_bundle,
    get_analysis_module_registry,
    normalize_analysis_module_output,
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


def _has_analysis_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return bool(value)
    return value is not None


def _analysis_missing_field_id(item: dict[str, Any]) -> str:
    scope = str(item.get("scope", "")).strip()
    module_id = str(item.get("moduleId", "")).strip()
    field_name = str(item.get("field", "")).strip()
    if scope == "module" and module_id:
        return f"analysis.{module_id}.{field_name}"
    return f"analysis.shared.{field_name}"


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
            header = f"[{index}] module={module_id} name={display_name} status={status}"
            if run_id:
                header += f" runId={run_id}"
            lines.append(header)
            if summary:
                lines.append(summary)
    limitations = bundle.get("limitations", [])
    if isinstance(limitations, list) and limitations:
        lines.append("限制说明：" + "；".join(str(item).strip() for item in limitations if str(item).strip()))
    return "\n".join(lines)


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


def analysis_intake_node(state: AgentState):
    enabled_modules = _enabled_analysis_modules(state)
    shared_inputs = _analysis_shared_inputs(state)
    module_inputs = _analysis_module_inputs(state)
    contracts, unsupported_modules = _analysis_contracts(enabled_modules)

    shared_missing: list[dict[str, Any]] = []
    seen_shared_fields: set[str] = set()
    for contract in contracts:
        for field in contract.shared_fields:
            if not field.required or field.field in seen_shared_fields:
                continue
            seen_shared_fields.add(field.field)
            if not _has_analysis_value(shared_inputs.get(field.field)):
                shared_missing.append(
                    {
                        "scope": "shared",
                        "field": field.field,
                        "label": field.label,
                    }
                )

    module_missing: list[dict[str, Any]] = []
    if not shared_missing:
        for contract in contracts:
            current_inputs = module_inputs.get(contract.module_id, {})
            for field in contract.module_fields:
                if not field.required:
                    continue
                if not _has_analysis_value(current_inputs.get(field.field)):
                    module_missing.append(
                        {
                            "scope": "module",
                            "moduleId": contract.module_id,
                            "moduleName": contract.display_name,
                            "field": field.field,
                            "label": field.label,
                        }
                    )

    missing_fields = shared_missing or module_missing
    clarification_question = ""
    if shared_missing:
        clarification_question = _analysis_shared_question(shared_missing)
    elif module_missing:
        clarification_question = _analysis_module_question(module_missing)

    debug_payload = {
        "enabledModules": enabled_modules,
        "supportedModules": [contract.module_id for contract in contracts],
        "unsupportedModules": unsupported_modules,
        "missingSharedFields": [item["field"] for item in shared_missing],
        "missingModuleFields": {
            contract.module_id: [
                item["field"]
                for item in module_missing
                if str(item.get("moduleId", "")).strip() == contract.module_id
            ]
            for contract in contracts
            if any(str(item.get("moduleId", "")).strip() == contract.module_id for item in module_missing)
        },
        "sharedInputsReady": not bool(shared_missing),
    }
    return {
        "needs_clarification": bool(missing_fields),
        "clarification_question": clarification_question,
        "missing_fields": [_analysis_missing_field_id(item) for item in missing_fields],
        "analysis_missing_fields": missing_fields,
        "analysis_unsupported_modules": unsupported_modules,
        "analysis_completed": False,
        "debug": {
            **(state.get("debug", {}) if isinstance(state.get("debug"), dict) else {}),
            "analysisIntake": debug_payload,
        },
    }


def analysis_modules_node(state: AgentState):
    enabled_modules = _enabled_analysis_modules(state)
    shared_inputs = _analysis_shared_inputs(state)
    module_inputs = _analysis_module_inputs(state)
    contracts, unsupported_modules = _analysis_contracts(enabled_modules)
    context = {
        "conversationContext": _conversation_context(state),
        "userMessage": str(state.get("user_message", "")).strip(),
    }
    results: dict[str, dict[str, Any]] = {}
    needs_clarification = False
    clarification_question = ""

    for contract in contracts:
        runtime_input = contract.build_input(shared_inputs, module_inputs.get(contract.module_id, {}), context)
        normalized_result = normalize_analysis_module_output(contract, contract.run(runtime_input))
        results[contract.module_id] = normalized_result
        if normalized_result.get("status") == "need_input" and not clarification_question:
            needs_clarification = True
            clarification_question = _analysis_need_input_question(normalized_result, contract)

    bundle = build_analysis_handoff_bundle(
        enabled_modules=enabled_modules,
        shared_inputs=shared_inputs,
        module_results=results,
        unsupported_modules=unsupported_modules,
    )
    debug_payload = {
        "enabledModules": enabled_modules,
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
    return {
        "analysis_results": results,
        "analysis_handoff_bundle": bundle,
        "analysis_completed": not needs_clarification,
        "analysis_unsupported_modules": unsupported_modules,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "missing_fields": ["analysis.modules"] if needs_clarification else [],
        "debug": {
            **(state.get("debug", {}) if isinstance(state.get("debug"), dict) else {}),
            "analysisModules": debug_payload,
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
