from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument
from .base import SourceCollectionResult


PdfTextExtractor = Callable[[Path], str]


class CninfoAnnouncementAdapter:
    source_type = "cninfo_announcement"
    source_name = "巨潮资讯网"

    def __init__(
        self,
        documents: list[SourceDocument] | None = None,
        *,
        pdf_text_extractor: PdfTextExtractor | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        self._documents = list(documents or [])
        self._pdf_text_extractor = pdf_text_extractor
        self._timeout_seconds = int(timeout_seconds)

    def collect(
        self,
        *,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
    ) -> SourceCollectionResult:
        if self._documents:
            return SourceCollectionResult(documents=[_normalize_cninfo_document(item) for item in self._documents])
        return SourceCollectionResult(
            documents=[],
            limitations=["巨潮资讯网适配器尚未配置实时公告查询，未返回企业公告证据。"],
        )

    def extract_pdf_text(self, pdf_url: str) -> str:
        if self._pdf_text_extractor is None:
            return ""
        request = Request(str(pdf_url), headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cninfo.com.cn/"})
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                data = response.read()
        except URLError:
            return ""
        if not data:
            return ""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(data)
            temp_path = Path(handle.name)
        try:
            return self._pdf_text_extractor(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)


def _normalize_cninfo_document(document: SourceDocument) -> SourceDocument:
    return SourceDocument(
        id=document.id,
        source_type="cninfo_announcement",
        source_name=document.source_name or CninfoAnnouncementAdapter.source_name,
        title=document.title,
        content=document.content,
        url=document.url,
        published_at=document.published_at,
        authority_score=float(document.authority_score or 0.95),
        relevance_scope=document.relevance_scope or "enterprise",
        metadata=document.metadata,
    )
