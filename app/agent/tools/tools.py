from __future__ import annotations

from flask import current_app

from ...rag.errors import RAGAuthorizationError, RAGValidationError
from ...rag.service import rag_search


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


def get_agent_tools():
    def rag_search_tool(
        *,
        query: str,
        top_k: int,
        filters: dict,
        user_id: int,
        workspace_id: str,
        include_debug: bool = False,
    ):
        if not bool(current_app.config.get("RAG_ENABLED", False)):
            return {"chunks": [], "debug": {}}
        try:
            response = rag_search(
                user_id=user_id,
                workspace_id=workspace_id,
                query=query,
                top_k=top_k,
                filters=filters,
                include_debug=include_debug,
            )
            if include_debug:
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

    return [{"name": "rag_search", "invoke": rag_search_tool}]
