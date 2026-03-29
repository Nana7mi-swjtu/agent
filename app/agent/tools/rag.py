from __future__ import annotations

from flask import current_app

from ...rag.errors import RAGAuthorizationError, RAGValidationError
from ...rag.service import rag_search
from .base import AgentToolSpec
from .context import AgentToolContext


def _semantic_segment_payload(metadata: dict) -> dict | None:
    if not isinstance(metadata, dict):
        return None
    segment_id = metadata.get("semantic_segment_id")
    segment_text = metadata.get("semantic_segment_text")
    if not isinstance(segment_id, str) or not segment_id.strip():
        return None
    if not isinstance(segment_text, str) or not segment_text.strip():
        return None
    return {
        "id": segment_id,
        "text": segment_text,
        "index": metadata.get("semantic_segment_index"),
        "sentenceIndex": metadata.get("semantic_sentence_index"),
        "sentenceCount": metadata.get("semantic_segment_sentence_count"),
        "offsetStart": metadata.get("semantic_segment_offset_start"),
        "offsetEnd": metadata.get("semantic_segment_offset_end"),
        "topic": metadata.get("semantic_segment_topic"),
        "summary": metadata.get("semantic_segment_summary"),
        "source": metadata.get("semantic_segment_source"),
    }


def create_rag_search_tool(context: AgentToolContext) -> AgentToolSpec:
    def rag_search_tool(*, query: str, top_k: int = 5, filters: dict | None = None, include_debug: bool | None = None):
        if not bool(current_app.config.get("RAG_ENABLED", False)):
            return {"ok": True, "chunks": [], "debug": {}}

        effective_debug = bool(context.rag_debug_enabled if include_debug is None else include_debug)
        try:
            response = rag_search(
                user_id=context.user_id,
                workspace_id=context.workspace_id,
                query=query,
                top_k=top_k,
                filters=filters if isinstance(filters, dict) else {},
                include_debug=effective_debug,
            )
            if effective_debug:
                hits, debug_payload = response
            else:
                hits = response
                debug_payload = {}
        except (RAGValidationError, RAGAuthorizationError) as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "chunks": [
                {
                    "chunk_id": hit.chunk_id,
                    "score": hit.score,
                    "source": hit.source,
                    "page": hit.page,
                    "section": hit.section,
                    "content": hit.content,
                    "metadata": hit.metadata,
                    "semantic_segment": _semantic_segment_payload(hit.metadata),
                }
                for hit in hits
            ],
            "debug": debug_payload if isinstance(debug_payload, dict) else {},
        }

    return AgentToolSpec(
        name="rag_search",
        description="Search private workspace knowledge base and return cited chunks.",
        invoke=rag_search_tool,
        args_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                "filters": {"type": "object", "description": "Optional retrieval filters."},
                "include_debug": {"type": "boolean", "default": False},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        category="knowledge",
    )

