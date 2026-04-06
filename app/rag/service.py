from __future__ import annotations

import concurrent.futures
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import current_app
from sqlalchemy import func

from ..db import session_scope
from ..models import RagChunk, RagDocument, RagIndexJob
from .errors import RAGAuthorizationError, RAGContractError, RAGValidationError
from .pipeline.indexer import parse_and_chunk_document
from .pipeline.chunking import build_chunking_applied, resolve_chunking_plan
from .providers.registry import (
    get_chunker,
    get_embedder,
    get_reranker,
    get_semantic_chunking_provider,
    get_vector_store,
)
from .repository import (
    create_chunk_entities,
    create_document,
    create_index_job,
    create_query_log,
    delete_document_chunks,
    ensure_document_deletable,
    get_document_for_scope,
    get_index_job_for_scope,
    list_documents_for_scope,
    replace_document_chunks,
    set_document_status,
    set_index_job_status,
)
from .schemas import ChunkingRequest, RAGAnswerPayload, RetrievalHit

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


def parse_chunking_request(chunking: dict | None) -> ChunkingRequest | None:
    if chunking is None:
        return None
    if not isinstance(chunking, dict):
        raise RAGValidationError("chunking must be an object")
    strategy = str(chunking.get("strategy", "")).strip().lower()
    version = chunking.get("version")
    if version is not None and not isinstance(version, str):
        raise RAGValidationError("chunking.version must be a string")
    numeric_fields = {
        "targetTokens": "target_tokens",
        "maxTokens": "max_tokens",
        "overlapTokens": "overlap_tokens",
        "minTokens": "min_tokens",
    }
    values: dict[str, int | str | None] = {
        "strategy": strategy,
        "version": version.strip() if isinstance(version, str) and version.strip() else None,
        "target_tokens": None,
        "max_tokens": None,
        "overlap_tokens": None,
        "min_tokens": None,
    }
    for key, mapped in numeric_fields.items():
        raw = chunking.get(key)
        if raw is None:
            raw = chunking.get(mapped)
        if raw is not None and not isinstance(raw, int):
            raise RAGValidationError(f"chunking.{key} must be an integer")
        values[mapped] = raw
    return ChunkingRequest(
        strategy=strategy,
        version=values["version"],
        target_tokens=values["target_tokens"],
        max_tokens=values["max_tokens"],
        overlap_tokens=values["overlap_tokens"],
        min_tokens=values["min_tokens"],
    )


def _chunking_plan_from_request(chunking_request: ChunkingRequest | None):
    if chunking_request:
        chunking_payload = {
            "strategy": chunking_request.strategy,
            "version": chunking_request.version,
            "target_tokens": chunking_request.target_tokens,
            "max_tokens": chunking_request.max_tokens,
            "overlap_tokens": chunking_request.overlap_tokens,
            "min_tokens": chunking_request.min_tokens,
        }
        payload = {"chunking": chunking_payload}
    else:
        payload = None
    return resolve_chunking_plan(payload=payload, config=current_app.config)


def _chunking_applied_payload(applied) -> dict:
    return {
        "requestedStrategy": applied.requested_strategy,
        "strategy": applied.strategy,
        "provider": applied.provider,
        "model": applied.model,
        "version": applied.version,
        "fallbackUsed": bool(applied.fallback_used),
        "fallbackReason": applied.fallback_reason,
    }


def _default_chunking_applied(*, requested_strategy: str, version: str):
    return build_chunking_applied(
        requested_strategy=requested_strategy,
        strategy=requested_strategy,
        provider="pending",
        model="pending",
        version=version,
        fallback_used=False,
        fallback_reason=None,
    )


def _hit_debug_payload(hit: RetrievalHit) -> dict[str, Any]:
    return {
        "chunkId": hit.chunk_id,
        "score": round(float(hit.score), 6),
        "source": hit.source,
        "page": hit.page,
        "section": hit.section,
        "contentPreview": str(hit.content or "")[:260],
        "metadata": hit.metadata if isinstance(hit.metadata, dict) else {},
    }


