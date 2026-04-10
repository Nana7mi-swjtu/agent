from __future__ import annotations

from collections.abc import Iterable

from .base import AgentToolSpec, ToolFactory
from .context import AgentToolContext
from .knowledge_graph import create_knowledge_graph_tool
from .mcp import create_mcp_tools
from .rag import create_rag_search_tool
from .websearch import create_web_search_tool


def _iter_specs(factory_output: AgentToolSpec | Iterable[AgentToolSpec] | None) -> Iterable[AgentToolSpec]:
    if factory_output is None:
        return ()
    if isinstance(factory_output, AgentToolSpec):
        return (factory_output,)
    return tuple(factory_output)


def get_agent_tools(*, context: AgentToolContext, factories: Iterable[ToolFactory] | None = None) -> list[AgentToolSpec]:
    tool_factories = tuple(factories) if factories is not None else (
        create_rag_search_tool,
        create_knowledge_graph_tool,
        create_web_search_tool,
        create_mcp_tools,
    )
    specs: list[AgentToolSpec] = []
    for factory in tool_factories:
        output = factory(context)
        for item in _iter_specs(output):
            specs.append(item)
    return specs
