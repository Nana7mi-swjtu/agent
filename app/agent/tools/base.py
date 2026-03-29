from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Callable

from .context import AgentToolContext

ToolInvoke = Callable[..., Any]
ToolFactory = Callable[[AgentToolContext], "AgentToolSpec | Iterable[AgentToolSpec] | None"]


@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    description: str
    invoke: ToolInvoke
    args_schema: dict[str, Any]
    category: str


