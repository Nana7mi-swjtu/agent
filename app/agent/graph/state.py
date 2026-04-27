from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict):
    main_llm: Any
    search_llm: Any
    analysis_llm: Any
    display_llm: Any
    prompt_template: str
    role: str
    system_prompt: str
    user_message: str
    conversation_history: list[dict[str, str]]
    conversation_context: str
    user_id: int
    workspace_id: str
    entity: str
    graph_intent: str
    intent: str
    needs_search: bool
    needs_clarification: bool
    clarification_question: str
    missing_fields: list[str]
    search_request: dict[str, Any]
    search_result: dict[str, Any]
    enabled_analysis_modules: list[str]
    analysis_shared_inputs: dict[str, Any]
    analysis_module_inputs: dict[str, dict[str, Any]]
    report_request: dict[str, Any]
    analysis_session: dict[str, Any]
    analysis_missing_fields: list[dict[str, Any]]
    analysis_results: dict[str, dict[str, Any]]
    analysis_handoff_bundle: dict[str, Any]
    analysis_completed: bool
    analysis_unsupported_modules: list[str]
    analysis_module_artifacts: list[dict[str, Any]]
    analysis_report: dict[str, Any]
    analysis_report_artifact: dict[str, Any]
    search_completed: bool
    kg_enabled: bool
    rag_enabled: bool
    web_enabled: bool
    rag_debug_enabled: bool
    rag_chunks: list[dict]
    rag_citations: list[dict]
    rag_no_evidence: bool
    rag_debug: dict[str, Any]
    graph_data: dict[str, Any]
    graph_meta: dict[str, Any]
    debug: dict[str, Any]
    reply: str
