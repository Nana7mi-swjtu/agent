from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict):
    main_llm: Any
    search_llm: Any
    mcp_llm: Any
    prompt_template: str
    role: str
    system_prompt: str
    user_message: str
    user_id: int
    workspace_id: str
    entity: str
    graph_intent: str
    intent: str
    needs_search: bool
    needs_mcp: bool
    needs_clarification: bool
    clarification_question: str
    missing_fields: list[str]
    search_request: dict[str, Any]
    search_result: dict[str, Any]
    mcp_request: dict[str, Any]
    mcp_result: dict[str, Any]
    search_completed: bool
    mcp_completed: bool
    rag_enabled: bool
    web_enabled: bool
    mcp_enabled: bool
    rag_debug_enabled: bool
    rag_chunks: list[dict]
    rag_citations: list[dict]
    rag_no_evidence: bool
    rag_debug: dict[str, Any]
    graph_data: dict[str, Any]
    graph_meta: dict[str, Any]
    debug: dict[str, Any]
    reply: str
