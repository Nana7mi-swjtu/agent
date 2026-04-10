from __future__ import annotations

import json
from typing import Any

from flask import current_app
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from ..tools import AgentToolContext, get_agent_tools
from ...rag.errors import RAGContractError
from ...rag.service import build_cited_response
from .state import AgentState


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
)

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
    intent = str(state.get("intent", "") or "").strip()
    user_message = str(state.get("user_message", "") or "").strip()
    if entity and intent:
        return f"查询{entity}的{intent}"
    if entity:
        return f"查询{entity}相关知识图谱"
    return user_message


def decide_rag_node(state: AgentState):
    message = state["user_message"].lower()
    if not state.get("rag_enabled", False):
        return {"rag_decision": "skip"}
    decision = "retrieve" if any(token in message for token in _KNOWLEDGE_HINTS) else "skip"
    return {"rag_decision": decision}


def retrieve_node(state: AgentState):
    tool_context = AgentToolContext(
        user_id=state["user_id"],
        workspace_id=state["workspace_id"],
        rag_debug_enabled=bool(state.get("rag_debug_enabled", False)),
    )
    tools = get_agent_tools(
        context=tool_context,
    )
    rag_tool = next((item for item in tools if item.name == "rag_search"), None)
    if rag_tool is None:
        return {"rag_chunks": [], "rag_debug": {}}

    response = rag_tool.invoke(
        query=state["user_message"],
        top_k=5,
        filters={},
        include_debug=bool(state.get("rag_debug_enabled", False)),
    )
    if not response.get("ok", True):
        return {"rag_chunks": [], "rag_debug": {}}
    payload = {"rag_chunks": response.get("chunks", [])}
    if bool(state.get("rag_debug_enabled", False)):
        payload["rag_debug"] = response.get("debug", {}) if isinstance(response.get("debug"), dict) else {}
    return payload


def rerank_node(state: AgentState):
    chunks = list(state.get("rag_chunks", []))
    chunks.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    trimmed = chunks[:5]
    payload = {"rag_chunks": trimmed}
    if bool(state.get("rag_debug_enabled", False)):
        rag_debug = state.get("rag_debug", {})
        if not isinstance(rag_debug, dict):
            rag_debug = {}
        rerank = rag_debug.get("rerank", {})
        if not isinstance(rerank, dict):
            rerank = {}
        if "afterRuntimeSort" not in rerank:
            rerank["afterRuntimeSort"] = [
                {
                    "chunkId": str(item.get("chunk_id", "")),
                    "score": round(float(item.get("score", 0.0)), 6),
                    "source": str(item.get("source", "")),
                }
                for item in trimmed
            ]
        rag_debug["rerank"] = rerank
        payload["rag_debug"] = rag_debug
    return payload


def answer_with_citations_node(state: AgentState):
    hits = []
    from ...rag.schemas import RetrievalHit

    for raw in state.get("rag_chunks", []):
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
        knowledge_required=(state.get("rag_decision") == "retrieve"),
    )
    result = {"reply": payload.reply, "rag_citations": payload.citations, "rag_no_evidence": payload.no_evidence}
    if bool(state.get("rag_debug_enabled", False)):
        rag_debug = state.get("rag_debug", {})
        if not isinstance(rag_debug, dict):
            rag_debug = {}
        rag_debug["citations"] = payload.citations
        rag_debug["noEvidence"] = bool(payload.no_evidence)
        result["rag_debug"] = rag_debug
    return result


