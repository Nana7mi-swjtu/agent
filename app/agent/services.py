from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock
from typing import Any

from flask import current_app
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from .graph import build_graph
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
    if str(entity or "").strip() or str(graph_intent or "").strip():
        return True
    lowered = str(user_message or "").strip().lower()
    return "知识图谱" in lowered or "knowledge graph" in lowered


def _direct_kg_payload(
    *,
    user_message: str,
    user_id: int,
    workspace_id: str,
    entity: str,
    graph_intent: str,
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

    raw = kg_tool.invoke(query=query_text, entity=entity, intent=graph_intent)
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


def _planner_summary(output: dict[str, Any]) -> str:
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
        details = {
            "replyLength": len(str(output.get("reply", ""))),
            "usedSearch": bool(output.get("search_completed", False)),
            "usedMcp": bool(output.get("mcp_completed", False)),
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
    rag_debug_enabled: bool = False,
    entity: str = "",
    intent: str = "",
    agent_trace_enabled: bool = False,
    agent_trace_debug_details_enabled: bool = False,
) -> dict[str, Any]:
    entity_text = str(entity or "").strip()
    graph_intent_text = str(intent or "").strip()
    if _should_run_direct_kg_query(user_message=user_message, entity=entity_text, graph_intent=graph_intent_text):
        try:
            return _direct_kg_payload(
                user_message=user_message,
                user_id=user_id,
                workspace_id=workspace_id,
                entity=entity_text,
                graph_intent=graph_intent_text,
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
            "user_message": user_message,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "intent": "",
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
            "rag_enabled": bool(current_app.config.get("RAG_ENABLED", False)),
            "web_enabled": bool(current_app.config.get("AGENT_WEBSEARCH_ENABLED", False)),
            "mcp_enabled": bool(current_app.config.get("AGENT_MCP_ENABLED", False)),
            "rag_debug_enabled": bool(rag_debug_enabled),
            "entity": entity_text,
            "graph_intent": graph_intent_text,
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
    payload = {"reply": reply, "citations": citations, "noEvidence": no_evidence, "debug": debug_payload}
    payload["graph"] = graph_payload
    payload["graphMeta"] = graph_meta_payload
    if trace_payload:
        payload["trace"] = trace_payload
    return payload


def generate_reply(*, role: str, system_prompt: str, user_message: str) -> str:
    payload = generate_reply_payload(role=role, system_prompt=system_prompt, user_message=user_message)
    return payload["reply"]
