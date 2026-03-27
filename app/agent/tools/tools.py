from __future__ import annotations

from flask import current_app

from ...rag.errors import RAGAuthorizationError, RAGValidationError
from ...rag.service import rag_search

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
                }
                for hit in hits
            ],
            "debug": debug_payload if isinstance(debug_payload, dict) else {},
        }

    return [{"name": "rag_search", "invoke": rag_search_tool}]