def _document_payload(document: RagDocument, *, chunk_count: int) -> dict[str, Any]:
    return {
        "id": document.id,
        "status": document.status,
        "sourceName": document.source_name,
        "fileName": document.file_name,
        "fileExtension": document.file_extension,
        "errorMessage": document.error_message,
        "embeddingModel": document.embedding_model,
        "embeddingVersion": document.embedding_version,
        "embeddingDimension": document.embedding_dimension,
        "chunkCount": int(chunk_count),
        "chunkingApplied": {
            "requestedStrategy": document.chunk_strategy or "paragraph",
            "strategy": document.chunk_strategy or "paragraph",
            "provider": document.chunk_provider or "pending",
            "model": document.chunk_model or "pending",
            "version": document.chunk_version or str(current_app.config.get("RAG_CHUNK_VERSION", "v1")),
            "fallbackUsed": bool(document.chunk_fallback_used),
            "fallbackReason": document.chunk_fallback_reason,
        },
        "createdAt": document.created_at.isoformat(),
        "updatedAt": document.updated_at.isoformat(),
        "indexedAt": document.indexed_at.isoformat() if document.indexed_at else None,
    }


def _query_chunk_counts(*, db, user_id: int, workspace_id: str, document_ids: list[int]) -> dict[int, int]:
    if not document_ids:
        return {}
    rows = (
        db.query(RagChunk.document_id, func.count(RagChunk.id))
        .filter(
            RagChunk.user_id == user_id,
            RagChunk.workspace_id == workspace_id,
            RagChunk.document_id.in_(document_ids),
        )
        .group_by(RagChunk.document_id)
        .all()
    )
    return {int(document_id): int(count) for document_id, count in rows}


def _clear_document_index_fields(document: RagDocument) -> None:
    document.embedding_model = None
    document.embedding_version = None
    document.embedding_dimension = None
    document.indexed_at = None


def _delete_document_vectors(*, workspace_id: str, document_id: int) -> None:
    vector_store = get_vector_store()
    vector_store.delete_document_chunks(
        workspace_id=workspace_id,
        collection_name=_collection_name_for_workspace(workspace_id),
        document_id=document_id,
    )


def _delete_document_file(document: RagDocument) -> None:
    file_path = Path(str(document.storage_path or "")).expanduser()
    if not file_path.exists():
        return
    try:
        file_path.unlink()
    except FileNotFoundError:
        return


def upload_document(*, user_id: int, workspace_id: str, file_storage, chunking: ChunkingRequest | None = None):
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

    plan = _chunking_plan_from_request(chunking)
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
            chunk_strategy=plan.request.strategy,
        )
        payload = {
            "id": document.id,
            "status": document.status,
            "workspaceId": document.workspace_id,
            "sourceName": document.source_name,
            "fileName": document.file_name,
            "fileExtension": document.file_extension,
            "createdAt": document.created_at.isoformat(),
            "chunkingApplied": _chunking_applied_payload(
                _default_chunking_applied(
                    requested_strategy=plan.request.strategy,
                    version=plan.request.version or str(current_app.config.get("RAG_CHUNK_VERSION", "v1")),
                )
            ),
        }

    if bool(current_app.config.get("RAG_AUTO_INDEX_ON_UPLOAD", True)):
        job_payload = enqueue_index_job(
            user_id=user_id,
            workspace_id=workspace,
            document_id=payload["id"],
            chunking=chunking,
        )
        payload["jobId"] = job_payload["jobId"]
        payload["jobStatus"] = job_payload["status"]
        payload["status"] = "indexing"
        payload["chunkingApplied"] = job_payload["chunkingApplied"]
    return payload


def enqueue_index_job(
    *,
    user_id: int,
    workspace_id: str,
    document_id: int,
    chunking: ChunkingRequest | None = None,
) -> dict:
    workspace = _workspace_from_request(workspace_id)
    plan = _chunking_plan_from_request(chunking)
    app = current_app._get_current_object()
    with session_scope() as db:
        document = get_document_for_scope(db=db, document_id=document_id, user_id=user_id, workspace_id=workspace)
        if document.status == "indexing":
            raise RAGValidationError("document is already indexing")
        set_document_status(document=document, status="indexing")
        document.chunk_strategy = plan.request.strategy
        job = create_index_job(db=db, document=document, requested_chunk_strategy=plan.request.strategy)
        job_payload = {
            "jobId": job.id,
            "documentId": document.id,
            "status": job.status,
            "chunkingApplied": _chunking_applied_payload(
                _default_chunking_applied(
                    requested_strategy=plan.request.strategy,
                    version=plan.request.version or str(current_app.config.get("RAG_CHUNK_VERSION", "v1")),
                )
            ),
        }

    if bool(app.config.get("TESTING", False)):
        _run_index_job(app, job_payload["jobId"], user_id, workspace, chunking)
    else:
        _ensure_executor().submit(_run_index_job, app, job_payload["jobId"], user_id, workspace, chunking)
    return job_payload


def reindex_document(
    *,
    user_id: int,
    workspace_id: str,
    document_id: int,
    chunking: ChunkingRequest | None = None,
) -> dict:
    return enqueue_index_job(
        user_id=user_id,
        workspace_id=workspace_id,
        document_id=document_id,
        chunking=chunking,
    )


