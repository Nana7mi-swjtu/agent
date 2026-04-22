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
            "briefMarkdown": self.brief_markdown,
        }
        return _drop_empty(payload)
