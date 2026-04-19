from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PdfTextExtractionResult:
    text: str = ""
    page_count: int | None = None
    extraction_method: str = ""
    ocr_used: bool = False
    ocr_provider: str | None = None
    parse_status: str = "failed"
    parse_error: str = ""

    @property
    def succeeded(self) -> bool:
        return self.parse_status == "parsed" and bool(self.text.strip())


def extract_pdf_text(
    path: Path,
    *,
    source_name: str | None = None,
    loader_version: str = "robotics-cache-v1",
    ocr_provider_factory: Callable[[], object | None] | None = None,
) -> PdfTextExtractionResult:
    try:
        from app.rag.fileloaders.pdf_loader import PdfFileLoader

        loader = PdfFileLoader(
            loader_version=loader_version,
            ocr_provider_factory=ocr_provider_factory or (lambda: None),
        )
        loaded = loader.load(path=Path(path), source_name=source_name or Path(path).name)
    except Exception as exc:
        return PdfTextExtractionResult(parse_error=str(exc))

    pages = {
        int(block.metadata["page"])
        for block in loaded.blocks
        if isinstance(getattr(block, "metadata", None), dict) and isinstance(block.metadata.get("page"), int)
    }
    text = "\n\n".join(block.text.strip() for block in loaded.blocks if str(block.text or "").strip())
    return PdfTextExtractionResult(
        text=text,
        page_count=len(pages) if pages else len(loaded.blocks),
        extraction_method=str(loaded.extraction_method or ""),
        ocr_used=bool(loaded.ocr_used),
        ocr_provider=loaded.ocr_provider,
        parse_status="parsed" if text.strip() else "failed",
        parse_error="" if text.strip() else "PDF produced no usable text",
    )


def extraction_result_to_metadata(result: PdfTextExtractionResult) -> dict[str, Any]:
    return {
        "pageCount": result.page_count,
        "extractionMethod": result.extraction_method,
        "ocrUsed": result.ocr_used,
        "ocrProvider": result.ocr_provider,
        "parseStatus": result.parse_status,
        "parseError": result.parse_error,
    }
