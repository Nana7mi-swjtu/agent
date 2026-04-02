from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from ..tools import AgentToolContext, get_agent_tools

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

_FRESHNESS_HINTS = (
    "最新",
    "news",
    "today",
    "recent",
    "搜索",
    "查找",
    "联网",
    "web",
    "网页",
    "监管新闻",
)


class SearchState(TypedDict):
    llm: Any
    query: str
    user_id: int
    workspace_id: str
    rag_enabled: bool
    rag_debug_enabled: bool
    preferred_strategy: str
    use_rag: bool
    use_web: bool
    rag_result: dict[str, Any]
    web_result: dict[str, Any]
    evidence: list[dict[str, Any]]
    rag_chunks: list[dict[str, Any]]
    rag_debug: dict[str, Any]
    sufficient: bool
    status: str
    summary: str
    follow_up_question: str
    strategy: str


class SearchPlanOutput(BaseModel):
    strategy: str = Field(default="private_first")
    use_rag: bool = Field(default=False)
    use_web: bool = Field(default=False)


def _preferred_strategy(state: SearchState) -> str:
    value = str(state.get("preferred_strategy", "")).strip().lower()
    if value in {"private_only", "public_only", "private_first", "hybrid"}:
        return value

    query = str(state.get("query", "")).lower()
    if any(token in query for token in _FRESHNESS_HINTS):
        return "hybrid" if bool(state.get("rag_enabled", False)) else "public_only"
    return "private_first" if bool(state.get("rag_enabled", False)) else "public_only"


def _search_plan_node(state: SearchState):
    strategy = _preferred_strategy(state)
    rag_enabled = bool(state.get("rag_enabled", False))
    query = str(state.get("query", "")).lower()
    knowledge_like = any(token in query for token in _KNOWLEDGE_HINTS)
    freshness_like = any(token in query for token in _FRESHNESS_HINTS)

    use_rag = rag_enabled and strategy in {"private_only", "private_first", "hybrid"}
    if rag_enabled and knowledge_like:
        use_rag = True

    use_web = strategy in {"public_only", "hybrid"}
    if strategy == "private_first" and not use_rag:
        use_web = True
    if freshness_like:
        use_web = True

    llm = state.get("llm")
    if hasattr(llm, "with_structured_output"):
        try:
            structured_llm = llm.with_structured_output(SearchPlanOutput)
            response = structured_llm.invoke(
                [
                    {
                        "role": "system",
                        "content": (
                            "You route search requests. Decide strategy from: private_only, public_only, "
                            "private_first, hybrid. Set use_rag/use_web based on the request and available sources."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"query={state.get('query', '')}\n"
                            f"rag_enabled={rag_enabled}\n"
                            f"preferred_strategy={strategy}\n"
                        ),
                    },
                ]
            )
            strategy = str(response.strategy).strip().lower() or strategy
            if strategy not in {"private_only", "public_only", "private_first", "hybrid"}:
                strategy = _preferred_strategy(state)
            use_rag = bool(response.use_rag) and rag_enabled
            use_web = bool(response.use_web)
        except Exception:
            pass

    return {
        "strategy": strategy,
        "use_rag": bool(use_rag),
        "use_web": bool(use_web),
        "rag_result": {},
        "web_result": {},
        "evidence": [],
        "rag_chunks": [],
        "rag_debug": {},
        "sufficient": False,
        "status": "pending",
        "summary": "",
        "follow_up_question": "",
    }


def _route_after_plan(state: SearchState) -> str:
    if state.get("use_rag", False):
        return "rag_lookup"
    if state.get("use_web", False):
        return "web_lookup"
    return "merge_results"


def _route_after_rag(state: SearchState) -> str:
    if state.get("use_web", False):
        return "web_lookup"
    return "merge_results"


