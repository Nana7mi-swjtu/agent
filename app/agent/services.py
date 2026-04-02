from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock
from typing import Any

from flask import current_app
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from .graph import build_graph

_runtime_lock = Lock()
_runtime: dict[str, Any] | None = None
logger = logging.getLogger(__name__)


class AgentServiceError(RuntimeError):
    pass


def _load_chat_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent / "prompts" / "chat.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    logger.warning("Agent prompt file missing, using built-in fallback prompt")
    return (
        "You are a helpful assistant.\n"
        "Role: {role}\n"
        "System prompt: {system_prompt}\n"
    )


def _agent_llm_config(agent_key: str) -> dict[str, Any]:
    normalized = agent_key.strip().upper()
    provider = str(
        current_app.config.get(f"AGENT_{normalized}_AI_PROVIDER") or current_app.config.get("AI_PROVIDER", "")
    ).strip().lower()
    model = str(
        current_app.config.get(f"AGENT_{normalized}_AI_MODEL") or current_app.config.get("AI_MODEL", "")
    ).strip()
    api_key = str(
        current_app.config.get(f"AGENT_{normalized}_AI_API_KEY") or current_app.config.get("AI_API_KEY", "")
    ).strip()
    base_url = str(
        current_app.config.get(f"AGENT_{normalized}_AI_BASE_URL") or current_app.config.get("AI_BASE_URL", "")
    ).strip()
    timeout = int(
        current_app.config.get(f"AGENT_{normalized}_AI_TIMEOUT_SECONDS")
        or current_app.config.get("AI_TIMEOUT_SECONDS", 30)
    )
    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "timeout": timeout,
    }


def _create_llm(agent_key: str) -> Any:
    config = _agent_llm_config(agent_key)
    if not config["model"] or not config["api_key"]:
        logger.error(
            "Missing AI runtime config",
            extra={
                "agent_key": agent_key,
                "provider": config["provider"],
                "model_set": bool(config["model"]),
                "api_key_set": bool(config["api_key"]),
            },
        )
        raise AgentServiceError("missing agent runtime configuration")
    return ChatOpenAI(
        model=config["model"],
        api_key=SecretStr(config["api_key"]),
        base_url=config["base_url"] or None,
        timeout=config["timeout"],
    )


def _build_runtime() -> dict[str, Any]:
    try:
        main_llm = _create_llm("MAIN")
        search_llm = _create_llm("SEARCH")
        mcp_llm = _create_llm("MCP")
        graph = build_graph()
        prompt_template = _load_chat_prompt()
    except Exception as exc:
        logger.exception("Failed to initialize agent runtime")
        raise AgentServiceError("runtime initialization failed") from exc

    return {
        "main_llm": main_llm,
        "search_llm": search_llm,
        "mcp_llm": mcp_llm,
        "graph": graph,
        "prompt_template": prompt_template,
    }


def _get_runtime() -> dict[str, Any]:
    global _runtime
    if _runtime is not None:
        return _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = _build_runtime()
    return _runtime


def reset_runtime_for_tests() -> None:
    global _runtime
    with _runtime_lock:
        _runtime = None


def generate_reply_payload(
    *,
    role: str,
    system_prompt: str,
    user_message: str,
    user_id: int = 0,
    workspace_id: str = "default",
    rag_debug_enabled: bool = False,
) -> dict[str, Any]:
    try:
        runtime = _get_runtime()
        state = {
            "main_llm": runtime["main_llm"],
            "search_llm": runtime["search_llm"],
            "mcp_llm": runtime["mcp_llm"],
            "prompt_template": runtime["prompt_template"],
            "role": role,
            "system_prompt": system_prompt,
            "user_message": user_message,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "intent": "",
            "needs_search": False,
            "needs_mcp": False,
            "needs_clarification": False,
            "clarification_question": "",
            "missing_fields": [],
            "search_request": {},
            "search_result": {},
            "mcp_request": {},
            "mcp_result": {},
            "search_completed": False,
            "mcp_completed": False,
            "rag_enabled": bool(current_app.config.get("RAG_ENABLED", False)),
            "web_enabled": bool(current_app.config.get("AGENT_WEBSEARCH_ENABLED", False)),
            "mcp_enabled": bool(current_app.config.get("AGENT_MCP_ENABLED", False)),
            "rag_debug_enabled": bool(rag_debug_enabled),
            "rag_chunks": [],
            "rag_citations": [],
            "rag_no_evidence": False,
            "rag_debug": {},
            "debug": {},
            "reply": "",
        }
        output = runtime["graph"].invoke(state)
        reply = str(output.get("reply", "")).strip()
        citations = output.get("rag_citations", [])
        if not isinstance(citations, list):
            citations = []
        no_evidence = bool(output.get("rag_no_evidence", False))
        debug_payload = output.get("debug", {})
        if not isinstance(debug_payload, dict):
            debug_payload = {}
    except AgentServiceError:
        raise
    except Exception as exc:
        logger.exception("Failed to generate agent reply")
        raise AgentServiceError("runtime invocation failed") from exc

    if not reply:
        raise AgentServiceError("empty agent reply")
    return {"reply": reply, "citations": citations, "noEvidence": no_evidence, "debug": debug_payload}


def generate_reply(*, role: str, system_prompt: str, user_message: str) -> str:
    payload = generate_reply_payload(role=role, system_prompt=system_prompt, user_message=user_message)
    return payload["reply"]
