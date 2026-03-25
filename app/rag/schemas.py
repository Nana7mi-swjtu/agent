from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TextBlock:
    text: str
    metadata: dict[str, Any]


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
