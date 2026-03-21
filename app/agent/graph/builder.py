from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import chat_agent_node
from .state import AgentState


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("chat_agent", chat_agent_node)
    builder.add_edge(START, "chat_agent")
    builder.add_edge("chat_agent", END)
    return builder.compile()
