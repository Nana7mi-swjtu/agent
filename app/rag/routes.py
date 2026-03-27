from __future__ import annotations

import logging

from flask import Blueprint, request, session

from .errors import RAGAuthorizationError, RAGError, RAGValidationError
from .service import (
    build_workspace_debug_snapshot,
    enqueue_index_job,
    get_chunk_embedding_debug,
    get_job_status,
    list_documents,
    parse_chunking_request,
    rag_search,
    upload_document,
)

rag_bp = Blueprint("rag", __name__)
logger = logging.getLogger(__name__)


def _json_error(message: str, status_code: int):
    return {"ok": False, "error": message}, status_code


def _current_user_id() -> int | None:
    user_id = session.get("user_id")
    if isinstance(user_id, int):
        return user_id
    return None


def _workspace_id_from_request(default: str = "default") -> str:
    payload = request.get_json(silent=True)
    workspace_id: str | None = None
    if isinstance(payload, dict):
        raw = payload.get("workspaceId")
        if isinstance(raw, str):
            workspace_id = raw
    if workspace_id is None:
        workspace_id = request.args.get("workspaceId", default)
    return str(workspace_id).strip() or default


def _ensure_rag_enabled():
    from flask import current_app

    if not bool(current_app.config.get("RAG_ENABLED", False)):
        return _json_error("rag feature is disabled", 404)
    return None


@rag_bp.get("/documents")
def get_documents():
    disabled = _ensure_rag_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    workspace_id = _workspace_id_from_request()
    try:
        documents = list_documents(user_id=user_id, workspace_id=workspace_id)
    except RAGValidationError as exc:
        return _json_error(str(exc), 400)
    return {"ok": True, "data": {"documents": documents}}


@rag_bp.get("/debug")
def debug_snapshot():
    disabled = _ensure_rag_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)
    from flask import current_app

    if not bool(current_app.config.get("RAG_DEBUG_VISUALIZATION_ENABLED", False)):
        return _json_error("rag debug visualization is disabled", 404)

    workspace_id = _workspace_id_from_request()
    try:
        data = build_workspace_debug_snapshot(user_id=user_id, workspace_id=workspace_id)
    except RAGValidationError as exc:
        return _json_error(str(exc), 400)
    except RAGError:
        logger.exception("RAG debug snapshot failed")
        return _json_error("failed to build rag debug snapshot", 500)
    return {"ok": True, "data": data}


@rag_bp.get("/embedding")
def read_chunk_embedding():
    disabled = _ensure_rag_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)
    from flask import current_app

    if not bool(current_app.config.get("RAG_DEBUG_VISUALIZATION_ENABLED", False)):
        return _json_error("rag debug visualization is disabled", 404)

    workspace_id = _workspace_id_from_request()
    chunk_id = str(request.args.get("chunkId", "")).strip()
    include_full_raw = str(request.args.get("full", "false")).strip().lower()
    include_full = include_full_raw in {"1", "true", "yes", "on"}
    sample_size_raw = request.args.get("sampleSize", "16")
    try:
        sample_size = int(sample_size_raw)
    except Exception:
        return _json_error("sampleSize must be an integer", 400)
    try:
        data = get_chunk_embedding_debug(
            user_id=user_id,
            workspace_id=workspace_id,
            chunk_id=chunk_id,
            include_full=include_full,
            sample_size=sample_size,
        )
    except RAGValidationError as exc:
        return _json_error(str(exc), 400)
    except RAGError:
        logger.exception("RAG embedding debug failed")
        return _json_error("failed to read embedding", 500)
    return {"ok": True, "data": data}


@rag_bp.post("/upload")
def upload():
    disabled = _ensure_rag_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    workspace_id = request.form.get("workspaceId", "").strip() or "default"
    chunking_raw = request.form.get("chunking")
    chunking_payload = None
    if chunking_raw:
        import json

        try:
            chunking_payload = json.loads(chunking_raw)
        except Exception:
            return _json_error("chunking must be valid JSON", 400)
    elif request.form.get("chunkingStrategy"):
        chunking_payload = {"strategy": str(request.form.get("chunkingStrategy"))}
    file_storage = request.files.get("file")
    try:
        data = upload_document(
            user_id=user_id,
            workspace_id=workspace_id,
            file_storage=file_storage,
            chunking=parse_chunking_request(chunking_payload),
        )
    except RAGValidationError as exc:
        return _json_error(str(exc), 400)
    except RAGError as exc:
        logger.exception("RAG upload failed")
        return _json_error(str(exc), 500)

    return {"ok": True, "data": data}


@rag_bp.post("/index")
def create_index():
    disabled = _ensure_rag_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error("request body is required", 400)
    document_id = payload.get("documentId")
    workspace_id = str(payload.get("workspaceId", "default")).strip() or "default"
    chunking_payload = payload.get("chunking")
    if not isinstance(document_id, int) or document_id <= 0:
        return _json_error("documentId must be a positive integer", 400)

    try:
        data = enqueue_index_job(
            user_id=user_id,
            workspace_id=workspace_id,
            document_id=document_id,
            chunking=parse_chunking_request(chunking_payload),
        )
    except RAGAuthorizationError as exc:
        return _json_error(str(exc), 403)
    except RAGValidationError as exc:
        return _json_error(str(exc), 400)
    except RAGError:
        logger.exception("RAG index enqueue failed")
        return _json_error("failed to enqueue index job", 500)

    return {"ok": True, "data": data}


@rag_bp.get("/jobs/<int:job_id>")
def read_job(job_id: int):
    disabled = _ensure_rag_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)
    workspace_id = _workspace_id_from_request()

    try:
        data = get_job_status(user_id=user_id, workspace_id=workspace_id, job_id=job_id)
    except RAGAuthorizationError as exc:
        return _json_error(str(exc), 403)
    except RAGValidationError as exc:
        return _json_error(str(exc), 404)
    return {"ok": True, "data": data}


@rag_bp.post("/search")
def search():
    disabled = _ensure_rag_enabled()
    if disabled:
        return disabled
    user_id = _current_user_id()
    if user_id is None:
        return _json_error("authentication required", 401)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error("request body is required", 400)
    query = payload.get("query", "")
    top_k = payload.get("topK", 5)
    filters = payload.get("filters", {})
    workspace_id = str(payload.get("workspaceId", "default")).strip() or "default"

    if not isinstance(top_k, int):
        return _json_error("topK must be an integer", 400)
    if not isinstance(filters, dict):
        return _json_error("filters must be an object", 400)

    try:
        hits = rag_search(
            user_id=user_id,
            workspace_id=workspace_id,
            query=str(query),
            top_k=top_k,
            filters=filters,
        )
    except RAGAuthorizationError as exc:
        return _json_error(str(exc), 403)
    except RAGValidationError as exc:
        return _json_error(str(exc), 400)
    except RAGError:
        logger.exception("RAG search failed")
        return _json_error("rag search failed", 500)

    return {
        "ok": True,
        "data": {
            "chunks": [
                {
                    "chunkId": hit.chunk_id,
                    "score": hit.score,
                    "source": hit.source,
                    "page": hit.page,
                    "section": hit.section,
                    "content": hit.content,
                    "metadata": hit.metadata,
                }
                for hit in hits
            ]
        },
    }
