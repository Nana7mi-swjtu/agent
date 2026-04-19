from __future__ import annotations

from ..schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument
from .base import SourceCollectionResult


class GovPolicyAdapter:
    source_type = "gov_policy"
    source_name = "国务院政策文件库"

    def __init__(self, documents: list[SourceDocument] | None = None) -> None:
        self._documents = list(documents or [])

    def collect(
        self,
        *,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
    ) -> SourceCollectionResult:
        if self._documents:
            return SourceCollectionResult(documents=[_normalize_policy_document(item) for item in self._documents])
        return SourceCollectionResult(
            documents=[],
            limitations=["国务院政策文件库适配器尚未配置实时检索，未返回政策证据。"],
        )


def _normalize_policy_document(document: SourceDocument) -> SourceDocument:
    return SourceDocument(
        id=document.id,
        source_type="gov_policy",
        source_name=document.source_name or GovPolicyAdapter.source_name,
        title=document.title,
        content=document.content,
        url=document.url,
        published_at=document.published_at,
        authority_score=float(document.authority_score or 0.95),
        relevance_scope=document.relevance_scope or "industry",
        metadata=document.metadata,
    )