def delete_document(*, user_id: int, workspace_id: str, document_id: int) -> dict:
    workspace = _workspace_from_request(workspace_id)
    with session_scope() as db:
        document = get_document_for_scope(db=db, document_id=document_id, user_id=user_id, workspace_id=workspace)
        ensure_document_deletable(document=document)
        document_payload = {
            "id": int(document.id),
            "workspaceId": document.workspace_id,
            "status": "deleted",
            "sourceName": document.source_name,
        }
        delete_document_chunks(db=db, document=document)
        _clear_document_index_fields(document)
        set_document_status(document=document, status="deleted")

    _delete_document_vectors(workspace_id=workspace, document_id=document_id)

    with session_scope() as db:
        document = get_document_for_scope(
            db=db,
            document_id=document_id,
            user_id=user_id,
            workspace_id=workspace,
            include_deleted=True,
        )
        _delete_document_file(document)

    return document_payload


def _run_index_job(
    app,
    job_id: int,
    user_id: int,
    workspace_id: str,
    chunking: ChunkingRequest | None = None,
) -> None:
    started = datetime.utcnow()
    chunk_count = 0
    chunking_applied = None
    document_id: int | None = None
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
                document_id = int(document.id)
                set_index_job_status(job=job, status="running")
                set_document_status(document=document, status="indexing")

            chunker = get_chunker()
            semantic_provider = get_semantic_chunking_provider()
            embedder = get_embedder()
            vector_store = get_vector_store()
            collection_name = _collection_name_for_workspace(workspace_id)
            chunk_payloads, chunking_applied = parse_and_chunk_document(
                file_path=document.storage_path,
                extension=document.file_extension,
                document_id=document.id,
                source_name=document.source_name,
                chunker=chunker,
                semantic_provider=semantic_provider,
                chunking_request=chunking,
                chunk_size=int(current_app.config["RAG_CHUNK_SIZE"]),
                overlap=int(current_app.config["RAG_CHUNK_OVERLAP"]),
            )
            for payload in chunk_payloads:
                payload.metadata["user_id"] = user_id
                payload.metadata["workspace_id"] = workspace_id
                payload.metadata["document_id"] = document.id
                if chunking_applied is not None:
                    payload.metadata["chunk_provider"] = chunking_applied.provider
                    payload.metadata["chunk_model"] = chunking_applied.model
            vectors = embedder.embed_documents([item.text for item in chunk_payloads])
            for vector in vectors:
                if len(vector) != embedder.dimension:
                    raise RAGValidationError("embedding dimension mismatch during indexing")

            vector_store.delete_document_chunks(
                workspace_id=workspace_id,
                collection_name=collection_name,
                document_id=document.id,
            )
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
                if chunking_applied is not None:
                    document.chunk_strategy = chunking_applied.strategy
                    document.chunk_provider = chunking_applied.provider
                    document.chunk_model = chunking_applied.model
                    document.chunk_version = chunking_applied.version
                    document.chunk_fallback_used = 1 if chunking_applied.fallback_used else 0
                    document.chunk_fallback_reason = chunking_applied.fallback_reason
                set_document_status(document=document, status="indexed", indexed_at=datetime.utcnow())
                set_index_job_status(
                    job=job,
                    status="done",
                    chunks_count=chunk_count,
                    applied_chunk_strategy=(chunking_applied.strategy if chunking_applied else None),
                    chunk_provider=(chunking_applied.provider if chunking_applied else None),
                    chunk_model=(chunking_applied.model if chunking_applied else None),
                    chunk_version=(chunking_applied.version if chunking_applied else None),
                    chunk_fallback_used=(chunking_applied.fallback_used if chunking_applied else False),
                    chunk_fallback_reason=(chunking_applied.fallback_reason if chunking_applied else None),
                    )
    except Exception as exc:
        logger.exception("RAG indexing job failed", extra={"job_id": job_id})
        with app.app_context():
            if document_id is not None:
                try:
                    _delete_document_vectors(workspace_id=workspace_id, document_id=document_id)
                except Exception:
                    logger.exception(
                        "Failed to clear document vectors after indexing failure",
                        extra={"job_id": job_id, "document_id": document_id},
                    )
            with session_scope() as db:
                try:
                    job = get_index_job_for_scope(db=db, job_id=job_id, user_id=user_id, workspace_id=workspace_id)
                    document = get_document_for_scope(
                        db=db,
                        document_id=job.document_id,
                        user_id=user_id,
                        workspace_id=workspace_id,
                    )
                    delete_document_chunks(db=db, document=document)
                    _clear_document_index_fields(document)
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
        requested_strategy = job.requested_chunk_strategy or "paragraph"
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
            "chunkingApplied": {
                "requestedStrategy": requested_strategy,
                "strategy": job.applied_chunk_strategy or requested_strategy,
                "provider": job.chunk_provider or "pending",
                "model": job.chunk_model or "pending",
                "version": job.chunk_version or str(current_app.config.get("RAG_CHUNK_VERSION", "v1")),
                "fallbackUsed": bool(job.chunk_fallback_used),
                "fallbackReason": job.chunk_fallback_reason,
            },
        }


