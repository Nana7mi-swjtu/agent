from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import (
    answer_with_citations_node,
    chat_agent_node,
    decide_rag_node,
    rerank_node,
    retrieve_node,
)
from .state import AgentState


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("decide_rag", decide_rag_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("rerank", rerank_node)
    builder.add_node("chat_agent", chat_agent_node)
    builder.add_node("answer_with_citations", answer_with_citations_node)

    builder.add_edge(START, "decide_rag")
    builder.add_conditional_edges(
        "decide_rag",
        lambda state: state.get("rag_decision", "skip"),
        {
            "retrieve": "retrieve",
            "skip": "chat_agent",
        },
    )
    builder.add_edge("retrieve", "rerank")
    builder.add_edge("rerank", "chat_agent")
    builder.add_edge("chat_agent", "answer_with_citations")
    builder.add_edge("answer_with_citations", END)
    return builder.compile()
