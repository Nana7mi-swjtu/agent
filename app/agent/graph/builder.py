from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import (
    answer_with_citations_node,
    clarify_node,
    compose_answer_node,
    mcp_subagent_node,
    plan_route_node,
    route_after_mcp,
    route_after_plan,
    route_after_search,
    search_subagent_node,
)
from .state import AgentState


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("plan_route", plan_route_node)
    builder.add_node("clarify", clarify_node)
    builder.add_node("search_subagent", search_subagent_node)
    builder.add_node("mcp_subagent", mcp_subagent_node)
    builder.add_node("compose_answer", compose_answer_node)
    builder.add_node("answer_with_citations", answer_with_citations_node)

    builder.add_edge(START, "plan_route")
    builder.add_conditional_edges(
        "plan_route",
        route_after_plan,
        {
            "clarify": "clarify",
            "search_subagent": "search_subagent",
            "mcp_subagent": "mcp_subagent",
            "compose_answer": "compose_answer",
        },
    )
    builder.add_conditional_edges(
        "search_subagent",
        route_after_search,
        {
            "clarify": "clarify",
            "mcp_subagent": "mcp_subagent",
            "compose_answer": "compose_answer",
        },
    )
    builder.add_conditional_edges(
        "mcp_subagent",
        route_after_mcp,
        {
            "clarify": "clarify",
            "compose_answer": "compose_answer",
        },
    )
    builder.add_edge("clarify", END)
    builder.add_edge("compose_answer", "answer_with_citations")
    builder.add_edge("answer_with_citations", END)
    return builder.compile()
