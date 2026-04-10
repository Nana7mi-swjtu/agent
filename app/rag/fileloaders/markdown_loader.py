from __future__ import annotations

from pathlib import Path

from ..schemas import LoadedDocument
from .canonical import serialize_canonical_blocks
from .normalizers import normalize_markdown_to_blocks


class MarkdownFileLoader:
    loader_type = "markdown"

    def __init__(self, *, loader_version: str) -> None:
        self.loader_version = loader_version

    def load(self, *, path: Path, source_name: str) -> LoadedDocument:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        blocks = normalize_markdown_to_blocks(source_name=source_name, raw=raw)
        return LoadedDocument(
            loader_type=self.loader_type,
            loader_version=self.loader_version,
            extraction_method="structured_markdown",
            blocks=blocks,
            derived_text=serialize_canonical_blocks(blocks),
        )
