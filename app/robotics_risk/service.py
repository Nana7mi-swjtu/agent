from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .adapters import (
    BiddingProcurementAdapter,
    CninfoAnnouncementAdapter,
    EvidenceSourceAdapter,
    GovPolicyAdapter,
    SourceUnavailableError,
)
from .extraction import extract_events
from .profiling import build_enterprise_profile
from .rendering import build_result
from .schemas import AnalysisScope, RoboticsInsightRequest, RoboticsInsightResult, SourceDocument
from .scoring import build_signals


class RoboticsInsightValidationError(ValueError):
    pass


def analyze_robotics_enterprise_risk_opportunity(
    request: RoboticsInsightRequest | dict[str, Any],
    *,
    adapters: Iterable[EvidenceSourceAdapter] | None = None,
) -> RoboticsInsightResult:
    normalized_request = _normalize_request(request)
    if not normalized_request.enterprise_name.strip():
        raise RoboticsInsightValidationError("enterprise_name is required")

    analysis_scope = AnalysisScope(
        time_range=normalized_request.time_range or "近30天",
        focus=normalized_request.focus or "综合",
        dimensions=normalized_request.dimensions or ["政策", "公告", "招中标", "竞争"],
    )
    profile = build_enterprise_profile(normalized_request)
    documents, source_limitations = _collect_documents(
        request=normalized_request,
        profile=profile,
        adapters=list(adapters) if adapters is not None else _default_adapters(),
    )
    events = extract_events(documents)
    opportunities, risks = build_signals(events=events, sources=documents, profile=profile)
    limitations = [*profile.limitations, *source_limitations]
    if not documents:
        limitations.append("未检索到可用于风险机会洞察的来源文档。")
    if not events and documents:
        limitations.append("已获取来源文档，但未抽取到明确风险或机会事件。")

    return build_result(
        target_company={
            "name": normalized_request.enterprise_name,
            "stockCode": normalized_request.stock_code,
        },
        analysis_scope=analysis_scope,
        profile=profile,
        opportunities=opportunities,
        risks=risks,
        events=events,
        sources=documents,
        limitations=_dedupe(limitations),
    )


def _normalize_request(request: RoboticsInsightRequest | dict[str, Any]) -> RoboticsInsightRequest:
    if isinstance(request, RoboticsInsightRequest):
        return request
    if isinstance(request, dict):
        return RoboticsInsightRequest.from_dict(request)
    raise RoboticsInsightValidationError("request must be a RoboticsInsightRequest or dict")


def _default_adapters() -> list[EvidenceSourceAdapter]:
    return [
        GovPolicyAdapter(),
        CninfoAnnouncementAdapter(),
        BiddingProcurementAdapter(),
    ]


def _collect_documents(
    *,
    request: RoboticsInsightRequest,
    profile,
    adapters: list[EvidenceSourceAdapter],
) -> tuple[list[SourceDocument], list[str]]:
    documents: list[SourceDocument] = []
    limitations: list[str] = []
    for adapter in adapters:
        source_type = str(getattr(adapter, "source_type", "unknown"))
        try:
            result = adapter.collect(request=request, profile=profile)
        except SourceUnavailableError as exc:
            limitations.append(f"{exc.source_type}来源不可用：{exc}")
            continue
        except Exception as exc:
            limitations.append(f"{source_type}来源不可用：{exc}")
            continue
        documents.extend(result.documents)
        limitations.extend(result.limitations)
    return _dedupe_documents(documents), _dedupe(limitations)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _dedupe_documents(documents: list[SourceDocument]) -> list[SourceDocument]:
    seen: set[str] = set()
    result: list[SourceDocument] = []
    for document in documents:
        key = document.id or f"{document.source_type}:{document.title}:{document.url}"
        if key in seen:
            continue
        seen.add(key)
        result.append(document)
    return result
