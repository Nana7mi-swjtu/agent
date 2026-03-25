from __future__ import annotations

from pathlib import Path

from ..errors import RAGValidationError
from ..pipeline.parsers import parse_document_file
from ..schemas import ChunkPayload, TextBlock


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
    chunk_size: int,
    overlap: int,
) -> list[ChunkPayload]:
    blocks = parse_document_file(Path(file_path), extension)
    normalized = normalize_blocks(blocks)
    return chunker.chunk(
        document_id=document_id,
        source_name=source_name,
        blocks=normalized,
        chunk_size=chunk_size,
        overlap=overlap,
    )
