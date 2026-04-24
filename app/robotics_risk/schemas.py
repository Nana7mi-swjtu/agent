from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


def _drop_empty(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {str(key): _drop_empty(item) for key, item in value.items() if item not in (None, "", [], {})}
    if isinstance(value, list):
        return [_drop_empty(item) for item in value]
    return value


@dataclass(frozen=True)
class RoboticsInsightRequest:
    enterprise_name: str
    stock_code: str = ""
    time_range: str = "近30天"
    focus: str = "综合"
    dimensions: list[str] = field(default_factory=lambda: ["政策", "公告", "招中标", "竞争"])
    context: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoboticsInsightRequest":
        dimensions = payload.get("dimensions", [])
        if not isinstance(dimensions, list):
            dimensions = []
        return cls(
            enterprise_name=str(payload.get("enterprise_name") or payload.get("enterpriseName") or "").strip(),
            stock_code=str(payload.get("stock_code") or payload.get("stockCode") or "").strip(),
            time_range=str(payload.get("time_range") or payload.get("timeRange") or "近30天").strip(),
            focus=str(payload.get("focus") or "综合").strip(),
            dimensions=[str(item).strip() for item in dimensions if str(item).strip()],
            context=str(payload.get("context") or "").strip(),
        )


@dataclass
class AnalysisScope:
    time_range: str
    focus: str
    dimensions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(self)


@dataclass
class EnterpriseProfile:
    name: str
    stock_code: str = ""
    industry: str = "机器人"
    segments: list[str] = field(default_factory=list)
    chain_positions: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(self)


@dataclass
class SourceDocument:
    id: str
    source_type: str
    source_name: str
    title: str
    content: str
    url: str = ""
    published_at: str = ""
    authority_score: float = 0.6
    relevance_scope: str = "industry"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(self)


@dataclass
class SourceRetrievalDiagnostic:
    source_type: str
    status: str
    query_strategy: str = ""
    cache_decision: str = ""
    raw_count: int | None = None
    filtered_count: int | None = None
    document_count: int | None = None
    failure_reason: str = ""
    started_at: str = ""
    completed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(
            {
                "sourceType": self.source_type,
                "status": self.status,
                "queryStrategy": self.query_strategy,
                "cacheDecision": self.cache_decision,
                "rawCount": self.raw_count,
                "filteredCount": self.filtered_count,
                "documentCount": self.document_count,
                "failureReason": self.failure_reason,
                "startedAt": self.started_at,
                "completedAt": self.completed_at,
                "metadata": dict(self.metadata or {}),
            }
        )


@dataclass
class InsightEvent:
    id: str
    source_document_id: str
    source_type: str
    event_type: str
    title: str
    summary: str
    direction: str
    dimension: str
    evidence_sentence: str
    published_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(self)


@dataclass
class InsightSignal:
    id: str
    type: str
    category: str
    title: str
    impact_score: int
    confidence: float
    reasoning: str
    event_ids: list[str]
    source_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(self)


@dataclass
class RoboticsReaderTheme:
    id: str
    type: str
    title: str
    summary: str
    basis_summary: str = ""
    interpretation_boundary: str = ""
    confidence: float | None = None
    impact_score: int | None = None
    categories: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    signal_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(
            {
                "id": self.id,
                "type": self.type,
                "title": self.title,
                "summary": self.summary,
                "basisSummary": self.basis_summary,
                "interpretationBoundary": self.interpretation_boundary,
                "confidence": self.confidence,
                "impactScore": self.impact_score,
                "categories": list(self.categories),
                "sourceIds": list(self.source_ids),
                "eventIds": list(self.event_ids),
                "signalIds": list(self.signal_ids),
            }
        )


@dataclass
class RoboticsReaderEvidenceReference:
    id: str
    title: str
    source_type: str
    source_name: str
    reader_summary: str
    published_at: str = ""
    url: str = ""
    locator: str = ""
    relevance_scope: str = ""
    verification_status: str = ""
    event_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(
            {
                "id": self.id,
                "title": self.title,
                "sourceType": self.source_type,
                "sourceName": self.source_name,
                "readerSummary": self.reader_summary,
                "publishedAt": self.published_at,
                "url": self.url,
                "locator": self.locator,
                "relevanceScope": self.relevance_scope,
                "verificationStatus": self.verification_status,
                "eventIds": list(self.event_ids),
                "sourceIds": list(self.source_ids),
            }
        )


@dataclass
class RoboticsReaderVisual:
    id: str
    type: str
    title: str
    caption: str
    interpretation_boundary: str = ""
    render_payload: dict[str, Any] = field(default_factory=dict)
    source_ids: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    signal_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(
            {
                "id": self.id,
                "type": self.type,
                "title": self.title,
                "caption": self.caption,
                "interpretationBoundary": self.interpretation_boundary,
                "renderPayload": dict(self.render_payload or {}),
                "sourceIds": list(self.source_ids),
                "eventIds": list(self.event_ids),
                "signalIds": list(self.signal_ids),
            }
        )


@dataclass
class RoboticsReaderPacket:
    schema_version: str
    target_company: dict[str, Any]
    analysis_scope: dict[str, Any]
    enterprise_profile: dict[str, Any]
    executive_summary: dict[str, str]
    opportunities: list[RoboticsReaderTheme] = field(default_factory=list)
    risks: list[RoboticsReaderTheme] = field(default_factory=list)
    evidence_references: list[RoboticsReaderEvidenceReference] = field(default_factory=list)
    visual_summaries: list[RoboticsReaderVisual] = field(default_factory=list)
    fact_table_refs: list[str] = field(default_factory=list)
    chart_candidate_refs: list[str] = field(default_factory=list)
    rendered_asset_refs: list[str] = field(default_factory=list)
    interpretation_boundaries: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(
            {
                "schemaVersion": self.schema_version,
                "targetCompany": dict(self.target_company or {}),
                "analysisScope": dict(self.analysis_scope or {}),
                "enterpriseProfile": dict(self.enterprise_profile or {}),
                "executiveSummary": dict(self.executive_summary or {}),
                "opportunities": [item.to_dict() for item in self.opportunities],
                "risks": [item.to_dict() for item in self.risks],
                "evidenceReferences": [item.to_dict() for item in self.evidence_references],
                "visualSummaries": [item.to_dict() for item in self.visual_summaries],
                "factTableRefs": list(self.fact_table_refs),
                "chartCandidateRefs": list(self.chart_candidate_refs),
                "renderedAssetRefs": list(self.rendered_asset_refs),
                "interpretationBoundaries": list(self.interpretation_boundaries),
                "limitations": list(self.limitations),
            }
        )


@dataclass
class RoboticsInsightResult:
    module: str
    target_company: dict[str, Any]
    analysis_scope: AnalysisScope
    enterprise_profile: EnterpriseProfile
    summary: dict[str, str]
    opportunities: list[InsightSignal]
    risks: list[InsightSignal]
    events: list[InsightEvent]
    sources: list[SourceDocument]
    limitations: list[str]
    brief_markdown: str
    reader_packet: RoboticsReaderPacket | None = None
    fact_tables: list[dict[str, Any]] = field(default_factory=list)
    chart_candidates: list[dict[str, Any]] = field(default_factory=list)
    rendered_assets: list[dict[str, Any]] = field(default_factory=list)
    status: str = "done"
    source_diagnostics: list[SourceRetrievalDiagnostic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "module": self.module,
            "status": self.status,
            "targetCompany": self.target_company,
            "analysisScope": self.analysis_scope.to_dict(),
            "enterpriseProfile": self.enterprise_profile.to_dict(),
            "summary": self.summary,
            "opportunities": [item.to_dict() for item in self.opportunities],
            "risks": [item.to_dict() for item in self.risks],
            "events": [item.to_dict() for item in self.events],
            "sources": [item.to_dict() for item in self.sources],
            "limitations": list(self.limitations),
            "sourceDiagnostics": [item.to_dict() for item in self.source_diagnostics],
            "readerPacket": self.reader_packet.to_dict() if self.reader_packet is not None else {},
            "factTables": [dict(item) for item in self.fact_tables if isinstance(item, dict)],
            "chartCandidates": [dict(item) for item in self.chart_candidates if isinstance(item, dict)],
            "renderedAssets": [dict(item) for item in self.rendered_assets if isinstance(item, dict)],
        }
        return _drop_empty(payload)
