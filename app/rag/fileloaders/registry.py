from __future__ import annotations

from pathlib import Path

from flask import current_app

from ..errors import RAGValidationError
from ..schemas import LoadedDocument
from .docx_loader import DocxFileLoader
from .interfaces import FileLoader
from .markdown_loader import MarkdownFileLoader
from .ocr.registry import get_ocr_provider
from .pdf_loader import PdfFileLoader
from .txt_loader import TxtFileLoader


def get_fileloader(extension: str) -> FileLoader:
    ext = str(extension or "").strip().lower().lstrip(".")
    version = str(current_app.config.get("RAG_FILELOADER_VERSION", "v1"))
    if ext == "txt":
        return TxtFileLoader(loader_version=version)
    if ext == "docx":
        return DocxFileLoader(loader_version=version)
    if ext == "md":
        return MarkdownFileLoader(loader_version=version)
    if ext == "pdf":
        return PdfFileLoader(loader_version=version, ocr_provider_factory=get_ocr_provider)
    raise RAGValidationError("unsupported document format")


def load_source_document(*, path: Path, extension: str, source_name: str) -> LoadedDocument:
    loader = get_fileloader(extension)
    return loader.load(path=path, source_name=source_name)