def rag_search(
    *,
    user_id: int,
    workspace_id: str,
    query: str,
    top_k: int,
    filters: dict[str, str | int] | None = None,
    include_debug: bool = False,
) -> list[RetrievalHit] | tuple[list[RetrievalHit], dict[str, Any]]:
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
    latency_ms = 0
    hits: list[RetrievalHit] = []
    raw_hits: list[RetrievalHit] = []
    threshold_hits: list[RetrievalHit] = []
    query_vector: list[float] = []
    threshold = float(current_app.config.get("RAG_RETRIEVAL_SCORE_THRESHOLD", 0.0))
    try:
        query_vector = embedder.embed_query(text)
        if len(query_vector) != embedder.dimension:
            raise RAGValidationError("query embedding dimension mismatch")
        raw_hits = vector_store.query(
            workspace_id=workspace,
            collection_name=_collection_name_for_workspace(workspace),
            query_vector=query_vector,
            top_k=top_k,
            filters=scoped_filters,
        )
        threshold_hits = [hit for hit in raw_hits if hit.score >= threshold]
        hits = threshold_hits
        if reranker:
            hits = reranker.rerank(query=text, hits=hits, top_k=top_k)
    except Exception as exc:
        failure_reason = str(exc)
        raise
    finally:
        latency_ms = int((time.perf_counter() - start) * 1000)
        chunk_strategy = None
        chunk_provider = None
        chunk_model = None
        if hits:
            first_meta = hits[0].metadata if isinstance(hits[0].metadata, dict) else {}
            if isinstance(first_meta.get("chunk_strategy"), str):
                chunk_strategy = str(first_meta.get("chunk_strategy"))
            if isinstance(first_meta.get("chunk_provider"), str):
                chunk_provider = str(first_meta.get("chunk_provider"))
            if isinstance(first_meta.get("chunk_model"), str):
                chunk_model = str(first_meta.get("chunk_model"))
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
                chunk_strategy=chunk_strategy,
                chunk_provider=chunk_provider,
                chunk_model=chunk_model,
                failure_reason=failure_reason,
            )
    if include_debug:
        vector_norm = sum(value * value for value in query_vector) ** 0.5 if query_vector else 0.0
        debug_payload = {
            "query": text,
            "topK": top_k,
            "latencyMs": latency_ms,
            "filters": scoped_filters,
            "vector": {
                "vectorProvider": vector_store.provider_name,
                "embedderProvider": embedder.provider_name,
                "embeddingModel": embedder.model_name,
                "embeddingVersion": embedder.model_version,
                "embeddingDimension": embedder.dimension,
                "queryVectorNorm": round(vector_norm, 6),
                "queryVectorSample": [round(float(item), 6) for item in query_vector[:16]],
            },
            "retrieval": {
                "threshold": threshold,
                "rawCount": len(raw_hits),
                "afterThresholdCount": len(threshold_hits),
                "rawHits": [_hit_debug_payload(hit) for hit in raw_hits],
                "afterThresholdHits": [_hit_debug_payload(hit) for hit in threshold_hits],
            },
            "rerank": {
                "enabled": bool(reranker),
                "provider": str(getattr(reranker, "provider_name", "")) if reranker else "",
                "model": str(getattr(reranker, "model_name", "")) if reranker else "",
                "before": [_hit_debug_payload(hit) for hit in threshold_hits],
                "after": [_hit_debug_payload(hit) for hit in hits],
            },
        }
        return hits, debug_payload
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
        docs = list_documents_for_scope(db=db, user_id=user_id, workspace_id=workspace)
        document_ids = [int(doc.id) for doc in docs]
        chunk_count_map = _query_chunk_counts(db=db, user_id=user_id, workspace_id=workspace, document_ids=document_ids)
        return [_document_payload(doc, chunk_count=chunk_count_map.get(int(doc.id), 0)) for doc in docs]


def build_workspace_debug_snapshot(*, user_id: int, workspace_id: str, limit: int = 10) -> dict[str, Any]:
    workspace = _workspace_from_request(workspace_id)
    safe_limit = max(1, min(int(limit), 50))
    with session_scope() as db:
        documents = list_documents_for_scope(db=db, user_id=user_id, workspace_id=workspace)[:safe_limit]
        document_ids = [int(doc.id) for doc in documents]
        chunk_count_map = _query_chunk_counts(db=db, user_id=user_id, workspace_id=workspace, document_ids=document_ids)
        document_payloads = [
            _document_payload(doc, chunk_count=chunk_count_map.get(int(doc.id), 0))
            for doc in documents
        ]

        latest_chunk_previews: list[dict[str, Any]] = []
        if documents:
            latest_document_id = int(documents[0].id)
            latest_chunks = (
                db.query(RagChunk)
                .filter(
                    RagChunk.user_id == user_id,
                    RagChunk.workspace_id == workspace,
                    RagChunk.document_id == latest_document_id,
                )
                .order_by(RagChunk.id.asc())
                .limit(12)
                .all()
            )
            latest_chunk_previews = [
                {
                    "chunkId": chunk.chunk_id,
                    "source": chunk.source,
                    "page": chunk.page,
                    "section": chunk.section,
                    "tokenCount": chunk.token_count,
                    "startOffset": chunk.start_offset,
                    "endOffset": chunk.end_offset,
                    "contentPreview": str(chunk.content or "")[:260],
                }
                for chunk in latest_chunks
            ]

        jobs = (
            db.query(RagIndexJob)
            .filter(RagIndexJob.user_id == user_id, RagIndexJob.workspace_id == workspace)
            .order_by(RagIndexJob.created_at.desc())
            .limit(safe_limit)
            .all()
        )
        job_payloads = [
            {
                "jobId": job.id,
                "documentId": job.document_id,
                "status": job.status,
                "chunksCount": job.chunks_count,
                "errorStage": job.error_stage,
                "errorMessage": job.error_message,
                "startedAt": job.started_at.isoformat() if job.started_at else None,
                "finishedAt": job.finished_at.isoformat() if job.finished_at else None,
                "durationMs": job.duration_ms,
                "chunkingApplied": {
                    "requestedStrategy": job.requested_chunk_strategy or "paragraph",
                    "strategy": job.applied_chunk_strategy or job.requested_chunk_strategy or "paragraph",
                    "provider": job.chunk_provider or "pending",
                    "model": job.chunk_model or "pending",
                    "version": job.chunk_version or str(current_app.config.get("RAG_CHUNK_VERSION", "v1")),
                    "fallbackUsed": bool(job.chunk_fallback_used),
                    "fallbackReason": job.chunk_fallback_reason,
                },
            }
            for job in jobs
        ]

        return {
            "workspaceId": workspace,
            "documents": document_payloads,
            "latestDocumentChunks": latest_chunk_previews,
            "recentJobs": job_payloads,
            "totalDocuments": len(document_payloads),
            "indexedDocuments": len([item for item in document_payloads if item["status"] == "indexed"]),
        }


def get_chunk_embedding_debug(
    *,
    user_id: int,
    workspace_id: str,
    chunk_id: str,
    include_full: bool = False,
    sample_size: int = 16,
) -> dict[str, Any]:
    workspace = _workspace_from_request(workspace_id)
    normalized_chunk_id = str(chunk_id).strip()
    if not normalized_chunk_id:
        raise RAGValidationError("chunk_id is required")
    with session_scope() as db:
        chunk = (
            db.query(RagChunk)
            .filter(
                RagChunk.chunk_id == normalized_chunk_id,
                RagChunk.user_id == user_id,
                RagChunk.workspace_id == workspace,
            )
            .one_or_none()
        )
        if chunk is None:
            raise RAGValidationError("chunk not found")

    vector_store = get_vector_store()
    vector = vector_store.get_chunk_vector(
        workspace_id=workspace,
        collection_name=_collection_name_for_workspace(workspace),
        chunk_id=normalized_chunk_id,
    )
    if vector is None:
        raise RAGValidationError("embedding vector not found")

    safe_sample_size = max(1, min(int(sample_size), 256))
    norm = sum(value * value for value in vector) ** 0.5
    payload = {
        "workspaceId": workspace,
        "chunkId": normalized_chunk_id,
        "vectorProvider": vector_store.provider_name,
        "vectorDimension": len(vector),
        "vectorNorm": round(float(norm), 6),
        "vectorSample": [round(float(item), 6) for item in vector[:safe_sample_size]],
    }
    if include_full:
        payload["vector"] = [float(item) for item in vector]
    return payload
