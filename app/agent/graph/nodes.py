from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ...rag.errors import RAGContractError
from ...rag.schemas import RetrievalHit
from ...rag.service import build_cited_response
from .mcp import build_mcp_graph
from .search import build_search_graph
from .state import AgentState

_search_graph = build_search_graph()
_mcp_graph = build_mcp_graph()

_KNOWLEDGE_HINTS = (
    "根据",
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

_MCP_HINTS = (
    "mcp",
    "server",
    "列出mcp工具",
    "列出工具",
    "list tools",
)


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


def _planner_prefers_search(message: str, *, rag_enabled: bool, web_enabled: bool) -> bool:
    lowered = message.lower()
    if any(token in lowered for token in _KNOWLEDGE_HINTS):
        return bool(rag_enabled or web_enabled)
    return False


def _planner_prefers_mcp(message: str, *, mcp_enabled: bool) -> bool:
    lowered = message.lower()
    return bool(mcp_enabled and any(token in lowered for token in _MCP_HINTS))


def _search_strategy(message: str, *, rag_enabled: bool, web_enabled: bool) -> str:
    lowered = message.lower()
    freshness = any(token in lowered for token in ("最新", "news", "today", "recent", "监管新闻", "web", "联网"))
    if freshness and rag_enabled and web_enabled:
        return "hybrid"
    if freshness and web_enabled:
        return "public_only"
    if rag_enabled:
        return "private_first"
    if web_enabled:
        return "public_only"
    return "private_only"


def plan_route_node(state: AgentState):
    user_message = str(state.get("user_message", "")).strip()
    rag_enabled = bool(state.get("rag_enabled", False))
    web_enabled = bool(state.get("web_enabled", False))
    mcp_enabled = bool(state.get("mcp_enabled", False))

    if not user_message:
        return {
            "intent": "clarify",
            "needs_search": False,
            "needs_mcp": False,
            "needs_clarification": True,
            "clarification_question": "请先提供你的问题或任务目标。",
            "missing_fields": ["user_message"],
        }

    needs_search = _planner_prefers_search(user_message, rag_enabled=rag_enabled, web_enabled=web_enabled)
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
            needs_search = bool(response.needs_search) and bool(rag_enabled or web_enabled)
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


def search_subagent_node(state: AgentState):
    request = state.get("search_request", {})
    if not isinstance(request, dict):
        request = {}

    result = _search_graph.invoke(
        {
            "llm": state.get("search_llm"),
            "query": str(request.get("query", state.get("user_message", ""))).strip(),
            "user_id": state["user_id"],
            "workspace_id": state["workspace_id"],
            "rag_enabled": bool(state.get("rag_enabled", False)),
            "rag_debug_enabled": bool(state.get("rag_debug_enabled", False)),
            "preferred_strategy": str(request.get("preferred_strategy", "")),
            "use_rag": False,
            "use_web": False,
            "rag_result": {},
            "web_result": {},
            "evidence": [],
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
    return system_content


def compose_answer_node(state: AgentState):
    llm = state["main_llm"]
    system_content = _build_system_content(state)
    messages: list[Any] = [
        SystemMessage(content=system_content),
        HumanMessage(content=state["user_message"]),
    ]
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
    return {
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
