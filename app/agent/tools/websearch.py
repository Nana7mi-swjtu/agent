from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

from .base import AgentToolSpec
from .context import AgentToolContext


def _normalize_result_item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(raw.get("title", "")),
        "url": str(raw.get("url", "")),
        "content": str(raw.get("content", "")),
        "score": float(raw.get("score", 0.0)),
    }


def _tavily_web_search_invoke(
    *,
    query: str,
    max_results: int = 5,
    topic: str = "general",
    include_raw_content: bool = False,
) -> dict[str, Any]:
    if not bool(current_app.config.get("AGENT_WEBSEARCH_ENABLED", False)):
        return {"ok": False, "error": "websearch is disabled"}

    api_key = str(current_app.config.get("TAVILY_API_KEY", "")).strip()
    if not api_key:
        return {"ok": False, "error": "TAVILY_API_KEY is not configured"}

    base_url = str(current_app.config.get("TAVILY_BASE_URL", "https://api.tavily.com/search")).strip()
    timeout_seconds = int(current_app.config.get("TAVILY_TIMEOUT_SECONDS", 15))

    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max(1, min(int(max_results), 10)),
        "topic": topic if topic in {"general", "news"} else "general",
        "include_raw_content": bool(include_raw_content),
    }
    encoded = json.dumps(payload).encode("utf-8")
    request = Request(base_url, data=encoded, method="POST")
    request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        return {"ok": False, "error": f"tavily http error: {exc.code}"}
    except URLError as exc:
        return {"ok": False, "error": f"tavily request failed: {exc.reason}"}
    data = json.loads(body)
    results = data.get("results", [])
    if not isinstance(results, list):
        results = []

    return {
        "ok": True,
        "answer": str(data.get("answer", "")),
        "results": [_normalize_result_item(item) for item in results if isinstance(item, dict)],
    }


def create_web_search_tool(_: AgentToolContext) -> AgentToolSpec | None:
    if not bool(current_app.config.get("AGENT_WEBSEARCH_ENABLED", False)):
        return None
    return AgentToolSpec(
        name="web_search",
        description="Search the public web by Tavily for fresh information.",
        invoke=_tavily_web_search_invoke,
        args_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                "topic": {"type": "string", "enum": ["general", "news"], "default": "general"},
                "include_raw_content": {"type": "boolean", "default": False},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        category="web",
    )

