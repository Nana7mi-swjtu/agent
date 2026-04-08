from __future__ import annotations

import json

from ..errors import RAGValidationError
from ..schemas import TextBlock

_BLOCK_START = "<<<RAG_BLOCK "
_BLOCK_END = "<<<END_RAG_BLOCK>>>"


def serialize_canonical_blocks(blocks: list[TextBlock]) -> str:
    parts: list[str] = []
    for block in blocks:
        header = json.dumps(block.metadata, ensure_ascii=False, sort_keys=True)
        text = str(block.text or "").strip()
        if not text:
            continue
        parts.append(f"{_BLOCK_START}{header}>>>")
        parts.append(text)
        parts.append(_BLOCK_END)
    return "\n".join(parts).strip()


def parse_canonical_text(raw: str) -> list[TextBlock]:
    lines = str(raw or "").splitlines()
    blocks: list[TextBlock] = []
    current_metadata: dict | None = None
    current_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(_BLOCK_START) and stripped.endswith(">>>"):
            if current_metadata is not None:
                raise RAGValidationError("canonical text asset is malformed")
            payload = stripped[len(_BLOCK_START) : -3]
            try:
                metadata = json.loads(payload)
            except Exception as exc:
                raise RAGValidationError("canonical text asset metadata is invalid") from exc
            if not isinstance(metadata, dict):
                raise RAGValidationError("canonical text asset metadata must be an object")
            current_metadata = metadata
            current_lines = []
            continue
        if stripped == _BLOCK_END:
            if current_metadata is None:
                raise RAGValidationError("canonical text asset is malformed")
            text = "\n".join(current_lines).strip()
            if text:
                blocks.append(TextBlock(text=text, metadata=dict(current_metadata)))
            current_metadata = None
            current_lines = []
            continue
        if current_metadata is not None:
            current_lines.append(line)
    if current_metadata is not None:
        raise RAGValidationError("canonical text asset is incomplete")
    return blocks
