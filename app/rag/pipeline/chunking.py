from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..errors import RAGChunkingError, RAGValidationError
from ..schemas import ChunkPayload, ChunkingApplied, ChunkingBounds, ChunkingRequest, SemanticSegment


ALLOWED_CHUNK_STRATEGIES = {"paragraph", "semantic_llm"}


@dataclass(slots=True)
class ChunkingPlan:
    request: ChunkingRequest
    bounds: ChunkingBounds
    allowed: set[str]
    fallback_strategy: str


def resolve_chunking_plan(*, payload: dict | None, config) -> ChunkingPlan:
    chunking = payload.get("chunking") if isinstance(payload, dict) else None
    requested_strategy = ""
    version = None
    target_tokens = None
    max_tokens = None
    overlap_tokens = None
    min_tokens = None
    if isinstance(chunking, dict):
        strategy_raw = chunking.get("strategy")
        if isinstance(strategy_raw, str):
            requested_strategy = strategy_raw.strip().lower()
        version_raw = chunking.get("version")
        if isinstance(version_raw, str) and version_raw.strip():
            version = version_raw.strip()
        for key in ("targetTokens", "maxTokens", "overlapTokens", "minTokens"):
            raw = chunking.get(key)
            if raw is not None and not isinstance(raw, int):
                raise RAGValidationError(f"chunking.{key} must be an integer")
        target_tokens = chunking.get("targetTokens")
        if target_tokens is None:
            target_tokens = chunking.get("target_tokens")
        max_tokens = chunking.get("maxTokens")
        if max_tokens is None:
            max_tokens = chunking.get("max_tokens")
        overlap_tokens = chunking.get("overlapTokens")
        if overlap_tokens is None:
            overlap_tokens = chunking.get("overlap_tokens")
        min_tokens = chunking.get("minTokens")
        if min_tokens is None:
            min_tokens = chunking.get("min_tokens")

    default_strategy = str(config.get("RAG_CHUNK_STRATEGY_DEFAULT", "paragraph")).strip().lower()
    strategy = requested_strategy or default_strategy
    allowed = {str(item).strip().lower() for item in config.get("RAG_CHUNK_STRATEGY_ALLOWED", ())}
    allowed = {item for item in allowed if item}
    if not allowed:
        allowed = {"paragraph"}
    if strategy not in ALLOWED_CHUNK_STRATEGIES or strategy not in allowed:
        raise RAGValidationError(f"chunking strategy is invalid; allowed: {', '.join(sorted(allowed))}")

    fallback = str(config.get("RAG_CHUNK_FALLBACK_STRATEGY", "paragraph")).strip().lower()
    if fallback not in ALLOWED_CHUNK_STRATEGIES:
        raise RAGValidationError("RAG_CHUNK_FALLBACK_STRATEGY is invalid")
    if fallback not in allowed:
        raise RAGValidationError("RAG_CHUNK_FALLBACK_STRATEGY must be present in RAG_CHUNK_STRATEGY_ALLOWED")

    bounds = ChunkingBounds(
        target_tokens=max(32, int(target_tokens or config.get("RAG_CHUNK_SEMANTIC_TARGET_TOKENS", 450))),
        max_tokens=max(32, int(max_tokens or config.get("RAG_CHUNK_SEMANTIC_MAX_TOKENS", 700))),
        overlap_tokens=max(0, int(overlap_tokens or config.get("RAG_CHUNK_SEMANTIC_OVERLAP_TOKENS", 50))),
        min_tokens=max(1, int(min_tokens or config.get("RAG_CHUNK_SEMANTIC_MIN_TOKENS", 120))),
    )
    if bounds.max_tokens < bounds.target_tokens:
        bounds.max_tokens = bounds.target_tokens
    if bounds.target_tokens < bounds.min_tokens:
        bounds.target_tokens = bounds.min_tokens
    if bounds.overlap_tokens >= bounds.max_tokens:
        bounds.overlap_tokens = max(0, bounds.max_tokens // 8)

    return ChunkingPlan(
        request=ChunkingRequest(
            strategy=strategy,
            version=version,
            target_tokens=bounds.target_tokens,
            max_tokens=bounds.max_tokens,
            overlap_tokens=bounds.overlap_tokens,
            min_tokens=bounds.min_tokens,
        ),
        bounds=bounds,
        allowed=allowed,
        fallback_strategy=fallback,
    )


def estimate_tokens(text: str) -> int:
    words = [item for item in text.strip().split() if item]
    if words:
        return max(1, int(len(words) * 1.35))
    # CJK fallback approximation
    return max(1, len(text.strip()) // 2)


def _split_text_by_max_tokens(text: str, max_tokens: int) -> list[tuple[str, int, int]]:
    clean = text.strip()
    if not clean:
        return []
    if estimate_tokens(clean) <= max_tokens:
        return [(clean, 0, len(clean))]
    parts: list[tuple[str, int, int]] = []
    step_chars = max(32, max_tokens * 2)
    start = 0
    while start < len(clean):
        end = min(len(clean), start + step_chars)
        piece = clean[start:end].strip()
        if piece:
            parts.append((piece, start, end))
        if end >= len(clean):
            break
        start = end
    return parts


def _merge_short_segments(segments: list[SemanticSegment], min_tokens: int) -> list[SemanticSegment]:
    merged: list[SemanticSegment] = []
    for segment in segments:
        if merged and estimate_tokens(segment.text) < min_tokens:
            prev = merged[-1]
            prev.text = f"{prev.text}\n{segment.text}".strip()
            if not prev.summary and segment.summary:
                prev.summary = segment.summary
            if not prev.topic and segment.topic:
                prev.topic = segment.topic
            continue
        merged.append(
            SemanticSegment(
                text=segment.text,
                metadata=dict(segment.metadata),
                topic=segment.topic,
                summary=segment.summary,
            )
        )
    return merged


def enforce_semantic_bounds(*, segments: list[SemanticSegment], bounds: ChunkingBounds) -> list[SemanticSegment]:
    staged = _merge_short_segments(segments, bounds.min_tokens)
    bounded: list[SemanticSegment] = []
    for segment in staged:
        pieces = _split_text_by_max_tokens(segment.text, bounds.max_tokens)
        if not pieces:
            continue
        for text, start, end in pieces:
            metadata = dict(segment.metadata)
            base_start = int(metadata.get("offset_start", 0))
            metadata["offset_start"] = base_start + start
            metadata["offset_end"] = base_start + end
            bounded.append(
                SemanticSegment(
                    text=text,
                    metadata=metadata,
                    topic=segment.topic,
                    summary=segment.summary,
                )
            )
    return bounded


def semantic_segments_to_payloads(
    *,
    segments: list[SemanticSegment],
    document_id: int,
    source_name: str,
    strategy: str,
    version: str,
) -> list[ChunkPayload]:
    payloads: list[ChunkPayload] = []
    for idx, segment in enumerate(segments):
        text = str(segment.text).strip()
        if not text:
            continue
        metadata = dict(segment.metadata)
        metadata["source"] = source_name
        metadata["document_id"] = document_id
        metadata["chunk_strategy"] = strategy
        metadata["chunk_version"] = version
        if segment.topic:
            metadata["topic"] = segment.topic
        if segment.summary:
            metadata["summary"] = segment.summary
        metadata["token_count"] = estimate_tokens(text)
        if "offset_start" not in metadata:
            metadata["offset_start"] = 0
        if "offset_end" not in metadata:
            metadata["offset_end"] = len(text)
        chunk_id = hashlib.sha1(
            f"{document_id}:{strategy}:{version}:{idx}:{text}".encode("utf-8")
        ).hexdigest()
        payloads.append(ChunkPayload(chunk_id=chunk_id, text=text, metadata=metadata))
    return payloads


def ensure_semantic_output(segments: list[SemanticSegment], strategy: str) -> None:
    if not isinstance(segments, list):
        raise RAGChunkingError(f"{strategy} provider output must be a list")
    if not segments:
        raise RAGChunkingError(f"{strategy} provider returned empty segments")
    for idx, segment in enumerate(segments):
        if not isinstance(segment, SemanticSegment):
            raise RAGChunkingError(f"{strategy} segment at index {idx} has invalid type")
        if not str(segment.text).strip():
            raise RAGChunkingError(f"{strategy} segment at index {idx} has empty text")


def build_chunking_applied(
    *,
    requested_strategy: str,
    strategy: str,
    provider: str,
    model: str,
    version: str,
    fallback_used: bool,
    fallback_reason: str | None,
) -> ChunkingApplied:
    return ChunkingApplied(
        requested_strategy=requested_strategy,
        strategy=strategy,
        provider=provider,
        model=model,
        version=version,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )
