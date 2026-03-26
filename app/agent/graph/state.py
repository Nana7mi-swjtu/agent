from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict):
    llm: Any
    prompt_template: str
    role: str
    system_prompt: str
    user_message: str
    reply: str
