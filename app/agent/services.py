from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from flask import current_app
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from .analysis_session import create_transient_analysis_session
from .graph import build_graph
from .graph.analysis_modules import (
    normalize_analysis_module_inputs,
    normalize_analysis_shared_inputs,
    normalize_enabled_analysis_modules,
)
from .tools import AgentToolContext, get_agent_tools

_runtime_lock = Lock()
_runtime: dict[str, Any] | None = None
logger = logging.getLogger(__name__)


class AgentServiceError(RuntimeError):
    pass


def _should_run_direct_kg_query(*, user_message: str, entity: str, graph_intent: str) -> bool:
    if not bool(current_app.config.get("AGENT_KNOWLEDGE_GRAPH_ENABLED", False)):
        return False
    if bool(current_app.config.get("AGENT_KNOWLEDGE_GRAPH_DIRECT_ONLY", False)):
        return True
    # entity/graph_intent are routing hints for the planner/search graph and
    # should not force direct KG execution unless direct-only mode is enabled.
    lowered = str(user_message or "").strip().lower()
    return "知识图谱" in lowered or "knowledge graph" in lowered


def _direct_kg_payload(
    *,
    user_message: str,
    user_id: int,
    workspace_id: str,
    entity: str,
    graph_intent: str,
    conversation_history: list[dict[str, str]] | None = None,
    agent_trace_enabled: bool,
    agent_trace_debug_details_enabled: bool,
) -> dict[str, Any]:
    tool_context = AgentToolContext(
        user_id=user_id,
        workspace_id=workspace_id,
        rag_debug_enabled=False,
    )
    tools = get_agent_tools(context=tool_context, categories=("knowledge_graph",))
    kg_tool = next((item for item in tools if item.name == "knowledge_graph_query"), None)
    if kg_tool is None:
        raise AgentServiceError("knowledge graph tool unavailable")

    query_text = str(user_message or "").strip()
    if not query_text:
        entity_text = str(entity or "").strip()
        intent_text = str(graph_intent or "").strip()
        query_text = f"query {entity_text} {intent_text}".strip()
    if not query_text:
        raise AgentServiceError("empty knowledge graph query")

    raw = kg_tool.invoke(query=query_text, entity=entity, intent=graph_intent, conversation_history=conversation_history)
    if not isinstance(raw, dict) or not bool(raw.get("ok", False)):
        raise AgentServiceError(str(raw.get("error", "knowledge graph query failed")) if isinstance(raw, dict) else "knowledge graph query failed")

    summary = str(raw.get("summary", "")).strip() or "知识图谱查询完成。"
    graph_payload = raw.get("graph", {})
    if not isinstance(graph_payload, dict):
        graph_payload = {}
    graph_meta_payload = raw.get("meta", {})
    if not isinstance(graph_meta_payload, dict):
        graph_meta_payload = {}

    payload: dict[str, Any] = {
        "reply": summary,
        "citations": [],
        "noEvidence": False,
        "intent": "knowledge_graph",
        "clarificationQuestion": "",
        "debug": {
            "knowledgeGraph": {
                "query": query_text,
                "status": "done",
            }
        },
        "graph": graph_payload,
        "graphMeta": graph_meta_payload,
    }
    if agent_trace_enabled:
        trace_details = None
        if agent_trace_debug_details_enabled:
            trace_details = {
                "query": query_text,
                "entity": str(entity or "").strip(),
                "graphIntent": str(graph_intent or "").strip(),
                "nodeCount": len(graph_payload.get("nodes", [])) if isinstance(graph_payload.get("nodes", []), list) else 0,
                "edgeCount": len(graph_payload.get("edges", [])) if isinstance(graph_payload.get("edges", []), list) else 0,
            }
        payload["trace"] = {
            "steps": [
                _trace_step(
                    step_id="knowledge_graph_direct",
                    step_type="tool",
                    title="Knowledge Graph Query",
                    summary="Executed knowledge graph query directly without planner routing.",
                    details=trace_details,
                )
            ]
        }
    return payload


