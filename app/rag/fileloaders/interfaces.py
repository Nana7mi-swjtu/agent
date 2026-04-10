from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..schemas import LoadedDocument


class FileLoader(Protocol):
    loader_type: str
    loader_version: str

    def load(self, *, path: Path, source_name: str) -> LoadedDocument: ...
