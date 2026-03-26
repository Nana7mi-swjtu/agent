from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from .state import AgentState


def chat_agent_node(state: AgentState):
    llm = state["llm"]
    prompt_template = state["prompt_template"]
    role = state["role"]
    system_prompt = state["system_prompt"]
    user_message = state["user_message"]

    system_content = prompt_template.format(role=role, system_prompt=system_prompt)
    response = llm.invoke(
        [
            SystemMessage(content=system_content),
            HumanMessage(content=user_message),
        ]
    )
    return {"reply": str(response.content)}
