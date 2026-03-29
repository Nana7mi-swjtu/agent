from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentToolContext:
    user_id: int
    workspace_id: str
    rag_debug_enabled: bool = False

