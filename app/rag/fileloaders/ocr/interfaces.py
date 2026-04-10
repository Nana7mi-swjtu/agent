from __future__ import annotations

from typing import Protocol


class OCRProvider(Protocol):
    provider_name: str
    model_name: str
    model_version: str

    def recognize_page(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        source_name: str,
        page_number: int,
    ) -> str: ...
