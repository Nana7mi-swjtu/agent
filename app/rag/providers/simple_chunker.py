from __future__ import annotations

import hashlib

from ..schemas import ChunkPayload


class DeterministicChunker:
    provider_name = "deterministic"

    def chunk(
        self,
        *,
        document_id: int,
        source_name: str,
        blocks: list[dict],
        chunk_size: int,
        overlap: int,
    ) -> list[ChunkPayload]:
        merged: list[ChunkPayload] = []
        step = max(1, chunk_size - max(0, overlap))
        for block_index, block in enumerate(blocks):
            text = str(block.get("text", "")).strip()
            if not text:
                continue
            start = 0
            while start < len(text):
                end = min(len(text), start + chunk_size)
                chunk_text = text[start:end].strip()
                if chunk_text:
                    chunk_id = hashlib.sha1(
                        f"{document_id}:{block_index}:{start}:{end}:{chunk_text}".encode("utf-8")
                    ).hexdigest()
                    metadata = dict(block.get("metadata", {}))
                    metadata["source"] = source_name
                    metadata["document_id"] = document_id
                    metadata["block_index"] = block_index
                    metadata["offset_start"] = start
                    metadata["offset_end"] = end
                    merged.append(
                        ChunkPayload(
                            chunk_id=chunk_id,
                            text=chunk_text,
                            metadata=metadata,
                        )
                    )
                if end >= len(text):
                    break
                start += step
        return merged
