from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from ..errors import RAGValidationError
from ..schemas import LoadedDocument, TextBlock
from .canonical import serialize_canonical_blocks
from .normalizers import normalize_plain_text


def _useful_character_ratio(text: str) -> float:
    if not text:
        return 0.0
    useful = 0
    for char in text:
        if char.isalnum() or "\u4e00" <= char <= "\u9fff":
            useful += 1
    return useful / max(1, len(text))


def _is_usable_pdf_text(text: str) -> bool:
    normalized = normalize_plain_text(text)
    if len(normalized) < 20:
        return False
    if _useful_character_ratio(normalized) < 0.35:
        return False
    if re.fullmatch(r"[\W_]+", normalized):
        return False
    return True


def _render_pdf_page_png(path: Path, page_index: int) -> bytes:
    try:
        import fitz
    except ImportError as exc:
        raise RAGValidationError("pdf OCR fallback requires pymupdf dependency") from exc

    document = fitz.open(str(path))
    try:
        page = document.load_page(int(page_index))
        pixmap = page.get_pixmap(dpi=180)
        return pixmap.tobytes("png")
    finally:
        document.close()


class PdfFileLoader:
    loader_type = "pdf"

    def __init__(self, *, loader_version: str, ocr_provider_factory: Callable[[], object | None]) -> None:
        self.loader_version = loader_version
        self._ocr_provider_factory = ocr_provider_factory

    def load(self, *, path: Path, source_name: str) -> LoadedDocument:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RAGValidationError("pdf parsing requires pypdf dependency") from exc

        reader = PdfReader(str(path))
        blocks: list[TextBlock] = []
        methods_used: set[str] = set()
        ocr_provider = None
        for idx, page in enumerate(reader.pages, start=1):
            native_text = normalize_plain_text(page.extract_text() or "")
            if _is_usable_pdf_text(native_text):
                methods_used.add("native")
                blocks.append(
                    TextBlock(
                        text=native_text,
                        metadata={"source": source_name, "page": idx, "extraction_method": "native"},
                    )
                )
                continue

            if ocr_provider is None:
                ocr_provider = self._ocr_provider_factory()
            if ocr_provider is None:
                raise RAGValidationError("ocr required for pdf page but OCR provider is unavailable")

            image_bytes = _render_pdf_page_png(path, idx - 1)
            ocr_text = normalize_plain_text(
                ocr_provider.recognize_page(
                    image_bytes=image_bytes,
                    mime_type="image/png",
                    source_name=source_name,
                    page_number=idx,
                )
            )
            if not ocr_text:
                raise RAGValidationError("ocr returned empty text for pdf page")
            methods_used.add("ocr")
            blocks.append(
                TextBlock(
                    text=ocr_text,
                    metadata={
                        "source": source_name,
                        "page": idx,
                        "extraction_method": "ocr",
                        "ocr_provider": str(getattr(ocr_provider, "provider_name", "unknown")),
                    },
                )
            )

        if not blocks:
            raise RAGValidationError("pdf produced no usable text")

        extraction_method = "mixed"
        if methods_used == {"native"}:
            extraction_method = "native"
        elif methods_used == {"ocr"}:
            extraction_method = "ocr"
        return LoadedDocument(
            loader_type=self.loader_type,
            loader_version=self.loader_version,
            extraction_method=extraction_method,
            blocks=blocks,
            derived_text=serialize_canonical_blocks(blocks),
            ocr_used="ocr" in methods_used,
            ocr_provider=(str(getattr(ocr_provider, "provider_name", "")) or None) if ocr_provider else None,
        )
