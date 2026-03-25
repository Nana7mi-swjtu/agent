from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from ..tools import get_agent_tools
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


def decide_rag_node(state: AgentState):
    message = state["user_message"].lower()
    if not state.get("rag_enabled", False):
        return {"rag_decision": "skip"}
    decision = "retrieve" if any(token in message for token in _KNOWLEDGE_HINTS) else "skip"
    return {"rag_decision": decision}


def retrieve_node(state: AgentState):
    tools = get_agent_tools()
    rag_tool = next((item for item in tools if item["name"] == "rag_search"), None)
    if rag_tool is None:
        return {"rag_chunks": []}

    response = rag_tool["invoke"](
        query=state["user_message"],
        top_k=5,
        filters={},
        user_id=state["user_id"],
        workspace_id=state["workspace_id"],
    )
    if not response.get("ok", True):
        return {"rag_chunks": []}
    return {"rag_chunks": response.get("chunks", [])}


def rerank_node(state: AgentState):
    chunks = list(state.get("rag_chunks", []))
    chunks.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return {"rag_chunks": chunks[:5]}


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
    return {"reply": payload.reply, "rag_citations": payload.citations, "rag_no_evidence": payload.no_evidence}


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
        for idx, chunk in enumerate(chunks, start=1):
            evidence_lines.append(
                f"[{idx}] source={chunk.get('source')} chunk_id={chunk.get('chunk_id')} section={chunk.get('section')} page={chunk.get('page')}\n{chunk.get('content')}"
            )
        system_content = f"{system_content}\n\n检索证据如下：\n" + "\n\n".join(evidence_lines)
    response = llm.invoke(
        [
            SystemMessage(content=system_content),
            HumanMessage(content=user_message),
        ]
    )
    return {"reply": str(response.content)}
