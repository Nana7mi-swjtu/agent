from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict):
    llm: Any
    prompt_template: str
    role: str
    system_prompt: str
    user_message: str
    user_id: int
    workspace_id: str
    rag_enabled: bool
    rag_debug_enabled: bool
    rag_decision: str
    rag_chunks: list[dict]
    rag_citations: list[dict]
    rag_no_evidence: bool
    rag_debug: dict[str, Any]
    graph_data: dict[str, Any]
    graph_meta: dict[str, Any]
    reply: str
