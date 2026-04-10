from __future__ import annotations

from flask import current_app

from ...errors import RAGConfigurationError
from .interfaces import OCRProvider
from .providers import FakeOCRProvider, OpenAICompatibleOCRProvider


def get_ocr_provider() -> OCRProvider | None:
    provider = str(current_app.config.get("RAG_OCR_PROVIDER", "openai-compatible")).strip().lower()
    if provider in {"", "disabled", "none"}:
        return None
    if provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleOCRProvider(
            model_name=str(current_app.config.get("RAG_OCR_MODEL", "")),
            api_key=str(current_app.config.get("RAG_OCR_API_KEY", "")),
            base_url=str(current_app.config.get("RAG_OCR_BASE_URL", "")),
            timeout_seconds=int(current_app.config.get("RAG_OCR_TIMEOUT_SECONDS", 20)),
        )
    if provider == "fake":
        return FakeOCRProvider()
    raise RAGConfigurationError(f"unsupported OCR provider: {provider}")
