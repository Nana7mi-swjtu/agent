from __future__ import annotations

from ..schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument
from .base import SourceCollectionResult


class BiddingProcurementAdapter:
    source_type = "bidding_procurement"
    source_name = "全国公共资源交易/招标采购信息源"

    def __init__(self, documents: list[SourceDocument] | None = None) -> None:
        self._documents = list(documents or [])

    def collect(
        self,
        *,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
    ) -> SourceCollectionResult:
        if self._documents:
            return SourceCollectionResult(documents=[_normalize_bidding_document(item) for item in self._documents])
        return SourceCollectionResult(
            documents=[],
            limitations=["招中标/采购适配器未返回可靠证据，该来源仅作为辅助信息。"],
        )


def _normalize_bidding_document(document: SourceDocument) -> SourceDocument:
    return SourceDocument(
        id=document.id,
        source_type="bidding_procurement",
        source_name=document.source_name or BiddingProcurementAdapter.source_name,
        title=document.title,
        content=document.content,
        url=document.url,
        published_at=document.published_at,
        authority_score=float(document.authority_score or 0.85),
        relevance_scope=document.relevance_scope or "market_demand",
        metadata=document.metadata,
    )
