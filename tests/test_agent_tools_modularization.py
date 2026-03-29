from __future__ import annotations

from app.agent.tools import AgentToolContext, AgentToolSpec, get_agent_tools


def test_get_agent_tools_can_be_composed_with_custom_factories(app):
    ctx = AgentToolContext(user_id=1, workspace_id="ws-1", rag_debug_enabled=False)

    def _invoke(*, text: str):
        return {"ok": True, "echo": text}

    def _factory(_):
        return AgentToolSpec(
            name="custom_echo",
            description="custom",
            invoke=_invoke,
            args_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            category="custom",
        )

    with app.app_context():
        tools = get_agent_tools(context=ctx, factories=(_factory,))

    assert len(tools) == 1
    assert tools[0].name == "custom_echo"
    result = tools[0].invoke(text="hello")
    assert result["ok"] is True
    assert result["echo"] == "hello"