def _rag_lookup_node(state: SearchState):
    tool_context = AgentToolContext(
        user_id=state["user_id"],
        workspace_id=state["workspace_id"],
        rag_debug_enabled=bool(state.get("rag_debug_enabled", False)),
    )
    tools = get_agent_tools(context=tool_context, categories=("knowledge",))
    rag_tool = next((item for item in tools if item.name == "rag_search"), None)
    if rag_tool is None:
        return {"rag_result": {"ok": False, "error": "rag tool unavailable"}}

    result = rag_tool.invoke(
        query=state["query"],
        top_k=5,
        filters={},
        include_debug=bool(state.get("rag_debug_enabled", False)),
    )
    payload: dict[str, Any] = {"rag_result": result}
    if isinstance(result, dict) and result.get("ok", False):
        chunks = result.get("chunks", [])
        if isinstance(chunks, list):
            payload["rag_chunks"] = [item for item in chunks if isinstance(item, dict)]
        debug_payload = result.get("debug", {})
        if isinstance(debug_payload, dict):
            payload["rag_debug"] = debug_payload
    return payload


def _web_lookup_node(state: SearchState):
    tool_context = AgentToolContext(
        user_id=state["user_id"],
        workspace_id=state["workspace_id"],
        rag_debug_enabled=bool(state.get("rag_debug_enabled", False)),
    )
    tools = get_agent_tools(context=tool_context, categories=("web",))
    web_tool = next((item for item in tools if item.name == "web_search"), None)
    if web_tool is None:
        return {"web_result": {"ok": False, "error": "web search unavailable"}}

    return {
        "web_result": web_tool.invoke(
            query=state["query"],
            max_results=5,
            topic="news" if any(token in state["query"].lower() for token in _FRESHNESS_HINTS) else "general",
            include_raw_content=False,
        )
    }


def _normalize_rag_evidence(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in chunks:
        evidence.append(
            {
                "source_type": "rag",
                "source": str(item.get("source", "")),
                "title": str(item.get("source", "")),
                "snippet": str(item.get("content", "")),
                "score": float(item.get("score", 0.0)),
                "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            }
        )
    return evidence


def _normalize_web_evidence(result: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(result, dict) or not result.get("ok", False):
        return []
    raw_results = result.get("results", [])
    if not isinstance(raw_results, list):
        return []
    evidence: list[dict[str, Any]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        evidence.append(
            {
                "source_type": "web",
                "source": str(item.get("url", "")),
                "title": str(item.get("title", "")),
                "snippet": str(item.get("content", "")),
                "score": float(item.get("score", 0.0)),
                "metadata": {"url": str(item.get("url", ""))},
            }
        )
    return evidence


def _merge_results_node(state: SearchState):
    rag_evidence = _normalize_rag_evidence(list(state.get("rag_chunks", [])))
    web_evidence = _normalize_web_evidence(state.get("web_result", {}))
    evidence = sorted(rag_evidence + web_evidence, key=lambda item: float(item.get("score", 0.0)), reverse=True)
    if evidence:
        source_labels = sorted({str(item.get("source_type", "")) for item in evidence if str(item.get("source_type", "")).strip()})
        return {
            "evidence": evidence,
            "sufficient": True,
            "status": "done",
            "summary": f"Collected {len(evidence)} evidence item(s) from {', '.join(source_labels)}.",
            "follow_up_question": "",
        }

    question = "未检索到可支持该问题的证据，请补充资料或换一种问法。"
    return {
        "evidence": [],
        "sufficient": False,
        "status": "need_input",
        "summary": "No supporting evidence was found.",
        "follow_up_question": question,
    }


def build_search_graph():
    builder = StateGraph(SearchState)
    builder.add_node("search_plan", _search_plan_node)
    builder.add_node("rag_lookup", _rag_lookup_node)
    builder.add_node("web_lookup", _web_lookup_node)
    builder.add_node("merge_results", _merge_results_node)

    builder.add_edge(START, "search_plan")
    builder.add_conditional_edges(
        "search_plan",
        _route_after_plan,
        {
            "rag_lookup": "rag_lookup",
            "web_lookup": "web_lookup",
            "merge_results": "merge_results",
        },
    )
    builder.add_conditional_edges(
        "rag_lookup",
        _route_after_rag,
        {
            "web_lookup": "web_lookup",
            "merge_results": "merge_results",
        },
    )
    builder.add_edge("web_lookup", "merge_results")
    builder.add_edge("merge_results", END)
    return builder.compile()
