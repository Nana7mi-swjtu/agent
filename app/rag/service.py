from __future__ import annotations

import concurrent.futures
import logging
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import current_app

from ..db import session_scope
from ..models import RagDocument
from .errors import RAGAuthorizationError, RAGContractError, RAGValidationError
from .pipeline.indexer import parse_and_chunk_document
from .providers.registry import get_chunker, get_embedder, get_reranker, get_vector_store
from .repository import (
    create_chunk_entities,
    create_document,
    create_index_job,
    create_query_log,
    get_document_for_scope,
    get_index_job_for_scope,
    replace_document_chunks,
    set_document_status,
    set_index_job_status,
)
from .schemas import RAGAnswerPayload, RetrievalHit

logger = logging.getLogger(__name__)
_executor: concurrent.futures.ThreadPoolExecutor | None = None


def _ensure_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, int(current_app.config.get("RAG_INDEX_MAX_WORKERS", 2)))
        )
    return _executor


def _rag_upload_dir() -> Path:
    directory = Path(current_app.root_path).parent / str(current_app.config["RAG_UPLOAD_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _allowed_extensions() -> set[str]:
    return {ext.lower().lstrip(".") for ext in current_app.config.get("RAG_ALLOWED_FILE_TYPES", ())}


def _workspace_from_request(workspace_id: str | None) -> str:
    normalized = (workspace_id or "").strip()
    if not normalized:
        raise RAGValidationError("workspace_id is required")
    return normalized


def _collection_name_for_workspace(workspace_id: str) -> str:
    return f"workspace_{workspace_id}"


def upload_document(*, user_id: int, workspace_id: str, file_storage):
    workspace = _workspace_from_request(workspace_id)
    if not file_storage or not file_storage.filename:
        raise RAGValidationError("file is required")

    original_name = str(file_storage.filename).strip()
    if "." not in original_name:
        raise RAGValidationError("file extension is required")
    extension = original_name.rsplit(".", 1)[1].lower()
    if extension not in _allowed_extensions():
        allowed = ", ".join(sorted(_allowed_extensions()))
        raise RAGValidationError(f"unsupported format; allowed formats: {allowed}")

    stored_name = f"{uuid4().hex}.{extension}"
    target_path = _rag_upload_dir() / stored_name
    file_storage.save(target_path)

    source_name = original_name
    mime_type = str(getattr(file_storage, "mimetype", "") or "application/octet-stream")
    with session_scope() as db:
        document = create_document(
            db=db,
            user_id=user_id,
            workspace_id=workspace,
            source_name=source_name,
            file_name=original_name,
            file_extension=extension,
            mime_type=mime_type,
            storage_path=str(target_path),
        )
        payload = {
            "id": document.id,
            "status": document.status,
            "workspaceId": document.workspace_id,
            "sourceName": document.source_name,
            "fileName": document.file_name,
            "fileExtension": document.file_extension,
            "createdAt": document.created_at.isoformat(),
        }

    if bool(current_app.config.get("RAG_AUTO_INDEX_ON_UPLOAD", True)):
        job_payload = enqueue_index_job(user_id=user_id, workspace_id=workspace, document_id=payload["id"])
        payload["jobId"] = job_payload["jobId"]
        payload["jobStatus"] = job_payload["status"]
        payload["status"] = "indexing"
    return payload


def enqueue_index_job(*, user_id: int, workspace_id: str, document_id: int) -> dict:
    workspace = _workspace_from_request(workspace_id)
    app = current_app._get_current_object()
    with session_scope() as db:
        document = get_document_for_scope(db=db, document_id=document_id, user_id=user_id, workspace_id=workspace)
        set_document_status(document=document, status="indexing")
        job = create_index_job(db=db, document=document)
        job_payload = {"jobId": job.id, "documentId": document.id, "status": job.status}

    if bool(app.config.get("TESTING", False)):
        _run_index_job(app, job_payload["jobId"], user_id, workspace)
    else:
        _ensure_executor().submit(_run_index_job, app, job_payload["jobId"], user_id, workspace)
    return job_payload


def _run_index_job(app, job_id: int, user_id: int, workspace_id: str) -> None:
    started = datetime.utcnow()
    chunk_count = 0
    try:
        with app.app_context():
            with session_scope() as db:
                job = get_index_job_for_scope(db=db, job_id=job_id, user_id=user_id, workspace_id=workspace_id)
                document = get_document_for_scope(
                    db=db,
                    document_id=job.document_id,
                    user_id=user_id,
                    workspace_id=workspace_id,
                )
                set_index_job_status(job=job, status="running")
                set_document_status(document=document, status="indexing")

            chunker = get_chunker()
            embedder = get_embedder()
            vector_store = get_vector_store()
            collection_name = _collection_name_for_workspace(workspace_id)
            chunk_payloads = parse_and_chunk_document(
                file_path=document.storage_path,
                extension=document.file_extension,
                document_id=document.id,
                source_name=document.source_name,
                chunker=chunker,
                chunk_size=int(current_app.config["RAG_CHUNK_SIZE"]),
                overlap=int(current_app.config["RAG_CHUNK_OVERLAP"]),
            )
            for payload in chunk_payloads:
                payload.metadata["user_id"] = user_id
                payload.metadata["workspace_id"] = workspace_id
                payload.metadata["document_id"] = document.id
            vectors = embedder.embed_documents([item.text for item in chunk_payloads])
            for vector in vectors:
                if len(vector) != embedder.dimension:
                    raise RAGValidationError("embedding dimension mismatch during indexing")

            vector_store.upsert_chunks(
                workspace_id=workspace_id,
                collection_name=collection_name,
                chunk_payloads=chunk_payloads,
                vectors=vectors,
            )
            chunk_entities = create_chunk_entities(
                document=document,
                chunk_payloads=chunk_payloads,
                embedding_model=embedder.model_name,
                embedding_version=embedder.model_version,
                embedding_dimension=embedder.dimension,
            )
            chunk_count = len(chunk_entities)

            with session_scope() as db:
                job = get_index_job_for_scope(db=db, job_id=job_id, user_id=user_id, workspace_id=workspace_id)
                document = get_document_for_scope(
                    db=db,
                    document_id=job.document_id,
                    user_id=user_id,
                    workspace_id=workspace_id,
                )
                replace_document_chunks(db=db, document=document, chunks=chunk_entities)
                document.embedding_model = embedder.model_name
                document.embedding_version = embedder.model_version
                document.embedding_dimension = embedder.dimension
                set_document_status(document=document, status="indexed", indexed_at=datetime.utcnow())
                set_index_job_status(job=job, status="done", chunks_count=chunk_count)
    except Exception as exc:
        logger.exception("RAG indexing job failed", extra={"job_id": job_id})
        with app.app_context():
            with session_scope() as db:
                try:
                    job = get_index_job_for_scope(db=db, job_id=job_id, user_id=user_id, workspace_id=workspace_id)
                    document = get_document_for_scope(
                        db=db,
                        document_id=job.document_id,
                        user_id=user_id,
                        workspace_id=workspace_id,
                    )
                    set_document_status(document=document, status="failed", error_message=str(exc))
                    set_index_job_status(
                        job=job,
                        status="failed",
                        error_stage="pipeline",
                        error_message=str(exc),
                        chunks_count=chunk_count,
                    )
                except Exception:
                    logger.exception("Failed to persist indexing failure", extra={"job_id": job_id})
    finally:
        elapsed = int((datetime.utcnow() - started).total_seconds() * 1000)
        logger.info("RAG indexing job finished", extra={"job_id": job_id, "duration_ms": elapsed})


def get_job_status(*, user_id: int, workspace_id: str, job_id: int) -> dict:
    workspace = _workspace_from_request(workspace_id)
    with session_scope() as db:
        job = get_index_job_for_scope(db=db, job_id=job_id, user_id=user_id, workspace_id=workspace)
        return {
            "jobId": job.id,
            "documentId": job.document_id,
            "status": job.status,
            "errorStage": job.error_stage,
            "errorMessage": job.error_message,
            "chunksCount": job.chunks_count,
            "startedAt": job.started_at.isoformat() if job.started_at else None,
            "finishedAt": job.finished_at.isoformat() if job.finished_at else None,
            "durationMs": job.duration_ms,
        }


def rag_search(
    *,
    user_id: int,
    workspace_id: str,
    query: str,
    top_k: int,
    filters: dict[str, str | int] | None = None,
) -> list[RetrievalHit]:
    workspace = _workspace_from_request(workspace_id)
    text = str(query).strip()
    if not text:
        raise RAGValidationError("query is required")
    if top_k <= 0:
        raise RAGValidationError("top_k must be positive")

    scoped_filters = dict(filters or {})
    if "user_id" in scoped_filters and scoped_filters["user_id"] != user_id:
        raise RAGAuthorizationError("unauthorized user scope requested")
    if "workspace_id" in scoped_filters and scoped_filters["workspace_id"] != workspace:
        raise RAGAuthorizationError("unauthorized workspace scope requested")
    scoped_filters["user_id"] = user_id
    scoped_filters["workspace_id"] = workspace

    embedder = get_embedder()
    vector_store = get_vector_store()
    reranker = get_reranker()

    start = time.perf_counter()
    failure_reason: str | None = None
    hits: list[RetrievalHit] = []
    try:
        query_vector = embedder.embed_query(text)
        if len(query_vector) != embedder.dimension:
            raise RAGValidationError("query embedding dimension mismatch")
        hits = vector_store.query(
            workspace_id=workspace,
            collection_name=_collection_name_for_workspace(workspace),
            query_vector=query_vector,
            top_k=top_k,
            filters=scoped_filters,
        )
        threshold = float(current_app.config.get("RAG_RETRIEVAL_SCORE_THRESHOLD", 0.0))
        hits = [hit for hit in hits if hit.score >= threshold]
        if reranker:
            hits = reranker.rerank(query=text, hits=hits, top_k=top_k)
    except Exception as exc:
        failure_reason = str(exc)
        raise
    finally:
        latency_ms = int((time.perf_counter() - start) * 1000)
        with session_scope() as db:
            create_query_log(
                db=db,
                user_id=user_id,
                workspace_id=workspace,
                query_text=text,
                top_k=top_k,
                hit_count=len(hits),
                latency_ms=latency_ms,
                top_scores=[round(hit.score, 6) for hit in hits[:3]],
                filters=scoped_filters,
                vector_provider=vector_store.provider_name,
                embedder_provider=embedder.provider_name,
                embedding_model=embedder.model_name,
                embedding_version=embedder.model_version,
                embedding_dimension=embedder.dimension,
                failure_reason=failure_reason,
            )
    return hits


def build_cited_response(*, base_reply: str, hits: list[RetrievalHit], knowledge_required: bool) -> RAGAnswerPayload:
    if not hits:
        if knowledge_required:
            reply = "未检索到可支持该问题的证据，请补充资料或换一种问法。"
            return RAGAnswerPayload(reply=reply, used_rag=False, no_evidence=True, citations=[])
        return RAGAnswerPayload(reply=base_reply, used_rag=False, no_evidence=False, citations=[])

    citations: list[dict] = []
    for hit in hits:
        if not hit.source or not hit.chunk_id:
            raise RAGContractError("retrieval hit missing required citation fields")
        citations.append(
            {
                "source": hit.source,
                "chunk_id": hit.chunk_id,
                "page": hit.page,
                "section": hit.section,
                "score": round(hit.score, 6),
            }
        )
    reply = base_reply
    return RAGAnswerPayload(reply=reply, used_rag=True, no_evidence=False, citations=citations)


def list_documents(*, user_id: int, workspace_id: str) -> list[dict]:
    workspace = _workspace_from_request(workspace_id)
    with session_scope() as db:
        docs = (
            db.query(RagDocument)
            .filter(RagDocument.user_id == user_id, RagDocument.workspace_id == workspace)
            .order_by(RagDocument.created_at.desc())
            .all()
        )
        return [
            {
                "id": doc.id,
                "status": doc.status,
                "sourceName": doc.source_name,
                "fileName": doc.file_name,
                "fileExtension": doc.file_extension,
                "errorMessage": doc.error_message,
                "embeddingModel": doc.embedding_model,
                "embeddingVersion": doc.embedding_version,
                "embeddingDimension": doc.embedding_dimension,
                "createdAt": doc.created_at.isoformat(),
                "updatedAt": doc.updated_at.isoformat(),
                "indexedAt": doc.indexed_at.isoformat() if doc.indexed_at else None,
            }
            for doc in docs
        ]
