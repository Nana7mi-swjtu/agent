from __future__ import annotations

from pathlib import Path

from ..schemas import LoadedDocument, TextBlock
from .canonical import serialize_canonical_blocks
from .normalizers import normalize_plain_text


class TxtFileLoader:
    loader_type = "txt"

    def __init__(self, *, loader_version: str) -> None:
        self.loader_version = loader_version

    def load(self, *, path: Path, source_name: str) -> LoadedDocument:
        text = normalize_plain_text(path.read_text(encoding="utf-8", errors="ignore"))
        blocks = [TextBlock(text=text, metadata={"source": source_name})] if text else []
        return LoadedDocument(
            loader_type=self.loader_type,
            loader_version=self.loader_version,
            extraction_method="plain_text",
            blocks=blocks,
            derived_text=serialize_canonical_blocks(blocks),
        )
