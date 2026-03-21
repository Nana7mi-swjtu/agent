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


def _build_runtime() -> dict[str, Any]:
    provider = str(current_app.config.get("AI_PROVIDER", "")).strip().lower()
    model = str(current_app.config.get("AI_MODEL", "")).strip()
    api_key = str(current_app.config.get("AI_API_KEY", "")).strip()
    base_url = str(current_app.config.get("AI_BASE_URL", "")).strip()
    timeout = int(current_app.config.get("AI_TIMEOUT_SECONDS", 30))

    if not model or not api_key:
        logger.error(
            "Missing AI runtime config",
            extra={"provider": provider, "model_set": bool(model), "api_key_set": bool(api_key)},
        )
        raise AgentServiceError("missing agent runtime configuration")

    try:
        llm = ChatOpenAI(
            model=model,
            api_key=SecretStr(api_key),
            base_url=base_url or None,
            timeout=timeout,
        )
        graph = build_graph()
        prompt_template = _load_chat_prompt()
    except Exception as exc:
        logger.exception("Failed to initialize agent runtime")
        raise AgentServiceError("runtime initialization failed") from exc
    
    return {"llm": llm, "graph": graph, "prompt_template": prompt_template}


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


def generate_reply(*, role: str, system_prompt: str, user_message: str) -> str:
    try:
        runtime = _get_runtime()
        state = {
            "llm": runtime["llm"],
            "prompt_template": runtime["prompt_template"],
            "role": role,
            "system_prompt": system_prompt,
            "user_message": user_message,
            "reply": "",
        }
        output = runtime["graph"].invoke(state)
        reply = str(output.get("reply", "")).strip()
    except AgentServiceError:
        raise
    except Exception as exc:
        logger.exception("Failed to generate agent reply")
        raise AgentServiceError("runtime invocation failed") from exc

    if not reply:
        raise AgentServiceError("empty agent reply")
    return reply