def chat_agent_node(state: AgentState):
    llm = state["llm"]
    prompt_template = state["prompt_template"]
    role = state["role"]
    system_prompt = state["system_prompt"]
    user_message = state["user_message"]
    chunks = state.get("rag_chunks", [])

    system_content = prompt_template.format(role=role, system_prompt=system_prompt)
    if chunks:
        evidence_lines = []
        segment_contexts: list[tuple[str, str]] = []
        seen_segment_ids: set[str] = set()
        for idx, chunk in enumerate(chunks, start=1):
            evidence_lines.append(
                f"[{idx}] source={chunk.get('source')} chunk_id={chunk.get('chunk_id')} section={chunk.get('section')} page={chunk.get('page')}\n{chunk.get('content')}"
            )
            segment_context = _extract_segment_context(chunk)
            if segment_context is None:
                continue
            segment_id, segment_text = segment_context
            if segment_id in seen_segment_ids:
                continue
            seen_segment_ids.add(segment_id)
            segment_contexts.append((segment_id, segment_text))
        system_content = f"{system_content}\n\n检索证据如下：\n" + "\n\n".join(evidence_lines)
        if segment_contexts:
            context_lines = [f"[{idx}] segment_id={segment_id}\n{segment_text}" for idx, (segment_id, segment_text) in enumerate(segment_contexts, start=1)]
            system_content = f"{system_content}\n\n命中句所在语义段上下文：\n" + "\n\n".join(context_lines)

    messages: list[Any] = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_message),
    ]

    tool_context = AgentToolContext(
        user_id=state["user_id"],
        workspace_id=state["workspace_id"],
        rag_debug_enabled=bool(state.get("rag_debug_enabled", False)),
    )

    tool_specs = get_agent_tools(
        context=tool_context,
    )
    tool_by_name = {item.name: item for item in tool_specs}

    graph_data = state.get("graph_data", {})
    if not isinstance(graph_data, dict):
        graph_data = {}
    graph_meta = state.get("graph_meta", {})
    if not isinstance(graph_meta, dict):
        graph_meta = {}

    kg_tool = tool_by_name.get("knowledge_graph_query")
    if kg_tool is not None:
        kg_query = _build_kg_query(state)
        kg_result = kg_tool.invoke(query=kg_query, entity=state.get("entity", ""), intent=state.get("intent", ""))
        if isinstance(kg_result, dict) and kg_result.get("ok", True):
            raw_graph = kg_result.get("graph", {})
            if isinstance(raw_graph, dict):
                nodes = raw_graph.get("nodes", [])
                edges = raw_graph.get("edges", [])
                graph_data = {
                    "nodes": nodes if isinstance(nodes, list) else [],
                    "edges": edges if isinstance(edges, list) else [],
                }
            raw_meta = kg_result.get("meta", {})
            if isinstance(raw_meta, dict):
                graph_meta = raw_meta
            summary = str(kg_result.get("summary", "")).strip()
            if summary:
                messages.append(SystemMessage(content=f"知识图谱检索结果摘要：{summary}"))

    if not bool(current_app.config.get("AGENT_AUTO_TOOL_SELECTION_ENABLED", True)) or not hasattr(llm, "bind_tools"):
        response = llm.invoke(messages)
        result = {"reply": str(getattr(response, "content", ""))}
        if graph_data:
            result["graph_data"] = graph_data
        if graph_meta:
            result["graph_meta"] = graph_meta
        return result

    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": item.name,
                "description": item.description,
                "parameters": item.args_schema,
            },
        }
        for item in tool_specs
    ]
    if not openai_tools:
        response = llm.invoke(messages)
        result = {"reply": str(getattr(response, "content", ""))}
        if graph_data:
            result["graph_data"] = graph_data
        if graph_meta:
            result["graph_meta"] = graph_meta
        return result

    auto_llm = llm.bind_tools(openai_tools)
    max_rounds = max(1, int(current_app.config.get("AGENT_TOOL_CALL_MAX_ROUNDS", 4)))
    collected_rag_chunks = list(chunks)
    merged_rag_debug = state.get("rag_debug", {})
    if not isinstance(merged_rag_debug, dict):
        merged_rag_debug = {}

    for _ in range(max_rounds):
        response = auto_llm.invoke(messages)
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", [])
        if not isinstance(tool_calls, list) or not tool_calls:
            result = {"reply": str(getattr(response, "content", ""))}
            if collected_rag_chunks:
                result["rag_chunks"] = collected_rag_chunks
            if graph_data:
                result["graph_data"] = graph_data
            if graph_meta:
                result["graph_meta"] = graph_meta
            if bool(state.get("rag_debug_enabled", False)):
                result["rag_debug"] = merged_rag_debug
            return result

        for idx, tool_call in enumerate(tool_calls, start=1):
            name = str(tool_call.get("name", "")).strip() if isinstance(tool_call, dict) else ""
            tool_call_id = (
                str(tool_call.get("id", "")).strip()
                if isinstance(tool_call, dict)
                else ""
            ) or f"tool-call-{idx}"
            args = tool_call.get("args", {}) if isinstance(tool_call, dict) else {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if not isinstance(args, dict):
                args = {}

            tool_spec = tool_by_name.get(name)
            if tool_spec is None:
                tool_result: dict[str, Any] = {"ok": False, "error": f"unknown tool: {name}"}
            else:
                tool_result = tool_spec.invoke(**args)
                if not isinstance(tool_result, dict):
                    tool_result = {"ok": True, "result": tool_result}

                if tool_spec.name == "rag_search" and tool_result.get("ok", True):
                    raw_chunks = tool_result.get("chunks", [])
                    if isinstance(raw_chunks, list):
                        collected_rag_chunks.extend(item for item in raw_chunks if isinstance(item, dict))
                    if bool(state.get("rag_debug_enabled", False)):
                        debug_payload = tool_result.get("debug", {})
                        if isinstance(debug_payload, dict):
                            merged_rag_debug = debug_payload
                if tool_spec.name == "knowledge_graph_query" and tool_result.get("ok", True):
                    raw_graph = tool_result.get("graph", {})
                    if isinstance(raw_graph, dict):
                        nodes = raw_graph.get("nodes", [])
                        edges = raw_graph.get("edges", [])
                        graph_data = {
                            "nodes": nodes if isinstance(nodes, list) else [],
                            "edges": edges if isinstance(edges, list) else [],
                        }
                    raw_meta = tool_result.get("meta", {})
                    if isinstance(raw_meta, dict):
                        graph_meta = raw_meta

            messages.append(
                ToolMessage(
                    content=json.dumps(tool_result, ensure_ascii=False, default=str),
                    tool_call_id=tool_call_id,
                )
            )

    final_response = auto_llm.invoke(messages)
    result = {"reply": str(getattr(final_response, "content", ""))}
    if collected_rag_chunks:
        result["rag_chunks"] = collected_rag_chunks
    if graph_data:
        result["graph_data"] = graph_data
    if graph_meta:
        result["graph_meta"] = graph_meta
    if bool(state.get("rag_debug_enabled", False)):
        result["rag_debug"] = merged_rag_debug
    return result