def _trace_step(
    *,
    step_id: str,
    step_type: str,
    title: str,
    summary: str,
    status: str = "done",
    details: dict[str, Any] | None = None,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": step_id,
        "type": step_type,
        "title": title,
        "status": status,
        "summary": summary,
    }
    if details:
        payload["details"] = details
    if children:
        payload["children"] = children
    return payload


def _source_counts(evidence: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in evidence:
        if not isinstance(item, dict):
            continue
        source_type = str(item.get("source_type", "")).strip().lower()
        if not source_type:
            continue
        counts[source_type] = counts.get(source_type, 0) + 1
    return counts


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError:
        return default


def _planner_summary(output: dict[str, Any]) -> str:
    enabled_analysis_modules = output.get("enabled_analysis_modules", [])
    if isinstance(enabled_analysis_modules, list) and enabled_analysis_modules:
        if bool(output.get("needs_clarification", False)):
            return "Entered module-gated analysis intake and requested clarification."
        if bool(output.get("analysis_completed", False)):
            return "Entered module-gated analysis intake and dispatched enabled analysis modules."
        return "Entered module-gated analysis intake."
    if bool(output.get("needs_clarification", False)):
        return "Requested clarification before continuing."
    if bool(output.get("needs_search", False)) and bool(output.get("needs_mcp", False)):
        return "Delegated to Search Subagent, then continued with MCP Subagent."
    if bool(output.get("needs_search", False)):
        return "Delegated to Search Subagent."
    if bool(output.get("needs_mcp", False)):
        return "Delegated to MCP Subagent."
    return "Answered directly without delegation."


def _planner_details(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent": str(output.get("intent", "")),
        "needsSearch": bool(output.get("needs_search", False)),
        "needsMcp": bool(output.get("needs_mcp", False)),
        "needsClarification": bool(output.get("needs_clarification", False)),
        "enabledAnalysisModules": list(output.get("enabled_analysis_modules", []))
        if isinstance(output.get("enabled_analysis_modules"), list)
        else [],
        "missingFields": list(output.get("missing_fields", []))
        if isinstance(output.get("missing_fields"), list)
        else [],
    }


def _search_children(output: dict[str, Any], *, include_details: bool) -> list[dict[str, Any]]:
    search_result = output.get("search_result", {})
    if not isinstance(search_result, dict):
        search_result = {}
    evidence = search_result.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = []
    counts = _source_counts(evidence)
    children: list[dict[str, Any]] = []

    kg_count = counts.get("knowledge_graph", 0)
    graph_meta = output.get("graph_meta", {})
    if not isinstance(graph_meta, dict):
        graph_meta = {}
    graph_payload = output.get("graph_data", {})
    if not isinstance(graph_payload, dict):
        graph_payload = {}
    kg_used = kg_count > 0 or bool(graph_meta) or bool(graph_payload)
    if kg_used:
        child_details = (
            {
                "evidenceCount": kg_count,
                "contextSize": _safe_int(graph_meta.get("contextSize", 0)),
                "nodeCount": len(graph_payload.get("nodes", [])) if isinstance(graph_payload.get("nodes"), list) else 0,
                "edgeCount": len(graph_payload.get("edges", [])) if isinstance(graph_payload.get("edges"), list) else 0,
            }
            if include_details
            else None
        )
        children.append(
            _trace_step(
                step_id="kg_lookup",
                step_type="retrieval",
                title="Knowledge Graph Lookup",
                summary=f"Collected {kg_count or 0} knowledge graph evidence item(s).",
                details=child_details,
            )
        )

    rag_count = counts.get("rag", 0)
    if rag_count or bool(output.get("rag_chunks")):
        child_details = (
            {
                "evidenceCount": rag_count,
                "chunkCount": len(output.get("rag_chunks", [])) if isinstance(output.get("rag_chunks"), list) else 0,
            }
            if include_details
            else None
        )
        children.append(
            _trace_step(
                step_id="rag_lookup",
                step_type="retrieval",
                title="RAG Lookup",
                summary=f"Collected {rag_count or 0} workspace evidence item(s).",
                details=child_details,
            )
        )

    web_count = counts.get("web", 0)
    web_result = search_result.get("web_result", {})
    web_used = web_count > 0 or (isinstance(web_result, dict) and bool(web_result))
    if web_used:
        child_details = (
            {
                "evidenceCount": web_count,
                "resultCount": len(web_result.get("results", []))
                if isinstance(web_result, dict) and isinstance(web_result.get("results"), list)
                else 0,
            }
            if include_details
            else None
        )
        children.append(
            _trace_step(
                step_id="web_lookup",
                step_type="retrieval",
                title="Web Lookup",
                summary=f"Collected {web_count or 0} public evidence item(s).",
                details=child_details,
            )
        )

    if bool(search_result):
        child_details = (
            {
                "evidenceCount": len(evidence),
                "sufficient": bool(search_result.get("sufficient", False)),
            }
            if include_details
            else None
        )
        children.append(
            _trace_step(
                step_id="merge_results",
                step_type="merge",
                title="Merge Results",
                summary=f"Normalized {len(evidence)} evidence item(s) for composition.",
                status=str(search_result.get("status", "done") or "done"),
                details=child_details,
            )
        )
    return children


def _search_step(output: dict[str, Any], *, include_details: bool) -> dict[str, Any]:
    search_result = output.get("search_result", {})
    if not isinstance(search_result, dict):
        search_result = {}
    evidence = search_result.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = []
    counts = _source_counts(evidence)
    details = None
    if include_details:
        details = {
            "strategy": str(search_result.get("strategy", "")),
            "status": str(search_result.get("status", "")),
            "sufficient": bool(search_result.get("sufficient", False)),
            "evidenceCount": len(evidence),
            "sourceCounts": counts,
            "followUpQuestion": str(search_result.get("follow_up_question", "")),
        }
    return _trace_step(
        step_id="search_subagent",
        step_type="subagent",
        title="Search Subagent",
        summary=str(search_result.get("summary", "")).strip() or "Completed evidence gathering.",
        status=str(search_result.get("status", "done") or "done"),
        details=details,
        children=_search_children(output, include_details=include_details),
    )


def _mcp_step(output: dict[str, Any], *, include_details: bool) -> dict[str, Any]:
    mcp_result = output.get("mcp_result", {})
    if not isinstance(mcp_result, dict):
        mcp_result = {}
    artifacts = mcp_result.get("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
    details = None
    if include_details:
        details = {
            "status": str(mcp_result.get("status", "")),
            "artifactKeys": sorted(artifacts.keys()),
            "followUpQuestion": str(mcp_result.get("follow_up_question", "")),
        }
    return _trace_step(
        step_id="mcp_subagent",
        step_type="subagent",
        title="MCP Subagent",
        summary=str(mcp_result.get("summary", "")).strip() or "Completed MCP execution.",
        status=str(mcp_result.get("status", "done") or "done"),
        details=details,
    )


def _compose_step(output: dict[str, Any], *, include_details: bool) -> dict[str, Any]:
    details = None
    if include_details:
        conversation_history = output.get("conversation_history", [])
        if not isinstance(conversation_history, list):
            conversation_history = []
        enabled_analysis_modules = output.get("enabled_analysis_modules", [])
        analysis_results = output.get("analysis_results", {})
        details = {
            "replyLength": len(str(output.get("reply", ""))),
            "usedSearch": bool(output.get("search_completed", False)),
            "usedMcp": bool(output.get("mcp_completed", False)),
            "usedAnalysis": bool(enabled_analysis_modules),
            "analysisModuleCount": len(enabled_analysis_modules) if isinstance(enabled_analysis_modules, list) else 0,
            "analysisCompleted": bool(output.get("analysis_completed", False)),
            "analysisResultCount": len(analysis_results) if isinstance(analysis_results, dict) else 0,
            "memoryUsed": bool(conversation_history),
            "memoryMessageCount": len(conversation_history),
            "conversationContextPresent": bool(str(output.get("conversation_context", "")).strip()),
        }
    return _trace_step(
        step_id="compose_answer",
        step_type="compose",
        title="Compose Answer",
        summary="Generated the final assistant reply.",
        details=details,
    )


def _citation_step(output: dict[str, Any], *, include_details: bool) -> dict[str, Any]:
    citations = output.get("rag_citations", [])
    if not isinstance(citations, list):
        citations = []
    no_evidence = bool(output.get("rag_no_evidence", False))
    if no_evidence and not citations:
        summary = "No citations attached because supporting evidence was not found."
    elif citations:
        summary = f"Attached {len(citations)} citation(s) to the reply."
    else:
        summary = "No citations were attached."
    details = None
    if include_details:
        details = {
            "citationCount": len(citations),
            "noEvidence": no_evidence,
        }
    return _trace_step(
        step_id="citations",
        step_type="citations",
        title="Citations",
        summary=summary,
        details=details,
    )


def _clarify_step(output: dict[str, Any], *, include_details: bool) -> dict[str, Any]:
    details = None
    if include_details:
        details = {
            "question": str(output.get("clarification_question", "")),
        }
    return _trace_step(
        step_id="clarify",
        step_type="clarify",
        title="Clarify",
        summary="Asked the user for more information before continuing.",
        details=details,
    )


def _analysis_intake_step(output: dict[str, Any], *, include_details: bool) -> dict[str, Any]:
    debug_payload = output.get("debug", {})
    if not isinstance(debug_payload, dict):
        debug_payload = {}
    intake_payload = debug_payload.get("analysisIntake", {})
    if not isinstance(intake_payload, dict):
        intake_payload = {}
    missing_fields = output.get("analysis_missing_fields", [])
    if not isinstance(missing_fields, list):
        missing_fields = []
    summary = "Collected required analysis inputs for enabled modules."
    if missing_fields:
        summary = f"Identified {len(missing_fields)} missing analysis input(s) before dispatch."
    details = None
    if include_details:
        details = {
            "enabledModules": list(output.get("enabled_analysis_modules", []))
            if isinstance(output.get("enabled_analysis_modules"), list)
            else [],
            "unsupportedModules": list(output.get("analysis_unsupported_modules", []))
            if isinstance(output.get("analysis_unsupported_modules"), list)
            else [],
            "missingFields": missing_fields,
            "sharedInputs": output.get("analysis_shared_inputs", {})
            if isinstance(output.get("analysis_shared_inputs"), dict)
            else {},
            "intake": intake_payload,
        }
    return _trace_step(
        step_id="analysis_intake",
        step_type="intake",
        title="Analysis Intake",
        summary=summary,
        details=details,
    )


def _analysis_modules_children(output: dict[str, Any], *, include_details: bool) -> list[dict[str, Any]]:
    analysis_results = output.get("analysis_results", {})
    if not isinstance(analysis_results, dict):
        return []
    children: list[dict[str, Any]] = []
    for module_id, payload in analysis_results.items():
        if not isinstance(payload, dict):
            continue
        child_details = None
        if include_details:
            child_details = {
                "runId": str(payload.get("runId", "")),
                "limitationCount": len(payload.get("limitations", []))
                if isinstance(payload.get("limitations"), list)
                else 0,
                "hasDocumentHandoff": isinstance(payload.get("documentHandoff"), dict) and bool(payload.get("documentHandoff")),
            }
        children.append(
            _trace_step(
                step_id=f"analysis_module:{module_id}",
                step_type="module",
                title=str(payload.get("displayName", module_id) or module_id),
                summary=str(payload.get("summary", "")).strip() or "Completed analysis module execution.",
                status=str(payload.get("status", "done") or "done"),
                details=child_details,
            )
        )
    return children


def _analysis_modules_step(output: dict[str, Any], *, include_details: bool) -> dict[str, Any]:
    analysis_results = output.get("analysis_results", {})
    if not isinstance(analysis_results, dict):
        analysis_results = {}
    debug_payload = output.get("debug", {})
    if not isinstance(debug_payload, dict):
        debug_payload = {}
    module_debug = debug_payload.get("analysisModules", {})
    if not isinstance(module_debug, dict):
        module_debug = {}
    statuses = [str(item.get("status", "")).strip() for item in analysis_results.values() if isinstance(item, dict)]
    overall_status = "done"
    if any(status == "failed" for status in statuses):
        overall_status = "failed"
    elif any(status == "partial" for status in statuses):
        overall_status = "partial"
    summary = f"Executed {len(analysis_results)} analysis module(s)."
    details = None
    if include_details:
        details = {
            "moduleCount": len(analysis_results),
            "statuses": {
                module_id: str(payload.get("status", "")).strip()
                for module_id, payload in analysis_results.items()
                if isinstance(payload, dict)
            },
            "runIds": {
                module_id: str(payload.get("runId", "")).strip()
                for module_id, payload in analysis_results.items()
                if isinstance(payload, dict) and str(payload.get("runId", "")).strip()
            },
            "bundleLimitations": list(output.get("analysis_handoff_bundle", {}).get("limitations", []))
            if isinstance(output.get("analysis_handoff_bundle"), dict)
            and isinstance(output.get("analysis_handoff_bundle", {}).get("limitations", []), list)
            else [],
            "dispatch": module_debug,
        }
    return _trace_step(
        step_id="analysis_modules",
        step_type="dispatch",
        title="Analysis Modules",
        summary=summary,
        status=overall_status,
        details=details,
        children=_analysis_modules_children(output, include_details=include_details),
    )


def _build_trace_payload(output: dict[str, Any], *, include_details: bool) -> dict[str, Any]:
    steps = [
        _trace_step(
            step_id="planner",
            step_type="planner",
            title="Planner",
            summary=_planner_summary(output),
            details=_planner_details(output) if include_details else None,
        )
    ]
    enabled_analysis_modules = output.get("enabled_analysis_modules", [])
    if isinstance(enabled_analysis_modules, list) and enabled_analysis_modules:
        steps.append(_analysis_intake_step(output, include_details=include_details))
        if bool(output.get("analysis_completed", False)) or bool(output.get("analysis_results")):
            steps.append(_analysis_modules_step(output, include_details=include_details))
        if bool(output.get("needs_clarification", False)):
            steps.append(_clarify_step(output, include_details=include_details))
            return {"steps": steps}
        steps.append(_compose_step(output, include_details=include_details))
        steps.append(_citation_step(output, include_details=include_details))
        return {"steps": steps}
    if bool(output.get("search_completed", False)):
        steps.append(_search_step(output, include_details=include_details))
    if bool(output.get("mcp_completed", False)):
        steps.append(_mcp_step(output, include_details=include_details))
    if bool(output.get("needs_clarification", False)):
        steps.append(_clarify_step(output, include_details=include_details))
        return {"steps": steps}
    steps.append(_compose_step(output, include_details=include_details))
    steps.append(_citation_step(output, include_details=include_details))
    return {"steps": steps}


def _canonical_web_url(value: str) -> str:
    raw = str(value).strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw
    if not parsed.scheme or not parsed.netloc:
        return raw
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def _group_rag_sources(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        source = str(citation.get("source", "")).strip()
        chunk_id = str(citation.get("chunk_id", "")).strip()
        if not source:
            continue
        entry = grouped.setdefault(
            source,
            {
                "id": f"rag:{source}",
                "kind": "rag",
                "title": source,
                "source": source,
                "pages": [],
                "sections": [],
                "chunkIds": [],
                "citationCount": 0,
            },
        )
        page = citation.get("page")
        if isinstance(page, int) and page not in entry["pages"]:
            entry["pages"].append(page)
        section = str(citation.get("section", "")).strip()
        if section and section not in entry["sections"]:
            entry["sections"].append(section)
        if chunk_id and chunk_id not in entry["chunkIds"]:
            entry["chunkIds"].append(chunk_id)
        entry["citationCount"] += 1

    for entry in grouped.values():
        entry["pages"].sort()
        entry["sections"].sort()
    return sorted(grouped.values(), key=lambda item: str(item.get("title", "")).lower())


def _group_web_sources(search_result: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = search_result.get("evidence", [])
    if not isinstance(evidence, list):
        return []
    grouped: dict[str, dict[str, Any]] = {}
    for item in evidence:
        if not isinstance(item, dict):
            continue
        if str(item.get("source_type", "")).strip().lower() != "web":
            continue
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        canonical_url = _canonical_web_url(str(metadata.get("url") or item.get("source") or ""))
        if not canonical_url:
            continue
        title = str(item.get("title", "")).strip() or canonical_url
        parsed = urlsplit(canonical_url)
        entry = grouped.setdefault(
            canonical_url,
            {
                "id": f"web:{canonical_url}",
                "kind": "web",
                "title": title,
                "source": canonical_url,
                "url": canonical_url,
                "domain": parsed.netloc.lower(),
            },
        )
        if title and entry["title"] == canonical_url:
            entry["title"] = title
    return sorted(grouped.values(), key=lambda item: str(item.get("title", "")).lower())


def _build_grouped_sources(output: dict[str, Any], citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    search_result = output.get("search_result", {})
    if not isinstance(search_result, dict):
        search_result = {}
    graph_meta = output.get("graph_meta", {})
    if not isinstance(graph_meta, dict):
        graph_meta = {}
    grouped: list[dict[str, Any]] = []
    graph_payload = output.get("graph_data", {})
    if isinstance(graph_payload, dict) and graph_payload:
        grouped.append(
            {
                "id": "kg:knowledge_graph",
                "kind": "knowledge_graph",
                "title": "Knowledge Graph",
                "source": str(graph_meta.get("source", "knowledge_graph") or "knowledge_graph"),
                "contextSize": _safe_int(graph_meta.get("contextSize", 0)),
            }
        )
    return grouped + _group_rag_sources(citations) + _group_web_sources(search_result)


def _load_chat_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent / "prompts" / "chat.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    logger.warning("Agent prompt file missing, using built-in fallback prompt")
    return (
        "You are a helpful assistant.\n"
        "Role: {role}\n"
        "System prompt: {system_prompt}\n"
    )


def _agent_llm_config(agent_key: str) -> dict[str, Any]:
    normalized = agent_key.strip().upper()
    provider = str(
        current_app.config.get(f"AGENT_{normalized}_AI_PROVIDER") or current_app.config.get("AI_PROVIDER", "")
    ).strip().lower()
    model = str(
        current_app.config.get(f"AGENT_{normalized}_AI_MODEL") or current_app.config.get("AI_MODEL", "")
    ).strip()
    api_key = str(
        current_app.config.get(f"AGENT_{normalized}_AI_API_KEY") or current_app.config.get("AI_API_KEY", "")
    ).strip()
    base_url = str(
        current_app.config.get(f"AGENT_{normalized}_AI_BASE_URL") or current_app.config.get("AI_BASE_URL", "")
    ).strip()
    timeout = int(
        current_app.config.get(f"AGENT_{normalized}_AI_TIMEOUT_SECONDS")
        or current_app.config.get("AI_TIMEOUT_SECONDS", 30)
    )
    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "timeout": timeout,
    }




def _create_llm(agent_key: str) -> Any:
    config = _agent_llm_config(agent_key)
    if not config["model"] or not config["api_key"]:
        logger.error(
            "Missing AI runtime config",
            extra={
                "agent_key": agent_key,
                "provider": config["provider"],
                "model_set": bool(config["model"]),
                "api_key_set": bool(config["api_key"]),
            },
        )
        raise AgentServiceError("missing agent runtime configuration")
    return ChatOpenAI(
        model=config["model"],
        api_key=SecretStr(config["api_key"]),
        base_url=config["base_url"] or None,
        timeout=config["timeout"],
    )


def _normalize_conversation_history(conversation_history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if not isinstance(conversation_history, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in conversation_history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if not role or not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized




def _build_runtime() -> dict[str, Any]:
    try:
        main_llm = _create_llm("MAIN")
        search_llm = _create_llm("SEARCH")
        mcp_llm = _create_llm("MCP")
        graph = build_graph()
        prompt_template = _load_chat_prompt()
    except Exception as exc:
        logger.exception("Failed to initialize agent runtime")
        raise AgentServiceError("runtime initialization failed") from exc

    return {
        "main_llm": main_llm,
        "search_llm": search_llm,
        "mcp_llm": mcp_llm,
        "graph": graph,
        "prompt_template": prompt_template,
    }


def _get_runtime() -> dict[str, Any]:
    global _runtime
    if _runtime is not None:
        return _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = _build_runtime()
    return _runtime


def reset_runtime_for_tests() -> None:
    global _runtime
    with _runtime_lock:
        _runtime = None


def generate_reply_payload(
    *,
    role: str,
    system_prompt: str,
    user_message: str,
    user_id: int = 0,
    workspace_id: str = "default",
    conversation_history: list[dict[str, str]] | None = None,
    conversation_context: str = "",
    rag_debug_enabled: bool = False,
    entity: str = "",
    intent: str = "",
    enabled_analysis_modules: list[str] | None = None,
    analysis_shared_inputs: dict[str, Any] | None = None,
    analysis_module_inputs: dict[str, dict[str, Any]] | None = None,
    analysis_session_state: dict[str, Any] | None = None,
    agent_trace_enabled: bool = False,
    agent_trace_debug_details_enabled: bool = False,
) -> dict[str, Any]:
    entity_text = str(entity or "").strip()
    graph_intent_text = str(intent or "").strip()
    effective_user_message = str(user_message or "").strip()
    if not effective_user_message:
        effective_user_message = f"{entity_text} {graph_intent_text}".strip()
    normalized_enabled_analysis_modules = normalize_enabled_analysis_modules(enabled_analysis_modules)
    normalized_analysis_session_state = (
        dict(analysis_session_state)
        if isinstance(analysis_session_state, dict)
        else {}
    )
    if not normalized_enabled_analysis_modules and isinstance(normalized_analysis_session_state.get("enabledModules"), list):
        normalized_enabled_analysis_modules = [
            str(item).strip()
            for item in normalized_analysis_session_state.get("enabledModules", [])
            if str(item).strip()
        ]
    fallback_report_goal = ""
    if not normalized_enabled_analysis_modules:
        fallback_report_goal = effective_user_message
    normalized_analysis_shared_inputs = normalize_analysis_shared_inputs(
        analysis_shared_inputs,
        fallback_enterprise=entity_text,
        fallback_report_goal=fallback_report_goal,
    )
    normalized_analysis_module_inputs = normalize_analysis_module_inputs(analysis_module_inputs)
    if not normalized_analysis_session_state and normalized_enabled_analysis_modules:
        normalized_analysis_session_state = create_transient_analysis_session(
            enabled_modules=normalized_enabled_analysis_modules
        )
    normalized_history = _normalize_conversation_history(conversation_history)
    normalized_context = str(conversation_context or "").strip()
    if not normalized_enabled_analysis_modules and _should_run_direct_kg_query(
        user_message=effective_user_message,
        entity=entity_text,
        graph_intent=graph_intent_text,
    ):
        try:
            return _direct_kg_payload(
                user_message=effective_user_message,
                user_id=user_id,
                workspace_id=workspace_id,
                entity=entity_text,
                graph_intent=graph_intent_text,
                conversation_history=normalized_history,
                agent_trace_enabled=agent_trace_enabled,
                agent_trace_debug_details_enabled=agent_trace_debug_details_enabled,
            )
        except AgentServiceError:
            raise
        except Exception as exc:
            logger.exception("Failed to execute direct knowledge graph query")
            raise AgentServiceError("knowledge graph direct query failed") from exc

    try:
        runtime = _get_runtime()
        state = {
            "main_llm": runtime["main_llm"],
            "search_llm": runtime["search_llm"],
            "mcp_llm": runtime["mcp_llm"],
            "prompt_template": runtime["prompt_template"],
            "role": role,
            "system_prompt": system_prompt,
            "user_message": effective_user_message,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "entity": entity_text,
            "graph_intent": graph_intent_text,
            "conversation_history": normalized_history,
            "conversation_context": normalized_context,
            "intent": "",
            "enabled_analysis_modules": normalized_enabled_analysis_modules,
            "analysis_shared_inputs": normalized_analysis_shared_inputs,
            "analysis_module_inputs": normalized_analysis_module_inputs,
            "analysis_session": normalized_analysis_session_state,
            "analysis_missing_fields": [],
            "analysis_results": {},
            "analysis_handoff_bundle": {},
            "analysis_completed": False,
            "analysis_unsupported_modules": [],
            "needs_search": False,
            "needs_mcp": False,
            "needs_clarification": False,
            "clarification_question": "",
            "missing_fields": [],
            "search_request": {},
            "search_result": {},
            "mcp_request": {},
            "mcp_result": {},
            "search_completed": False,
            "mcp_completed": False,
            "kg_enabled": bool(current_app.config.get("AGENT_KNOWLEDGE_GRAPH_ENABLED", False)),
            "rag_enabled": bool(current_app.config.get("RAG_ENABLED", False)),
            "web_enabled": bool(current_app.config.get("AGENT_WEBSEARCH_ENABLED", False)),
            "mcp_enabled": bool(current_app.config.get("AGENT_MCP_ENABLED", False)),
            "rag_debug_enabled": bool(rag_debug_enabled),
            "rag_decision": "skip",
            "rag_chunks": [],
            "rag_citations": [],
            "rag_no_evidence": False,
            "rag_debug": {},
            "graph_data": {},
            "graph_meta": {},
            "debug": {},
            "reply": "",
        }
        output = runtime["graph"].invoke(state)
        reply = str(output.get("reply", "")).strip()
        citations = output.get("rag_citations", [])
        if not isinstance(citations, list):
            citations = []
        sources = _build_grouped_sources(output, citations)
        no_evidence = bool(output.get("rag_no_evidence", False))
        debug_payload = output.get("debug", {})
        if not isinstance(debug_payload, dict):
            debug_payload = {}
        graph_payload = output.get("graph_data", {})
        if not isinstance(graph_payload, dict):
            graph_payload = {}
        graph_meta_payload = output.get("graph_meta", {})
        if not isinstance(graph_meta_payload, dict):
            graph_meta_payload = {}
        analysis_results_payload = output.get("analysis_results", {})
        if not isinstance(analysis_results_payload, dict):
            analysis_results_payload = {}
        analysis_handoff_bundle_payload = output.get("analysis_handoff_bundle", {})
        if not isinstance(analysis_handoff_bundle_payload, dict):
            analysis_handoff_bundle_payload = {}
        analysis_session_payload = output.get("analysis_session", {})
        if not isinstance(analysis_session_payload, dict):
            analysis_session_payload = {}
        trace_payload = (
            _build_trace_payload(output, include_details=bool(agent_trace_debug_details_enabled))
            if agent_trace_enabled
            else None
        )
    except AgentServiceError:
        raise
    except Exception as exc:
        logger.exception("Failed to generate agent reply")
        raise AgentServiceError("runtime invocation failed") from exc

    if not reply:
        raise AgentServiceError("empty agent reply")
    payload = {
        "reply": reply,
        "citations": citations,
        "sources": sources,
        "noEvidence": no_evidence,
        "intent": str(output.get("intent", "")),
        "clarificationQuestion": str(output.get("clarification_question", "")),
        "debug": debug_payload,
        "graph": graph_payload,
        "graphMeta": graph_meta_payload,
    }
    if analysis_results_payload:
        payload["analysisResults"] = analysis_results_payload
    if analysis_handoff_bundle_payload:
        payload["analysisHandoffBundle"] = analysis_handoff_bundle_payload
    if analysis_session_payload:
        payload["analysisSession"] = analysis_session_payload
    if trace_payload:
        payload["trace"] = trace_payload
    return payload


def generate_reply(*, role: str, system_prompt: str, user_message: str) -> str:
    payload = generate_reply_payload(role=role, system_prompt=system_prompt, user_message=user_message)
    return payload["reply"]
