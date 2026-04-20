from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .adapters import (
    BiddingProcurementAdapter,
    CninfoAnnouncementAdapter,
    EvidenceSourceAdapter,
    GovPolicyAdapter,
    SourceCollectionResult,
)
from .document_handoff import build_document_handoff
from .repository import SOURCE_BIDDING, SOURCE_CNINFO, SOURCE_POLICY
from .run_repository import RoboticsInsightRunRepository
from .schemas import RoboticsInsightRequest, RoboticsInsightResult
from .service import RoboticsInsightValidationError, analyze_robotics_enterprise_risk_opportunity

SUBAGENT_NAME = "robotics_risk_opportunity_subagent"
DEFAULT_DIMENSIONS = ["政策", "公告", "招中标", "竞争"]


@dataclass(frozen=True)
class RoboticsSubagentEnterprise:
    name: str
    stock_code: str = ""
    aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoboticsSubagentAnalysisScope:
    time_range: str = "近30天"
    focus: str = "综合"
    dimensions: list[str] = field(default_factory=lambda: list(DEFAULT_DIMENSIONS))


@dataclass(frozen=True)
class RoboticsSubagentSourceControls:
    use_policy: bool = True
    use_cninfo: bool = True
    use_bidding: bool = True
    prefer_cache: bool = True
    allow_live_fetch: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RoboticsSubagentSourceControls":
        data = dict(payload or {})
        return cls(
            use_policy=_bool_value(data, "use_policy", "usePolicy", default=True),
            use_cninfo=_bool_value(data, "use_cninfo", "useCninfo", default=True),
            use_bidding=_bool_value(data, "use_bidding", "useBidding", default=True),
            prefer_cache=_bool_value(data, "prefer_cache", "preferCache", default=True),
            allow_live_fetch=_bool_value(data, "allow_live_fetch", "allowLiveFetch", default=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "usePolicy": self.use_policy,
            "useCninfo": self.use_cninfo,
            "useBidding": self.use_bidding,
            "preferCache": self.prefer_cache,
            "allowLiveFetch": self.allow_live_fetch,
        }


@dataclass(frozen=True)
class RoboticsRiskSubagentInput:
    enterprise: RoboticsSubagentEnterprise
    analysis_scope: RoboticsSubagentAnalysisScope = field(default_factory=RoboticsSubagentAnalysisScope)
    source_controls: RoboticsSubagentSourceControls = field(default_factory=RoboticsSubagentSourceControls)
    conversation_context: str = ""
    upstream_evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoboticsRiskSubagentInput":
        data = dict(payload or {})
        enterprise_data = dict(data.get("enterprise") or data.get("targetEnterprise") or {})
        scope_data = dict(data.get("analysisScope") or data.get("analysis_scope") or {})
        source_controls = RoboticsSubagentSourceControls.from_dict(
            data.get("sourceControls") or data.get("source_controls") or {}
        )
        dimensions = scope_data.get("dimensions") or data.get("dimensions") or list(DEFAULT_DIMENSIONS)
        if not isinstance(dimensions, list):
            dimensions = list(DEFAULT_DIMENSIONS)
        return cls(
            enterprise=RoboticsSubagentEnterprise(
                name=_clean_text(enterprise_data.get("name") or data.get("enterpriseName") or data.get("enterprise_name")),
                stock_code=_clean_text(
                    enterprise_data.get("stockCode")
                    or enterprise_data.get("stock_code")
                    or data.get("stockCode")
                    or data.get("stock_code")
                ),
                aliases=_clean_list(enterprise_data.get("aliases") or data.get("aliases") or []),
            ),
            analysis_scope=RoboticsSubagentAnalysisScope(
                time_range=_clean_text(scope_data.get("timeRange") or scope_data.get("time_range") or data.get("timeRange"))
                or "近30天",
                focus=_clean_text(scope_data.get("focus") or data.get("focus")) or "综合",
                dimensions=_clean_list(dimensions) or list(DEFAULT_DIMENSIONS),
            ),
            source_controls=source_controls,
            conversation_context=_clean_text(
                data.get("conversationContext") or data.get("conversation_context") or data.get("context")
            ),
            upstream_evidence=_clean_evidence(data.get("upstreamEvidence") or data.get("upstream_evidence") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_request(self) -> RoboticsInsightRequest:
        context_parts = [self.conversation_context, *_upstream_context_lines(self.upstream_evidence)]
        return RoboticsInsightRequest(
            enterprise_name=self.enterprise.name,
            stock_code=self.enterprise.stock_code,
            time_range=self.analysis_scope.time_range,
            focus=self.analysis_scope.focus,
            dimensions=list(self.analysis_scope.dimensions),
            context="\n".join(part for part in context_parts if part).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(
            {
                "enterprise": {
                    "name": self.enterprise.name,
                    "stockCode": self.enterprise.stock_code,
                    "aliases": list(self.enterprise.aliases),
                },
                "analysisScope": {
                    "timeRange": self.analysis_scope.time_range,
                    "focus": self.analysis_scope.focus,
                    "dimensions": list(self.analysis_scope.dimensions),
                },
                "sourceControls": self.source_controls.to_dict(),
                "conversationContext": self.conversation_context,
                "upstreamEvidence": list(self.upstream_evidence),
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True)
class RoboticsRiskSubagentOutput:
    status: str
    run_id: str = ""
    target_company: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    document_handoff: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    source_references: list[dict[str, Any]] = field(default_factory=list)
    source_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    normalized_input: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(
            {
                "subagent": SUBAGENT_NAME,
                "status": self.status,
                "runId": self.run_id,
                "targetCompany": self.target_company,
                "result": self.result,
                "documentHandoff": self.document_handoff,
                "limitations": list(self.limitations),
                "sourceReferences": list(self.source_references),
                "sourceDiagnostics": list(self.source_diagnostics),
                "normalizedInput": self.normalized_input,
                "errorMessage": self.error_message,
            }
        )


def run_robotics_risk_subagent(
    payload: RoboticsRiskSubagentInput | dict[str, Any],
    *,
    db: Any | None = None,
    run_repository: Any | None = None,
    adapters: Iterable[EvidenceSourceAdapter] | None = None,
    evidence_cache: Any | None = None,
    company_resolver: Any | None = None,
    now_factory: Callable[[], datetime] | None = None,
    id_factory: Callable[[], str] | None = None,
) -> RoboticsRiskSubagentOutput:
    normalized = payload if isinstance(payload, RoboticsRiskSubagentInput) else RoboticsRiskSubagentInput.from_dict(payload)
    normalized_payload = normalized.to_dict()
    request = normalized.to_request()
    if not request.enterprise_name.strip():
        return RoboticsRiskSubagentOutput(
            status="need_input",
            limitations=["缺少目标企业名称，无法启动机器人风险机会洞察。"],
            normalized_input=normalized_payload,
            error_message="enterprise_name is required",
        )

    repository = run_repository
    if repository is None and db is not None:
        repository = RoboticsInsightRunRepository(db)
    run_id = _new_run_id(id_factory)
    started_at = _now(now_factory)

    if repository is not None:
        try:
            repository.create_run(
                run_id=run_id,
                enterprise_name=request.enterprise_name,
                stock_code=request.stock_code,
                request_payload=normalized_payload,
                started_at=started_at,
            )
        except Exception as exc:
            return RoboticsRiskSubagentOutput(
                status="failed",
                run_id=run_id,
                limitations=["运行记录创建失败，未启动来源检索。"],
                normalized_input=normalized_payload,
                error_message=str(exc),
            )

    try:
        result = analyze_robotics_enterprise_risk_opportunity(
            request,
            adapters=_select_adapters(adapters=adapters, controls=normalized.source_controls),
            evidence_cache=evidence_cache if normalized.source_controls.prefer_cache else None,
            company_resolver=company_resolver,
        )
        status = _result_status(result)
        result_payload = result.to_dict()
        result_payload["status"] = status
        handoff_payload = build_document_handoff(result)
        handoff_payload["runId"] = run_id
        if repository is not None:
            repository.complete_run(
                run_id=run_id,
                result_payload=result_payload,
                handoff_payload=handoff_payload,
                status=status,
                completed_at=_now(now_factory),
            )
        return RoboticsRiskSubagentOutput(
            status=status,
            run_id=run_id,
            target_company=dict(result.target_company),
            result=result_payload,
            document_handoff=handoff_payload,
            limitations=list(result.limitations),
            source_references=_source_references(result),
            source_diagnostics=[item.to_dict() for item in result.source_diagnostics],
            normalized_input=normalized_payload,
        )
    except RoboticsInsightValidationError as exc:
        return _failed_output(
            run_id=run_id,
            repository=repository,
            normalized_payload=normalized_payload,
            error_message=str(exc),
            now_factory=now_factory,
        )
    except Exception as exc:
        return _failed_output(
            run_id=run_id,
            repository=repository,
            normalized_payload=normalized_payload,
            error_message=str(exc),
            now_factory=now_factory,
        )


def _select_adapters(
    *,
    adapters: Iterable[EvidenceSourceAdapter] | None,
    controls: RoboticsSubagentSourceControls,
) -> list[EvidenceSourceAdapter]:
    selected_types = _selected_source_types(controls)
    if adapters is None:
        if controls.allow_live_fetch:
            candidates: list[EvidenceSourceAdapter] = []
            if controls.use_policy:
                candidates.append(GovPolicyAdapter())
            if controls.use_cninfo:
                candidates.append(CninfoAnnouncementAdapter())
            if controls.use_bidding:
                candidates.append(BiddingProcurementAdapter())
            return candidates
        return [_CacheOnlyAdapter(source_type) for source_type in selected_types]

    filtered = [
        adapter
        for adapter in adapters
        if str(getattr(adapter, "source_type", "")) not in _known_source_types()
        or str(getattr(adapter, "source_type", "")) in selected_types
    ]
    if controls.allow_live_fetch:
        return filtered
    return [
        _CacheOnlyAdapter(str(getattr(adapter, "source_type", "unknown")))
        for adapter in filtered
        if str(getattr(adapter, "source_type", "unknown")) in selected_types
    ]


def _selected_source_types(controls: RoboticsSubagentSourceControls) -> list[str]:
    source_types: list[str] = []
    if controls.use_policy:
        source_types.append(SOURCE_POLICY)
    if controls.use_cninfo:
        source_types.append(SOURCE_CNINFO)
    if controls.use_bidding:
        source_types.append(SOURCE_BIDDING)
    return source_types


def _known_source_types() -> set[str]:
    return {SOURCE_POLICY, SOURCE_CNINFO, SOURCE_BIDDING}


@dataclass
class _CacheOnlyAdapter:
    source_type: str

    def collect(self, *, request: RoboticsInsightRequest, profile: Any) -> SourceCollectionResult:
        return SourceCollectionResult(
            documents=[],
            limitations=[f"{self.source_type}实时检索已关闭，仅允许使用缓存证据。"],
        )


def _result_status(result: RoboticsInsightResult) -> str:
    if not result.sources:
        return "partial"
    degraded_terms = ("不可用", "未返回", "受限", "解析失败", "缓存不可用", "实时检索已关闭")
    if any(any(term in item for term in degraded_terms) for item in result.limitations):
        return "partial"
    return "done"


def _failed_output(
    *,
    run_id: str,
    repository: Any | None,
    normalized_payload: dict[str, Any],
    error_message: str,
    now_factory: Callable[[], datetime] | None,
) -> RoboticsRiskSubagentOutput:
    limitations = [f"机器人风险机会洞察执行失败：{error_message}"]
    if repository is not None and run_id:
        try:
            repository.fail_run(
                run_id=run_id,
                error_message=error_message,
                result_payload={"status": "failed", "limitations": limitations},
                handoff_payload={"limitations": limitations},
                completed_at=_now(now_factory),
            )
        except Exception as persist_exc:
            limitations.append(f"运行记录失败状态写入失败：{persist_exc}")
    return RoboticsRiskSubagentOutput(
        status="failed",
        run_id=run_id,
        limitations=limitations,
        normalized_input=normalized_payload,
        error_message=error_message,
    )


def _source_references(result: RoboticsInsightResult) -> list[dict[str, Any]]:
    return [
        _drop_empty(
            {
                "id": source.id,
                "sourceType": source.source_type,
                "sourceName": source.source_name,
                "title": source.title,
                "publishedAt": source.published_at,
                "url": source.url,
                "relevanceScope": source.relevance_scope,
            }
        )
        for source in result.sources
    ]


def _new_run_id(id_factory: Callable[[], str] | None) -> str:
    if id_factory is not None:
        return _clean_text(id_factory())
    return f"rrisk_{uuid.uuid4().hex[:16]}"


def _now(now_factory: Callable[[], datetime] | None) -> datetime:
    return now_factory() if now_factory is not None else datetime.utcnow()


def _upstream_context_lines(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in items[:10]:
        title = _clean_text(item.get("title") or item.get("name"))
        summary = _clean_text(item.get("summary") or item.get("content") or item.get("snippet"))
        if title or summary:
            lines.append(f"上游证据：{title} {summary}".strip())
    return lines


def _clean_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            cleaned.append(dict(item))
    return cleaned


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        clean = _clean_text(item)
        if clean and clean not in result:
            result.append(clean)
    return result


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _bool_value(payload: dict[str, Any], snake_key: str, camel_key: str, *, default: bool) -> bool:
    value = payload.get(snake_key, payload.get(camel_key, default))
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


def _drop_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _drop_empty(item)
            for key, item in value.items()
            if item not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_drop_empty(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return _drop_empty(asdict(value))
    return value
