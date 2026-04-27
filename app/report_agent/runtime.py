from __future__ import annotations

import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

from flask import current_app, has_app_context
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

logger = logging.getLogger(__name__)

_runtime_lock = Lock()
_runtime: dict[str, Any] | None = None


class ReportRuntimeError(RuntimeError):
    pass


def _config_value(key: str, fallback: str = "") -> Any:
    if has_app_context():
        value = current_app.config.get(key)
        if value not in (None, ""):
            return value
    return os.getenv(key, fallback)


def report_llm_config() -> dict[str, Any]:
    provider = str(_config_value("AGENT_REPORT_AI_PROVIDER") or "").strip().lower()
    model = str(_config_value("AGENT_REPORT_AI_MODEL") or "").strip()
    api_key = str(_config_value("AGENT_REPORT_AI_API_KEY") or "").strip()
    base_url = str(_config_value("AGENT_REPORT_AI_BASE_URL") or "").strip()
    raw_timeout = _config_value("AGENT_REPORT_AI_TIMEOUT_SECONDS") or 60
    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        timeout = 60
    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "timeout": timeout,
    }


def _load_env_if_needed() -> None:
    if has_app_context():
        return
    if report_llm_config()["model"] and report_llm_config()["api_key"]:
        return
    try:
        from dotenv import load_dotenv
    except Exception:  # pragma: no cover
        return
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)


def _create_report_llm() -> Any:
    _load_env_if_needed()
    config = report_llm_config()
    if not config["model"] or not config["api_key"]:
        logger.error(
            "Missing report AI runtime config",
            extra={
                "provider": config["provider"],
                "model_set": bool(config["model"]),
                "api_key_set": bool(config["api_key"]),
            },
        )
        raise ReportRuntimeError("missing report runtime configuration")
    return ChatOpenAI(
        model=config["model"],
        api_key=SecretStr(config["api_key"]),
        base_url=config["base_url"] or None,
        timeout=config["timeout"],
    )


def _build_runtime() -> dict[str, Any]:
    try:
        report_llm = _create_report_llm()
    except ReportRuntimeError:
        raise
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to initialize report runtime")
        raise ReportRuntimeError("report runtime initialization failed") from exc
    return {"report_llm": report_llm}


def get_report_writer(report_writer: Any | None = None) -> Any:
    if report_writer is not None:
        return report_writer
    return get_report_runtime()["report_llm"]


def get_report_runtime() -> dict[str, Any]:
    global _runtime
    if _runtime is not None:
        return _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = _build_runtime()
    return _runtime


def reset_report_runtime_for_tests() -> None:
    global _runtime
    with _runtime_lock:
        _runtime = None
