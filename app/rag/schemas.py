from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TextBlock:
    text: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class LoadedDocument:
    loader_type: str
    loader_version: str
    extraction_method: str
    blocks: list[TextBlock]
    derived_text: str
    ocr_used: bool = False
    ocr_provider: str | None = None
    warnings: list[str] | None = None


@dataclass(slots=True)
class ChunkPayload:
    chunk_id: str
    text: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class RetrievalHit:
    chunk_id: str
    score: float
    source: str
    page: int | None
    section: str | None
    content: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class RAGAnswerPayload:
    reply: str
    used_rag: bool
    no_evidence: bool
    citations: list[dict[str, Any]]


@dataclass(slots=True)
class IndexResult:
    status: str
    error_message: str | None
    chunks_count: int
    finished_at: datetime


@dataclass(slots=True)
class ChunkingRequest:
    strategy: str
    version: str | None
    target_tokens: int | None
    max_tokens: int | None
    overlap_tokens: int | None
    min_tokens: int | None


@dataclass(slots=True)
class ChunkingApplied:
    requested_strategy: str
    strategy: str
    provider: str
    model: str
    version: str
    fallback_used: bool
    fallback_reason: str | None = None


@dataclass(slots=True)
class ChunkingBounds:
    target_tokens: int
    max_tokens: int
    overlap_tokens: int
    min_tokens: int


@dataclass(slots=True)
class SemanticSegment:
    text: str
    metadata: dict[str, Any]
    topic: str | None = None
    summary: str | None = None
