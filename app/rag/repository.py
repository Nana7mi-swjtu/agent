from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select

from ..models import RagChunk, RagDocument, RagIndexJob, RagQueryLog
from .errors import RAGAuthorizationError, RAGValidationError

ALLOWED_DOCUMENT_STATUSES = {"uploaded", "indexing", "indexed", "failed", "deleted"}
ALLOWED_INDEX_JOB_STATUSES = {"pending", "running", "done", "failed"}


def create_document(
    *,
    db,
    user_id: int,
    workspace_id: str,
    source_name: str,
    file_name: str,
    file_extension: str,
    mime_type: str,
    storage_path: str,
    chunk_strategy: str | None = None,
) -> RagDocument:
    doc = RagDocument(
        user_id=user_id,
        workspace_id=workspace_id,
        source_name=source_name,
        file_name=file_name,
        file_extension=file_extension.lower(),
        mime_type=mime_type,
        storage_path=storage_path,
        status="uploaded",
        chunk_strategy=chunk_strategy,
    )
    db.add(doc)
    db.flush()
    return doc


def get_document_for_scope(*, db, document_id: int, user_id: int, workspace_id: str) -> RagDocument:
    document = db.execute(select(RagDocument).where(RagDocument.id == document_id)).scalar_one_or_none()
    if document is None:
        raise RAGValidationError("document not found")
    if document.user_id != user_id or document.workspace_id != workspace_id:
        raise RAGAuthorizationError("document is outside authorized scope")
    return document


def set_document_status(
    *,
    document: RagDocument,
    status: str,
    error_message: str | None = None,
    indexed_at: datetime | None = None,
) -> None:
    if status not in ALLOWED_DOCUMENT_STATUSES:
        raise RAGValidationError("invalid document status")
    if document.status == "deleted" and status != "deleted":
        raise RAGValidationError("deleted document cannot transition to active state")
    document.status = status
    document.error_message = error_message
    if status == "indexed":
        document.indexed_at = indexed_at or datetime.utcnow()
    if status == "deleted":
        document.deleted_at = datetime.utcnow()


def create_index_job(
    *,
    db,
    document: RagDocument,
    requested_chunk_strategy: str | None = None,
) -> RagIndexJob:
    if document.status == "deleted":
        raise RAGValidationError("cannot index deleted document")
    job = RagIndexJob(
        document_id=document.id,
        user_id=document.user_id,
        workspace_id=document.workspace_id,
        status="pending",
        requested_chunk_strategy=requested_chunk_strategy,
    )
    db.add(job)
    db.flush()
    return job


def get_index_job_for_scope(*, db, job_id: int, user_id: int, workspace_id: str) -> RagIndexJob:
    job = db.execute(select(RagIndexJob).where(RagIndexJob.id == job_id)).scalar_one_or_none()
    if job is None:
        raise RAGValidationError("index job not found")
    if job.user_id != user_id or job.workspace_id != workspace_id:
        raise RAGAuthorizationError("index job is outside authorized scope")
    return job


def set_index_job_status(
    *,
    job: RagIndexJob,
    status: str,
    error_stage: str | None = None,
    error_message: str | None = None,
    chunks_count: int | None = None,
    applied_chunk_strategy: str | None = None,
    chunk_provider: str | None = None,
    chunk_model: str | None = None,
    chunk_version: str | None = None,
    chunk_fallback_used: bool | None = None,
    chunk_fallback_reason: str | None = None,
) -> None:
    if status not in ALLOWED_INDEX_JOB_STATUSES:
        raise RAGValidationError("invalid index job status")
    now = datetime.utcnow()
    if status == "running":
        if job.started_at is None:
            job.started_at = now
    if status in {"done", "failed"}:
        if job.started_at is None:
            job.started_at = now
        job.finished_at = now
        job.duration_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)
    job.status = status
    job.error_stage = error_stage
    job.error_message = error_message
    if chunks_count is not None:
        job.chunks_count = max(0, chunks_count)
    if applied_chunk_strategy is not None:
        job.applied_chunk_strategy = applied_chunk_strategy
    if chunk_provider is not None:
        job.chunk_provider = chunk_provider
    if chunk_model is not None:
        job.chunk_model = chunk_model
    if chunk_version is not None:
        job.chunk_version = chunk_version
    if chunk_fallback_used is not None:
        job.chunk_fallback_used = 1 if chunk_fallback_used else 0
    if chunk_fallback_reason is not None:
        job.chunk_fallback_reason = chunk_fallback_reason


def replace_document_chunks(*, db, document: RagDocument, chunks: list[RagChunk]) -> None:
    db.execute(delete(RagChunk).where(RagChunk.document_id == document.id))
    for chunk in chunks:
        db.add(chunk)


def create_chunk_entities(
    *,
    document: RagDocument,
    chunk_payloads: list,
    embedding_model: str,
    embedding_version: str,
    embedding_dimension: int,
) -> list[RagChunk]:
    entities: list[RagChunk] = []
    for payload in chunk_payloads:
        metadata = dict(payload.metadata)
        entities.append(
            RagChunk(
                document_id=document.id,
                user_id=document.user_id,
                workspace_id=document.workspace_id,
                chunk_id=payload.chunk_id,
                content=payload.text,
                source=str(metadata.get("source", document.source_name)),
                page=int(metadata["page"]) if isinstance(metadata.get("page"), int) else None,
                section=str(metadata["section"]) if isinstance(metadata.get("section"), str) else None,
                topic=str(metadata["topic"]) if isinstance(metadata.get("topic"), str) else None,
                summary=str(metadata["summary"]) if isinstance(metadata.get("summary"), str) else None,
                token_count=int(metadata["token_count"]) if isinstance(metadata.get("token_count"), int) else None,
                start_offset=int(metadata["offset_start"]) if isinstance(metadata.get("offset_start"), int) else None,
                end_offset=int(metadata["offset_end"]) if isinstance(metadata.get("offset_end"), int) else None,
                strategy_version=(
                    str(metadata["chunk_version"]) if isinstance(metadata.get("chunk_version"), str) else None
                ),
                metadata_json=metadata,
                embedding_model=embedding_model,
                embedding_version=embedding_version,
                embedding_dimension=embedding_dimension,
            )
        )
    return entities


def create_query_log(
    *,
    db,
    user_id: int,
    workspace_id: str,
    query_text: str,
    top_k: int,
    hit_count: int,
    latency_ms: int,
    top_scores: list[float],
    filters: dict,
    vector_provider: str,
    embedder_provider: str,
    embedding_model: str,
    embedding_version: str,
    embedding_dimension: int,
    chunk_strategy: str | None = None,
    chunk_provider: str | None = None,
    chunk_model: str | None = None,
    failure_reason: str | None = None,
) -> None:
    db.add(
        RagQueryLog(
            user_id=user_id,
            workspace_id=workspace_id,
            query_text=query_text,
            top_k=top_k,
            hit_count=hit_count,
            latency_ms=latency_ms,
            top_scores={"scores": top_scores},
            filters=filters,
            vector_provider=vector_provider,
            embedder_provider=embedder_provider,
            embedding_model=embedding_model,
            embedding_version=embedding_version,
            embedding_dimension=embedding_dimension,
            chunk_strategy=chunk_strategy,
            chunk_provider=chunk_provider,
            chunk_model=chunk_model,
            failure_reason=failure_reason,
        )
    )
