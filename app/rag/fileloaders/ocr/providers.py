from __future__ import annotations

import json
from base64 import b64encode
from urllib import request as urllib_request

from ...errors import RAGConfigurationError, RAGValidationError


class OpenAICompatibleOCRProvider:
    provider_name = "openai-compatible"
    model_version = "1"

    def __init__(self, *, model_name: str, api_key: str, base_url: str, timeout_seconds: int) -> None:
        if not model_name.strip():
            raise RAGConfigurationError("RAG_OCR_MODEL must be configured")
        if not api_key.strip():
            raise RAGConfigurationError("RAG_OCR_API_KEY must be configured")
        if not base_url.strip():
            raise RAGConfigurationError("RAG_OCR_BASE_URL must be configured")
        self.model_name = model_name.strip()
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = max(1, int(timeout_seconds))

    def recognize_page(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        source_name: str,
        page_number: int,
    ) -> str:
        image_b64 = b64encode(bytes(image_bytes)).decode("ascii")
        prompt = (
            "Extract all visible text from this page.\n"
            "Return plain text only.\n"
            "Preserve natural reading order.\n"
            "Do not add commentary.\n"
            f"Source: {source_name}\n"
            f"Page: {page_number}\n"
        )
        body = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
                    ],
                }
            ],
        }
        req = urllib_request.Request(
            url=f"{self._base_url}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self._timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise RAGValidationError(f"openai-compatible OCR request failed: {exc}") from exc
        try:
            content = payload["choices"][0]["message"]["content"]
        except Exception as exc:
            raise RAGValidationError("openai-compatible OCR provider returned invalid response payload") from exc
        if isinstance(content, list):
            text_parts = [str(item.get("text", "")) for item in content if isinstance(item, dict) and item.get("type") == "text"]
            content = "\n".join(part for part in text_parts if part.strip())
        text = str(content or "").strip()
        if not text:
            raise RAGValidationError("openai-compatible OCR provider returned empty text")
        return text


class FakeOCRProvider:
    provider_name = "fake"
    model_name = "fake-ocr"
    model_version = "1"

    def recognize_page(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        source_name: str,
        page_number: int,
    ) -> str:
        _ = image_bytes, mime_type
        return f"OCR text for {source_name} page {int(page_number)}"
