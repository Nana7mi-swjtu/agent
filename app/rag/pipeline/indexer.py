from __future__ import annotations

from pathlib import Path

from flask import current_app

from ..errors import RAGChunkingError, RAGValidationError
from ..pipeline.parsers import parse_document_file
from ..schemas import ChunkPayload, ChunkingApplied, ChunkingRequest, TextBlock
from .chunking import (
    build_chunking_applied,
    enforce_semantic_bounds,
    ensure_semantic_output,
    resolve_chunking_plan,
    semantic_segments_to_payloads,
)


def normalize_blocks(blocks: list[TextBlock]) -> list[dict]:
    normalized: list[dict] = []
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        metadata = dict(block.metadata)
        if not metadata.get("source"):
            raise RAGValidationError("normalized text block missing source metadata")
        normalized.append({"text": text, "metadata": metadata})
    return normalized


def parse_and_chunk_document(
    *,
    file_path: str,
    extension: str,
    document_id: int,
    source_name: str,
    chunker,
    semantic_provider,
    chunking_request: ChunkingRequest | None,
    chunk_size: int,
    overlap: int,
) -> tuple[list[ChunkPayload], ChunkingApplied]:
    blocks = parse_document_file(Path(file_path), extension)
    normalized = normalize_blocks(blocks)
    chunking_payload = None
    if chunking_request is not None:
        chunking_payload = {
            "strategy": chunking_request.strategy,
            "version": chunking_request.version,
            "target_tokens": chunking_request.target_tokens,
            "max_tokens": chunking_request.max_tokens,
            "overlap_tokens": chunking_request.overlap_tokens,
            "min_tokens": chunking_request.min_tokens,
        }
    plan = resolve_chunking_plan(payload={"chunking": chunking_payload} if chunking_payload else None, config=current_app.config)
    requested_strategy = plan.request.strategy
    version = plan.request.version or str(current_app.config.get("RAG_CHUNK_VERSION", "v1"))

    if requested_strategy == "paragraph":
        payloads = chunker.chunk(
            document_id=document_id,
            source_name=source_name,
            blocks=normalized,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        for payload in payloads:
            payload.metadata["chunk_strategy"] = "paragraph"
            payload.metadata["chunk_version"] = version
        applied = build_chunking_applied(
            requested_strategy=requested_strategy,
            strategy="paragraph",
            provider=chunker.provider_name,
            model=chunker.provider_name,
            version=version,
            fallback_used=False,
            fallback_reason=None,
        )
        return payloads, applied

    fallback_reason = None
    try:
        segments = semantic_provider.segment(
            strategy=requested_strategy,
            source_name=source_name,
            blocks=normalized,
        )
        ensure_semantic_output(segments, requested_strategy)
        bounded = enforce_semantic_bounds(segments=segments, bounds=plan.bounds)
        payloads = semantic_segments_to_payloads(
            segments=bounded,
            document_id=document_id,
            source_name=source_name,
            strategy=requested_strategy,
            version=version,
        )
        if not payloads:
            raise RAGChunkingError(f"{requested_strategy} generated no chunk payloads")
        applied = build_chunking_applied(
            requested_strategy=requested_strategy,
            strategy=requested_strategy,
            provider=semantic_provider.provider_name,
            model=semantic_provider.model_name,
            version=version,
            fallback_used=False,
            fallback_reason=None,
        )
        return payloads, applied
    except RAGChunkingError as exc:
        fallback = plan.fallback_strategy
        if fallback != "paragraph":
            raise
        fallback_reason = str(exc)
        payloads = chunker.chunk(
            document_id=document_id,
            source_name=source_name,
            blocks=normalized,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        for payload in payloads:
            payload.metadata["chunk_strategy"] = "paragraph"
            payload.metadata["chunk_version"] = version
        applied = build_chunking_applied(
            requested_strategy=requested_strategy,
            strategy="paragraph",
            provider=chunker.provider_name,
            model=chunker.provider_name,
            version=version,
            fallback_used=True,
            fallback_reason=fallback_reason,
        )
        return payloads, applied
